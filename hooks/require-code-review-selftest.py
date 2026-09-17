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
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write("%s#%s\n" % (repo, sel))
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
    # No number means the current branch's PR, in the target.
    ("cd {O} && gh pr merge --squash", BLOCK, ["other/repo#current"], "no number: current branch in the target"),
    ("gh pr merge 24 --squash 2>&1", BLOCK, ["sess/repo#24"], "a redirect is not a PR number"),
    # Gate 1 asks the target too.
    ("cd {O} && gh pr merge 26", BLOCK, ["other/repo#26"], "pending check in the target repo"),
    # A target that cannot be worked out blocks and asks for -R.
    ('cd "$SOMEWHERE" && gh pr merge 25', BLOCK, [], "cd to a variable: blocked, nothing guessed"),
    ("cd /no/such/dir/anywhere && gh pr merge 25", BLOCK, [], "cd to a missing directory"),
    ("cd - && gh pr merge 25", BLOCK, [], "cd -"),
    ('cd "$SOMEWHERE" && gh pr merge 24 -R flag/repo', ALLOW, ["flag/repo#24"],
     "an explicit -R makes an unknown cd irrelevant"),
    ('cd "$SOMEWHERE" && cd {O} && gh pr merge 24', ALLOW, ["other/repo#24"],
     "an absolute cd after an unknown one is known again"),
    # Text that mentions a merge is not a merge.
    ('git commit -m "then gh pr merge 24"', ALLOW, [], "a commit message mentioning a merge"),
    ("SKIP_REVIEW_GATE=1 gh pr merge 24", ALLOW, [], "the override still works"),
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
        if label.startswith(("cd to a", "cd -")) and "-R owner/repo" not in out.stderr:
            failures.append(f"  {label}: the block message does not ask for -R owner/repo")

    # The event's cwd is where the Bash tool's shell is now, and an earlier
    # call may have cd'd it away from the folder the hook process starts in.
    out, asked = run("gh pr merge 25", dirs["S"], dirs["O"])
    judge("the event's cwd beats the hook process's cwd", out, asked, BLOCK, ["other/repo#25"])
    # A block has to say which repo it looked in, or a wrong lookup is invisible.
    if "other" not in out.stderr:
        failures.append("  the block message does not name the target it asked about")
    shutil.rmtree(tmp, ignore_errors=True)
    return len(TARGET_CASES) + 1


def main() -> int:
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    failures = []
    for body, want, label in CASES:
        got = gate.has_verdict(body)
        if got != want:
            failures.append(f"  {label}: wanted {want}, got {got} for {body!r}")

    total = len(CASES) + run_target_cases(failures)

    if failures:
        print(f"FAIL: {len(failures)} failures in {total} cases", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"ok: {total} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
