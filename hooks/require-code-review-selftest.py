#!/usr/bin/env python3
"""Self-test for require-code-review.py: verdict matching, and which repo it asks.

The gate has now missed a real review four times, each time because its
vocabulary drifted from whatever the review flow actually writes. Every miss
cost a SKIP_REVIEW_GATE=1, and a gate you routinely disable is not a gate.
This pins what counts as a verdict and, just as importantly, what does not.

The second half pins WHICH repo the hook asks about. On 2026-09-17 a session
started in one repo ran `cd <a second repo> && gh pr merge 24`, and the hook
looked up PR 24 of the session's repo. It blocked a reviewed PR. The mirror is
worse: it would pass an unreviewed PR whenever the session repo's PR with the
same number happens to be reviewed. Those cases run the real hook as a
subprocess against a fake `gh` on PATH, which answers per repo and logs which
repo each call resolved to, so a test can assert the question as well as the
answer.

Run: ./hooks/require-code-review-selftest.py
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = pathlib.Path(__file__).with_name("require-code-review.py")

# (comment body, should it satisfy the gate, what this pins)
CASES = [
    # The fresh-eye skill tells reviewers to open with exactly one word.
    ("PASS\n\n## Executive TL;DR\nAll good.", True, "fresh-eye PASS"),
    ("BLOCK\n\n## Executive TL;DR\nTwo defects.", True, "fresh-eye BLOCK"),
    ("**PASS**\n\nreviewed at abc123", True, "PASS in bold"),
    ("> BLOCK", True, "BLOCK in a quote"),
    ("## PASS", True, "PASS as a heading"),
    ("Full report below.\n\nPASS\n", True, "verdict on a later line"),
    # The vocabularies that were already known.
    ("Verdict: approve", True, "Verdict: with a space after the colon"),
    ("Verdict:approve", True, "Verdict: with no space"),
    ("APPROVE_WITH_NITS", True, "bare uppercase marker"),
    ("READY TO MERGE", True, "LOOP.md vocabulary"),
    ("Approve with nits.", True, "opener without the word verdict"),
    ("LGTM", True, "lgtm"),
    # What must NOT satisfy it. These are the whole point: PASS and BLOCK are
    # ordinary words in prose about CI, so they only count stated up front.
    ("CI has to PASS before we merge this.", False, "PASS mid-sentence"),
    ("This would BLOCK the post job.", False, "BLOCK mid-sentence"),
    ("REVIEW\n\nA human needs to decide.", False, "REVIEW is a human's call"),
    ("Review the diff carefully.", False, "Review as an imperative"),
    ("I approve of this direction.", False, "prose about approving"),
    ("blocked on #123", False, "blocked in prose"),
    ("passport control", False, "pass as a word prefix"),
    ("blockchain notes", False, "block as a word prefix"),
    ("Nice work, shipping it.", False, "plain praise"),
    ("", False, "empty body"),
]


# The fake gh. It resolves the repo the way real gh does: a PR URL wins, then
# -R/--repo, then GH_REPO, then the git remote of the working directory (here a
# map from directory to repo name). It ignores --jq and prints text already in
# the shape the hook's jq filters produce. Every resolved lookup is logged.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, re, sys
fx = json.load(open(os.environ["FAKE_GH_FIXTURES"]))
args = sys.argv[1:]
repo, rest, i = None, [], 0
while i < len(args):
    a = args[i]
    if a in ("-R", "--repo"):
        repo = args[i + 1]; i += 2; continue
    if a.startswith("--repo="):
        repo = a.split("=", 1)[1]; i += 1; continue
    if a in ("--json", "--jq"):
        if a == "--json":
            field = args[i + 1]
        i += 2; continue
    rest.append(a); i += 1
sub, sel = rest[1], (rest[2] if len(rest) > 2 else "current")
m = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", sel)
if m:
    repo, sel = m.group(1), m.group(2)
repo = repo or os.environ.get("GH_REPO") or fx["cwds"].get(os.path.realpath(os.getcwd()))
host = os.environ.get("GH_HOST")
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write("%s%s#%s\n" % (host + ":" if host else "", repo, sel))
pr = fx["repos"].get(repo or "", {}).get(sel)
if pr is None:
    sys.exit(1)
key = "checks" if sub == "checks" else field.split(",")[0]
print(pr.get(key, ""))
"""

BIG = "src/thing.py 30 6"          # 36 code lines, over the threshold
UNREVIEWED = {"files": BIG}
REVIEWED = {"files": BIG, "comments": "Verdict: PASS\n\nreviewed at the head commit"}
# In every repo but the session's, PR 24 is reviewed and PR 25 is not. The
# session repo is the other way round. So a hook that asks the wrong repo gets
# the wrong answer in BOTH directions, and each form below is tried both ways.
TARGET = {"24": REVIEWED, "25": UNREVIEWED}
REPOS = {
    "sess/repo": {"24": UNREVIEWED, "25": REVIEWED, "current": REVIEWED},
    "other/repo": dict(TARGET, **{
        "26": dict(REVIEWED, checks="PENDING build"), "current": UNREVIEWED}),
    "space/repo": TARGET,
    "home/repo": TARGET,
    "flag/repo": TARGET,
}

ALLOW, BLOCK = 0, 2
# (command, exit code wanted, repo#pr lookups wanted, what this pins).
# {S} is the session repo, {O} a second repo, {SP} one with a space in its path.
TARGET_CASES = [
    ("gh pr merge 25 --squash", ALLOW, ["sess/repo#25"], "no redirect: the session repo, as before"),
    ("gh pr merge 24 --squash", BLOCK, ["sess/repo#24"], "no redirect: still blocks"),
    # The reproduced false block, and its dangerous mirror.
    ("cd {O} && gh pr merge 24 --squash --delete-branch", ALLOW, ["other/repo#24"],
     "cd && merge: reviewed in the target, unreviewed in the session repo"),
    ("cd {O} && gh pr merge 25 --squash", BLOCK, ["other/repo#25"],
     "cd && merge: unreviewed in the target, reviewed in the session repo"),
    ("cd {O}; gh pr merge 24", ALLOW, ["other/repo#24"], "cd ; merge"),
    ("cd {O}\ngh pr merge 25", BLOCK, ["other/repo#25"], "cd, newline, merge"),
    ("pushd {O} && gh pr merge 25", BLOCK, ["other/repo#25"], "pushd"),
    ("cd ../other && gh pr merge 24", ALLOW, ["other/repo#24"], "relative cd, from the session cwd"),
    ("cd '{SP}' && gh pr merge 24", ALLOW, ["space/repo#24"], "single-quoted path with a space"),
    ('cd "{SP}" && gh pr merge 25', BLOCK, ["space/repo#25"], "double-quoted path with a space"),
    ("cd ~/homerepo && gh pr merge 24", ALLOW, ["home/repo#24"], "~ path"),
    ("cd ~/homerepo && gh pr merge 25", BLOCK, ["home/repo#25"], "~ path, mirror"),
    ("{{ cd {O}; gh pr merge 25; }}", BLOCK, ["other/repo#25"], "cd inside a brace group"),
    ("(cd {O} && true); gh pr merge 25", ALLOW, ["sess/repo#25"], "a cd inside a subshell ends with it"),
    ("bash -c 'cd {O} && gh pr merge 25'", BLOCK, ["other/repo#25"], "bash -c"),
    # An explicit repo.
    ("gh pr merge 24 -R flag/repo", ALLOW, ["flag/repo#24"], "-R"),
    ("gh pr merge 25 -R flag/repo", BLOCK, ["flag/repo#25"], "-R, mirror"),
    ("gh pr merge -R flag/repo --squash 25", BLOCK, ["flag/repo#25"], "-R before the number"),
    ("gh pr merge 24 --repo flag/repo", ALLOW, ["flag/repo#24"], "--repo"),
    ("gh pr merge 24 --repo=flag/repo", ALLOW, ["flag/repo#24"], "--repo="),
    ("gh pr merge 25 --repo=flag/repo", BLOCK, ["flag/repo#25"], "--repo=, mirror"),
    ("gh pr merge https://github.com/flag/repo/pull/24 --squash", ALLOW, ["flag/repo#24"], "PR URL"),
    ("gh pr merge https://github.com/flag/repo/pull/25", BLOCK, ["flag/repo#25"], "PR URL, mirror"),
    ("GH_REPO=flag/repo gh pr merge 24", ALLOW, ["flag/repo#24"], "GH_REPO prefix"),
    ("GH_REPO=flag/repo gh pr merge 25", BLOCK, ["flag/repo#25"], "GH_REPO prefix, mirror"),
    ("export GH_REPO=flag/repo; gh pr merge 25", BLOCK, ["flag/repo#25"], "exported GH_REPO"),
    # gh's own precedence: GH_REPO beats the working directory, -R beats both.
    ("cd {O} && GH_REPO=flag/repo gh pr merge 24 -R space/repo", ALLOW, ["space/repo#24"],
     "-R beats GH_REPO beats cd"),
    # Several merges, each judged against its own target.
    ("gh pr merge 25 && cd {O} && gh pr merge 24", ALLOW, ["sess/repo#25", "other/repo#24"],
     "two merges, two targets, both reviewed"),
    ("gh pr merge 25 && cd {O} && gh pr merge 25", BLOCK, ["sess/repo#25", "other/repo#25"],
     "two merges, the second target unreviewed"),
    # A merge with no number is invisible to detection, as it was in 1.6.0.
    # Filed as emmanuelwunjc/yw-workflow#17.
    ("cd {O} && gh pr merge --squash", ALLOW, [], "no number: detection cannot see it (#17)"),
    ("gh pr merge 24 --squash 2>&1", BLOCK, ["sess/repo#24"], "a redirect is not a PR number"),
    # Flags between `merge` and the number, with a value flag's value skipped.
    ("gh pr merge --squash 24", BLOCK, ["sess/repo#24"], "a flag before the number"),
    ("gh pr merge --body text 24", BLOCK, ["sess/repo#24"], "--body's value is not the PR"),
    ("gh pr merge -t subject 24", BLOCK, ["sess/repo#24"], "-t's value is not the PR"),
    ("gh pr merge --body text 25", ALLOW, ["sess/repo#25"], "--body before the number, mirror"),
    # Gate 1 asks the target too.
    ("cd {O} && gh pr merge 26", BLOCK, ["other/repo#26"], "pending check in the target repo"),
    # A target that cannot be worked out blocks and asks for -R.
    ('cd "$SOMEWHERE" && gh pr merge 25', BLOCK, [], "cd to a variable: blocked, nothing guessed"),
    # A cd to a path that does not exist is not unknown, it is unchanged: the cd
    # fails, so `;` leaves the shell where it was and `&&` drops the merge.
    ("cd /no/such/dir/anywhere && gh pr merge 25", ALLOW, ["sess/repo#25"],
     "cd to a missing directory: the old directory still answers"),
    ("cd /no/such/dir/anywhere && gh pr merge 24", BLOCK, ["sess/repo#24"],
     "cd to a missing directory, mirror: still checked, in the old directory"),
    ("cd - && gh pr merge 25", BLOCK, [], "cd -"),
    ('cd "$SOMEWHERE" && gh pr merge 24 -R flag/repo', ALLOW, ["flag/repo#24"],
     "an explicit -R makes an unknown cd irrelevant"),
    ('cd "$SOMEWHERE" && cd {O} && gh pr merge 24', ALLOW, ["other/repo#24"],
     "an absolute cd after an unknown one is known again"),
    # Text that only MENTIONS a merge is judged as a merge. That is 1.6.0's
    # known false block, kept deliberately: the alternative is a walk that
    # decides what is and is not a merge, and review round 2 measured what that
    # costs. The workaround is in every block message.
    ('git commit -m "then gh pr merge 24"', BLOCK, ["sess/repo#24"],
     "1.6.0's false block: a commit message is judged as a merge"),
    ('git commit -m "then gh pr merge 25"', ALLOW, ["sess/repo#25"],
     "the same mention of a reviewed PR goes through"),
    ("SKIP_REVIEW_GATE=1 gh pr merge 24", ALLOW, [], "the override still works"),
    ("SKIP_REVIEW_GATE=0 gh pr merge 24", BLOCK, ["sess/repo#24"], "=0 is not the override"),
    ("SKIP_REVIEW_GATE=true gh pr merge 24", BLOCK, ["sess/repo#24"], "=true is not the override"),

    # --- Review round 1 of this change, 2026-09-17: BLOCK, three false passes ---
    # Each shape below went through with NO gh call at all. The rule they pin:
    # a merge the hook can see but cannot read down to a literal target blocks.
    #
    # B1, a regression the first version introduced: it read a quoted string as
    # a command only when bash/sh/zsh/eval was the FIRST word.
    ("timeout 60 bash -c 'gh pr merge 24'", BLOCK, ["sess/repo#24"], "B1: runner behind timeout"),
    ("env bash -c 'gh pr merge 24'", BLOCK, ["sess/repo#24"], "B1: runner behind env"),
    ("cd {O} && sudo -u me sh -c 'gh pr merge 25'", BLOCK, ["other/repo#25"], "B1: runner behind sudo, after a cd"),
    ("echo `gh pr merge 24`", BLOCK, ["sess/repo#24"], "B1: backticks"),
    ("cd {O} && echo `gh pr merge 24`", ALLOW, ["other/repo#24"], "B1: backticks, judged in the target"),
    ("echo $(gh pr merge 24)", BLOCK, ["sess/repo#24"], "B1: $( ) still caught"),
    # B2: a variable where a literal is needed. Where the variable stands in for
    # the PR number, detection never sees a merge at all, exactly as in 1.6.0,
    # and that gap is emmanuelwunjc/yw-workflow#17. Where it stands in for the
    # repo, the merge IS detected and the target is unreadable, which blocks.
    ("cd {O} && for n in 25; do gh pr merge $n; done", ALLOW, [], "B2: loop variable as the PR (#17)"),
    ("PR=25; cd {O} && gh pr merge $PR --squash", ALLOW, [], "B2: variable as the PR (#17)"),
    ("gh pr merge 2$n", BLOCK, [], "B2: a variable spliced onto the number"),
    ("gh pr merge 25 -R $REPO", BLOCK, [], "B2: variable as -R"),
    ("export GH_REPO=$R; gh pr merge 25", BLOCK, [], "B2: variable in an exported GH_REPO"),
    ("GH_REPO=$R gh pr merge 25", BLOCK, [], "B2: variable in a GH_REPO prefix"),
    ("GH_HOST=$H gh pr merge 25", BLOCK, [], "B2: variable in a GH_HOST prefix"),
    ("gh pr merge `cat n`", ALLOW, [], "B2: backticks as the PR (#17)"),
    ("echo 25 | xargs -I{{}} gh pr merge {{}}", ALLOW, [], "B2: an xargs placeholder as the PR (#17)"),
    # xargs with a literal number IS detected, and what xargs appends is not in
    # the text, so the merge cannot be tied to one PR.
    ("echo --squash | xargs gh pr merge 24", BLOCK, [], "xargs in front of a literal merge"),
    ("echo 24 | xargs gh pr merge", ALLOW, [], "xargs with no number in the text (#17)"),
    # B3: gh takes -R before the subcommand too, and the shell removes quotes
    # and line continuations before gh sees anything.
    ("gh -R flag/repo pr merge 25", BLOCK, ["flag/repo#25"], "B3: global -R"),
    ("gh --repo=flag/repo pr merge 24", ALLOW, ["flag/repo#24"], "B3: global --repo="),
    ("gh pr \\\n  merge 24", BLOCK, ["sess/repo#24"], "B3: line continuation inside the command"),
    # Quoting that hides the words from the text pattern was 1.6.0's gap and
    # still is: closing it means matching quote-stripped text, which newly
    # blocks `rg "gh pr merge" --max-count 5`. Filed as #16.
    ('"gh" pr merge 24', ALLOW, [], "B3: quoted gh is invisible to detection (#17)"),
    ("gh \"pr\" 'merge' 24", ALLOW, [], "B3: quoted pr and merge (#17)"),
    ("gh pr merge 25 -R=flag/repo", BLOCK, ["flag/repo#25"], "B3: -R=owner/repo"),
    ("gh pr merge 25 -Rflag/repo", BLOCK, ["flag/repo#25"], "B3: attached -Rowner/repo"),
    # The walk reading nothing is not a block by itself. Nothing in these aims
    # the merge anywhere else, so the session's repo is the target and 1.6.0's
    # answer stands.
    ("gh --no-such-flag value pr merge 25", ALLOW, ["sess/repo#25"],
     "the walk reads nothing, no redirect: the session repo answers"),
    ("gh --no-such-flag value pr merge 24", BLOCK, ["sess/repo#24"],
     "the walk reads nothing, no redirect: mirror, still checked"),
    ("gh pr merge 25 && gh --no-such-flag value pr merge 24", BLOCK, ["sess/repo#25"],
     "fewer merges walked than detected: the untied one blocks"),
    ("gh pr\nmerge 25", ALLOW, ["sess/repo#25"], "a newline inside the merge: the session repo answers"),
    ("cd {O} && gh --no-such-flag value pr merge 24", BLOCK, [],
     "the walk reads nothing and a cd could aim it elsewhere"),
    # Nits from the same round. A numberless merge is invisible to detection.
    ("git switch feature && gh pr merge --squash", ALLOW, [], "numberless merge after a git switch (#17)"),
    ("git checkout feature; gh pr merge", ALLOW, [], "numberless merge after a git checkout (#17)"),
    ("gh pr checkout 7 && gh pr merge", ALLOW, [], "numberless merge after gh pr checkout (#17)"),
    ("git switch feature && gh pr merge 25", ALLOW, ["sess/repo#25"], "a number makes the switch irrelevant"),
    ("cat <<EOF\nit's unbalanced\nEOF\ngh pr merge --squash", ALLOW, [], "unbalanced quotes, numberless (#17)"),
    ("cat <<EOF\nit's unbalanced\nEOF\ngh pr merge 24", BLOCK, ["sess/repo#24"],
     "unbalanced quotes: the words cannot be read, the session repo answers"),
    ("cat <<EOF\nit's unbalanced\nEOF\ncd {O} && gh pr merge 24", BLOCK, [],
     "unbalanced quotes plus a cd: nothing is guessed"),
    ("cd {O} && popd && gh pr merge 25", BLOCK, [], "popd leaves the directory unknown"),
    ('gh pr merge 24 --body "SKIP_REVIEW_GATE=1"', BLOCK, ["sess/repo#24"], "override text inside a body is not the override"),
    ("gh pr merge 24 # SKIP_REVIEW_GATE=1", BLOCK, ["sess/repo#24"], "override text in a trailing comment is not the override"),
    ("env SKIP_REVIEW_GATE=1 gh pr merge 24", ALLOW, [], "override as an env argument"),
    ("export SKIP_REVIEW_GATE=1; gh pr merge 24", ALLOW, [], "override exported earlier in the command"),
    ("SKIP_REVIEW_GATE=1 gh pr merge 24; gh pr merge 25", ALLOW, ["sess/repo#25"], "the override covers its own merge only"),
    ("SKIP_REVIEW_GATE=1 gh pr merge 25; gh pr merge 24", BLOCK, ["sess/repo#24"], "the override covers its own merge only, mirror"),
    ("GH_HOST=ghe.example.com gh pr merge 25", ALLOW, ["ghe.example.com:sess/repo#25"], "GH_HOST is copied"),
    ("gh pr merge --squash 2>&1", ALLOW, [], "numberless with a redirect: the 2 is not a PR"),
    ('cd "$SOMEWHERE" && GH_REPO=flag/repo gh pr merge 25', BLOCK, ["flag/repo#25"], "unknown cd, GH_REPO names the repo"),
    ('cd "$SOMEWHERE" && gh pr merge https://github.com/flag/repo/pull/25', BLOCK, ["flag/repo#25"], "unknown cd, a URL names the repo"),
    # Text that is data is judged as a merge anyway, because detection is a text
    # pattern. 1.6.0 did the same. Every one of these is measured in the PR body.
    ("echo gh pr merge 24", BLOCK, ["sess/repo#24"], "an unquoted echo"),
    ('gh pr comment 5 --body "then gh pr merge 24"', BLOCK, ["sess/repo#24"],
     "a PR comment body mentioning a merge"),
    ("watch -n5 gh pr merge 24", BLOCK, ["sess/repo#24"], "watch runs it, so it is a merge"),

    # --- Review round 2 of this change, 2026-09-17: BLOCK, four findings ------
    # The rewrite had regressed detection. These are the shapes 1.6.0 caught and
    # the rewrite passed, plus the read-only shapes the rewrite newly blocked.
    # Each runs both ways: PR 24 is unreviewed in the session repo, 25 reviewed.
    ('echo "out: $(gh pr merge 24)"', BLOCK, ["sess/repo#24"], "R2: merge in $( ) inside a quoted argument"),
    ('echo "out: $(gh pr merge 25)"', ALLOW, ["sess/repo#25"], "R2: same shape, reviewed"),
    ("echo 'gh pr merge 24' | sh", BLOCK, ["sess/repo#24"], "R2: a merge piped to sh"),
    ("echo 'gh pr merge 25' | sh", ALLOW, ["sess/repo#25"], "R2: same shape, reviewed"),
    ("git rebase --exec 'gh pr merge 24' main", BLOCK, ["sess/repo#24"], "R2: a merge git runs"),
    ("git rebase --exec 'gh pr merge 25' main", ALLOW, ["sess/repo#25"], "R2: same shape, reviewed"),
    ("sh -c 'gh pr merge 24'", BLOCK, ["sess/repo#24"], "R2: a bare sh -c"),
    ("sh -c 'gh pr merge 25'", ALLOW, ["sess/repo#25"], "R2: a bare sh -c, reviewed"),
    ("cd {O} && sh -c 'gh pr merge 25'", BLOCK, ["other/repo#25"], "R2: sh -c after a cd"),
    # Read-only commands. No number after `merge`, so detection never fires and
    # no lookup happens at all. These are the ones the rewrite blocked.
    ('grep -rn "gh pr merge" hooks/', ALLOW, [], "R2: grep for the phrase"),
    ("rg -n 'gh pr merge' --type py", ALLOW, [], "R2: rg for the phrase"),
    ("sed -n '/gh pr merge/p' README.md", ALLOW, [], "R2: sed for the phrase"),
    ("awk '/gh pr merge/ {{print NR}}' docs/DECISIONS.md", ALLOW, [], "R2: awk for the phrase"),
    ("gh pr merge --help", ALLOW, [], "R2: the help text"),
    ("gh pr merge --help | head -40", ALLOW, [], "R2: the help text, piped"),
    ("git log --oneline --grep=\"gh pr merge\"", ALLOW, [], "R2: git log --grep"),
    # A merge written inside a data structure. shlex glues the `]]` onto the
    # number; that punctuation is not a shell expansion, so it comes off and the
    # session repo answers, as it did in 1.6.0.
    ("""echo '[["x", "gh pr merge 25"]]' > /dev/null""", ALLOW, ["sess/repo#25"],
     "R2: a merge inside a JSON string"),
    ("""echo '[["x", "gh pr merge 24"]]' > /dev/null""", BLOCK, ["sess/repo#24"],
     "R2: the same, unreviewed"),

    # --- Review round 3 of this change, 2026-09-17: BLOCK, two findings -------
    # R3-1: the override every block message names has to work on the path that
    # blocks a merge the walk could not tie to a command. It did not, so the
    # hook printed "review gate skipped", blocked anyway, and named the
    # workaround that had just been used.
    ("gh pr merge 24 && gh --no-such-flag v pr merge 24", BLOCK, ["sess/repo#24"],
     "R3-1: an untied merge blocks"),
    ("export SKIP_REVIEW_GATE=1; gh pr merge 24 && gh --no-such-flag v pr merge 24",
     ALLOW, [], "R3-1: the export unblocks an untied merge"),
    ("gh pr merge 25 && gh --no-such-flag v pr merge 24", BLOCK, ["sess/repo#25"],
     "R3-1: untied beside a readable merge"),
    ("export SKIP_REVIEW_GATE=1; gh pr merge 25 && gh --no-such-flag v pr merge 24",
     ALLOW, [], "R3-1: the export covers both"),
    # An unknown value flag: the pattern skips its value and reads 25, the walk
    # does not know it takes one and reads 24. So 24 is checked and 25 is untied.
    ("gh pr merge -X 24 25", BLOCK, ["sess/repo#24"],
     "R3-1: an unknown value flag splits what is read"),
    ("export SKIP_REVIEW_GATE=1; gh pr merge -X 24 25", ALLOW, [],
     "R3-1: the export unblocks that too"),
    ("export SKIP_REVIEW_GATE=1; gh pr merge 2$n", ALLOW, [],
     "R3-1: the export unblocks a spliced number"),
    ("SKIP_REVIEW_GATE=1 gh pr merge 24 && gh --no-such-flag v pr merge 24",
     BLOCK, [], "R3-1: a prefix on one merge does not cover an untied one"),
    # R3 nit: the URL key is the PR number, so a query string does not make it a
    # different PR from the one detection counted.
    ("gh pr merge https://github.com/flag/repo/pull/24?x=1", ALLOW, ["flag/repo#24"],
     "R3: a URL with a query string"),
    ("gh pr merge https://github.com/flag/repo/pull/25?x=1", BLOCK, ["flag/repo#25"],
     "R3: a URL with a query string, mirror"),
    # R3 nit: one lookup per distinct target, however often the text names it.
    ("echo 'gh pr merge 24' 'gh pr merge 24' 'gh pr merge 24'", BLOCK, ["sess/repo#24"],
     "R3: the same target three times is asked once"),
    # R3 nit: an assignment in front of the runner comes with it.
    ("env SKIP_REVIEW_GATE=1 bash -c 'gh pr merge 24'", ALLOW, [],
     "R3: env in front of the runner sets it for the subshell"),
    ("env GH_REPO=flag/repo bash -c 'gh pr merge 25'", BLOCK, ["flag/repo#25"],
     "R3: env GH_REPO in front of the runner"),
    ("bash -c 'gh pr merge 24'", BLOCK, ["sess/repo#24"],
     "R3: the same runner with no assignment still blocks"),
]


def run_target_cases(failures: list) -> int:
    tmp = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="rcr-selftest-")))
    dirs = {"S": tmp / "sess", "O": tmp / "other", "SP": tmp / "with space",
            "H": tmp / "home" / "homerepo"}
    for d in dirs.values():
        d.mkdir(parents=True)
    (tmp / "bin").mkdir()
    fake = tmp / "bin" / "gh"
    fake.write_text(FAKE_GH)
    fake.chmod(0o755)
    log = tmp / "gh.log"
    fixtures = tmp / "fixtures.json"
    fixtures.write_text(json.dumps({"repos": REPOS, "cwds": {
        str(dirs["S"]): "sess/repo", str(dirs["O"]): "other/repo",
        str(dirs["SP"]): "space/repo", str(dirs["H"]): "home/repo"}}))
    env = dict(os.environ, PATH=str(tmp / "bin") + os.pathsep + os.environ["PATH"],
               HOME=str(tmp / "home"), FAKE_GH_FIXTURES=str(fixtures),
               FAKE_GH_LOG=str(log))
    env.pop("GH_REPO", None)
    env.pop("GH_HOST", None)
    env.pop("SKIP_REVIEW_GATE", None)

    def run(command, cwd, event_cwd):
        log.write_text("")
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        if event_cwd:
            event["cwd"] = str(event_cwd)
        out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                             capture_output=True, text=True, env=env, cwd=cwd)
        # consecutive duplicates collapse: one PR is asked about up to four times
        asked = []
        for line in log.read_text().split():
            if not asked or asked[-1] != line:
                asked.append(line)
        return out, asked

    def judge(label, out, asked, want_exit, want_asked):
        if out.returncode != want_exit or asked != want_asked:
            failures.append(f"  {label}: wanted exit {want_exit} asking {want_asked}, "
                            f"got exit {out.returncode} asking {asked}")

    paths = {k: str(v) for k, v in dirs.items()}
    for command, want_exit, want_asked, label in TARGET_CASES:
        out, asked = run(command.format(**paths), dirs["S"], None)
        judge(label, out, asked, want_exit, want_asked)
        # Blocked without asking gh anything means the target was unreadable,
        # and that message has to say what to type instead.
        if want_exit == BLOCK and not want_asked and "-R owner/repo" not in out.stderr:
            failures.append(f"  {label}: the block message does not ask for -R owner/repo")

    # The event's cwd is where the Bash tool's shell is now, and an earlier
    # call may have cd'd it away from the folder the hook process starts in.
    out, asked = run("gh pr merge 25", dirs["S"], dirs["O"])
    judge("the event's cwd beats the hook process's cwd", out, asked, BLOCK, ["other/repo#25"])
    # A block has to say which repo it looked in, or a wrong lookup is invisible.
    if "other" not in out.stderr:
        failures.append("  the block message does not name the target it asked about")

    # One lookup per distinct target, however often the text names it. Two
    # things hide this from an ordinary case: the `asked` list collapses
    # consecutive duplicates, and a target that BLOCKS exits before the repeats
    # are ever looked up. So it takes a reviewed PR, which is allowed and
    # therefore checked every time, and the raw call count. Three targets cost
    # twelve calls, one costs four.
    out, asked = run("echo 'gh pr merge 25' 'gh pr merge 25' 'gh pr merge 25'",
                     dirs["S"], None)
    calls = len(log.read_text().split())
    judge("three mentions of one PR", out, asked, ALLOW, ["sess/repo#25"])
    if calls > 4:
        failures.append("  three mentions of one PR cost %d gh calls, wanted 4"
                        % calls)

    # An honored override says so on stderr. An override nobody sees is an
    # override nobody reconsiders.
    out, asked = run("SKIP_REVIEW_GATE=1 gh pr merge 24", dirs["S"], None)
    judge("an honored override allows the merge", out, asked, ALLOW, [])
    if "review gate skipped" not in out.stderr:
        failures.append("  the honored override is not announced on stderr")
    shutil.rmtree(tmp, ignore_errors=True)
    return len(TARGET_CASES) + 3


def main() -> int:
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    failures = []

    # Detection has to fail fast on a long line of flag-shaped words. An earlier
    # pattern let one flag be read as the previous flag's value, which gives two
    # paths per word: 40 of them took about 15 seconds to come back empty, and a
    # PreToolUse hook that slow is a hung session.
    # getattr, because this file is also run against an older copy of the hook
    # to recount how many cases that copy fails, and 1.6.0 has no DETECT.
    slow = "gh pr merge " + " ".join("-f%d" % i for i in range(40)) + " end"
    started = time.time()
    if getattr(gate, "DETECT", None) is not None:
        gate.DETECT.search(slow)
    if time.time() - started > 2:
        failures.append("  detection took %.1fs on 40 flag-shaped words"
                        % (time.time() - started))

    for body, want, label in CASES:
        got = gate.has_verdict(body)
        if got != want:
            failures.append(f"  {label}: wanted {want}, got {got} for {body!r}")

    total = len(CASES) + run_target_cases(failures) + 1

    if failures:
        print(f"FAIL: {len(failures)} failures in {total} cases", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"ok: {total} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
