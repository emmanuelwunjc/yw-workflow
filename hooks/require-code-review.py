#!/usr/bin/env python3
"""Block `gh pr merge` when nothing has code-reviewed the PR.

CLAUDE.md Section 2 step 3 requires the code-review skill on non-trivial
diffs before anything is called done. On 2026-08-04 that step was skipped on
22 of 26 PRs merged in one session. Nothing stopped it, because the rule was
prose. The four PRs that *were* reviewed each produced a real finding,
including a fix whose covering test did not exist while CI stayed green.

So this is the mechanism, per CLAUDE.md's own rule that a broken rule gets a
hook rather than a stronger sentence.

A PR counts as reviewed when either:
  - it has a GitHub review (APPROVED or CHANGES_REQUESTED), or
  - a comment on it carries a review verdict marker.

Trivial diffs are exempt: a PR touching no code file, or under the line
threshold, merges without ceremony. The point is to stop unreviewed
*behaviour* changes, not to add friction to a typo fix.

The PR is looked up in the repo the merge command targets, which is often a
different repo from the one the session started in: `cd <elsewhere> && gh pr
merge 24`, `-R owner/repo`, a PR URL, `GH_REPO=owner/repo`. When the target
cannot be read from the command text, the hook blocks and asks for an explicit
`-R owner/repo` instead of guessing. See merge_targets below.

Escape hatch: set SKIP_REVIEW_GATE=1 for the single command, as a real
assignment: a prefix on the merge, an `env` argument, or an `export` earlier in
the same command. The text appearing elsewhere (a --body, a comment) does not
count. That is deliberate and visible, unlike forgetting.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

# A verdict marker any of our review flows emit.
#
# Two patterns, not one alternation, and deliberately so.
#
# The bare uppercase markers stay case-SENSITIVE. Lower-casing them would let
# the word "blocked" in ordinary prose ("blocked on #123") satisfy the gate,
# which is a false pass on the exact check that is meant to be hard to pass by
# accident.
#
# `verdict:` is case-insensitive and carries NO trailing `\b`. The original
# pattern ended `|Verdict:)\b`, which never matched: `\b` needs a word
# character on one side, and a colon followed by a space has non-word
# characters on both. So it matched `Verdict:approve` and not
# `Verdict: approve`, and every review writes the second. The gate was
# unsatisfiable by its own documented marker, and the only way past it was
# SKIP_REVIEW_GATE=1. A safety gate that can only be passed by disabling it
# teaches you to disable it.
# Found 2026-08-05 merging synthweave #181, which had a posted review verdict.
# The third pattern is anchored to the start of a line, on purpose. Reviews
# very often open "**Approve with nits.**" and never write the word "verdict",
# so matching only `Verdict:` still reads a real review as no review. But
# matching "approve" anywhere would pass on "I approve of this direction",
# which is a false pass on the check that most needs to resist one. A verdict
# is stated up front; prose about approving is not. Leading `*`, `#` and `>`
# are skipped so bold, headings and quotes still count.
#
# `READY TO MERGE`/`DO-NOT-MERGE` were missing entirely until 2026-08-28, even
# though they are LOOP.md's and tools/loop_gate.py's own verdict words in
# any repo that adopts the LOOP.md convention, and this
# session's real reviewer comments used them verbatim. A same-shape gap to the
# `Verdict:` one above: this hook has its own separate vocabulary from the
# repo's `loop_gate.py`, so a comment that satisfies one satisfies neither
# automatically, and the only way past it was SKIP_REVIEW_GATE=1 again. Found
# 2026-08-28 merging two PRs in such a repo, both with a posted, real,
# independent-review-backed verdict this hook still could not see.
VERDICT_MARKERS = re.compile(
    r"\b(APPROVE|APPROVE_WITH_NITS|CHANGES_MADE|BLOCKED|READY TO MERGE|DO-NOT-MERGE)\b"
)
VERDICT_LINE = re.compile(r"verdict\s*:", re.IGNORECASE)
#
# `pass` and `block` were the fourth instance of the same vocabulary gap, found
# 2026-09-02 merging office-weather-bot #1 and #3. The fresh-eye skill tells its
# reviewers to open with exactly one word, `PASS`, `BLOCK` or `REVIEW`, and this
# hook knew none of them. Nine independent adversarial review rounds across two
# PRs, every verdict posted as a comment, and the gate still read them as no
# review, so the only way to merge was SKIP_REVIEW_GATE=1 three times in one
# session. A gate that a real review cannot satisfy trains you to disable it.
#
# They go in the line-anchored pattern, not the bare-marker one, for the reason
# that pattern already exists: `PASS` and `BLOCK` appear in ordinary prose about
# CI ("the check must PASS", "this will BLOCK the post") far too often to accept
# anywhere in a body. A verdict is stated up front.
#
# `review` is deliberately NOT here. In that skill it means "a human has to
# decide", which is the one verdict that must not satisfy a merge gate on its
# own, and "Review the diff" is a common way to open a comment.
VERDICT_OPENER = re.compile(
    r"^[\s*#>_]*(approve|approved|approve with nits|lgtm|request changes|"
    r"requesting changes|changes requested|blocking|ready to merge|do-not-merge|"
    r"pass|block)\b",
    re.IGNORECASE | re.MULTILINE,
)


def has_verdict(body: str) -> bool:
    return bool(
        VERDICT_MARKERS.search(body)
        or VERDICT_LINE.search(body)
        or VERDICT_OPENER.search(body)
    )
# Files whose change is behaviour, not prose.
CODE_SUFFIXES = (".py", ".yml", ".yaml", ".toml", ".cfg", ".sh", ".ts", ".js")
# Below this, a code diff is treated as trivial.
TRIVIAL_LINES = 25


# --- Which repo does the merge command target? ------------------------------
#
# Until 2026-09-17 every gh call here ran in the hook's own working directory,
# which is the folder the session started in. That day a session started in one
# repo ran `cd <a second repo> && gh pr merge 24 --squash`. The hook looked up
# PR 24 of the SESSION's repo, an old unreviewed PR, and blocked, although the
# second repo's PR 24 carried a posted "Verdict: PASS". The only way through was
# SKIP_REVIEW_GATE=1. The mirror is worse and was equally possible: the session
# repo's PR with that number is reviewed or trivial, so the hook passes the
# merge of an unreviewed PR somewhere else.
#
# The fix does not reimplement gh's repo resolution. It reads what steers it
# out of the command text (the directory the shell is in when gh runs, GH_REPO
# and GH_HOST assignments, -R/--repo, and the PR argument itself, which may be a
# URL) and hands the same to every gh call the hook makes. gh then applies its
# own precedence (URL, then -R, then GH_REPO, then the directory's git remote),
# so the hook asks about exactly the PR the merge would merge.
#
# THE RULE, from review round 1 of this change (2026-09-17, verdict BLOCK with
# three false passes, one of them a regression): a merge the hook can SEE but
# cannot read down to a fully literal target BLOCKS and asks for the literal
# form. Seeing a merge and passing it unchecked is the failure this hook exists
# to prevent. The three false passes were all that shape:
#   - `timeout 60 bash -c 'gh pr merge 24'`: the first version read a quoted
#     string as a command only when bash/sh/zsh/eval was the FIRST word. 1.6.0
#     had caught this one with its plain text match, so it was a regression.
#     Now every quoted string that holds a merge is read as a command, whatever
#     runs it, except where it is an argument of a command that only ever
#     treats it as data (DATA_COMMANDS, and gh itself).
#   - `gh pr merge $n`: the lookup failed, a failed lookup reads as a network
#     blip, and hook mode allows a blip. A PR, repo or host that is not literal
#     is now unreadable, which blocks.
#   - `gh -R o/r pr merge 25`: gh takes -R before the subcommand too. Both the
#     text prefilter and the word match wanted `pr` right after `gh`.
# And the walk ends with a fallback: text that matched the prefilter and
# produced no target blocks. New unknown shapes fail closed by construction.
#
# Deliberately NOT handled, because no text match can see them:
#   - `gh api -X PUT repos/o/r/pulls/N/merge`, which merges without `pr merge`
#   - a shell function, a shell alias, a `gh alias` or a gh extension that
#     wraps the merge
#   - a script file that runs the merge
#
# gh flags that take a value, so the value is never mistaken for the PR.
MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t",
                     "--subject", "-A", "--author-email", "--match-head-commit"}
# Words that can stand in front of a command without changing what it is.
# Without these, `{ cd /elsewhere; gh pr merge 5; }` hides its cd behind the `{`.
SHELL_PREFIXES = {"{", "}", "!", "then", "do", "else", "elif", "if", "while",
                  "until", "time", "command", "builtin", "exec"}
# Commands whose arguments are data and are never run. `git commit -m "then gh
# pr merge 24"` is a sentence. The installed 1.6.0 hook blocked this change's
# own commit over exactly that. gh is handled the same way for its QUOTED
# arguments (a --body), while its own words are still read as a command.
DATA_COMMANDS = {"echo", "printf", "git"}
# The cheap prefilter, run on text with quotes and line continuations removed,
# because the shell removes them before gh sees anything: `"gh" pr merge` and a
# backslash-newline between `pr` and `merge` are ordinary merges. Flags may sit
# between `gh` and `pr`.
MERGE_TEXT = re.compile(r"\bgh\s+(?:-\S+\s+(?:[^\s-]\S*\s+)?)*?pr\s+merge\b")
# Environment names copied from the command onto the hook's own gh calls, plus
# the override, which counts only as a real assignment (see merge_targets).
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
TRACKED_ENV = ("GH_REPO", "GH_HOST", "SKIP_REVIEW_GATE")
# What a literal looks like. Anything else (`$n`, `{}`, a backtick) is a value
# only the shell knows.
LITERAL_PR = re.compile(r"^(\d+|https?://[\w./:@-]+/pull/\d+\S*|[\w./@-]+)$")
LITERAL_REPO = re.compile(r"^[\w.-]+(/[\w.-]+){1,2}$|^https?://[\w./:@-]+$")
LITERAL_HOST = re.compile(r"^[\w.-]+(:\d+)?$")


def _plain(text: str) -> str:
    """Text as the prefilter should see it: no quotes, no line continuations."""
    return re.sub(r"[\"']", "", text.replace("\\\n", " "))


def _repo_flag(args: list, k: int):
    """If args[k] is a -R/--repo flag in any of gh's spellings, (value, words
    used). Otherwise (None, 0). `-R=o/r` is real: gh accepts it."""
    a = args[k]
    if a in ("-R", "--repo"):
        return (args[k + 1] if k + 1 < len(args) else ""), 2
    if a.startswith("--repo="):
        return a[len("--repo="):], 1
    if a.startswith("-R") and len(a) > 2:
        return a[2:].lstrip("="), 1
    return None, 0


def _cd(words: list, cwd):
    """Where `cd`/`pushd` with these arguments lands, or None when that cannot
    be known from the text alone: a variable, a glob, `cd -`, a bare `cd`, or a
    directory that does not exist (after `cd missing; gh ...` the shell is still
    in the old directory, after `cd missing && gh ...` gh never runs, and the
    hook cannot tell which it is looking at from one token)."""
    args = [w for w in words if w not in ("--", "-P", "-L", "-e", "-@")]
    if len(args) != 1 or args[0] == "-" or any(c in args[0] for c in "$`*?"):
        return None
    path = os.path.expanduser(args[0])
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    return path if os.path.isdir(path) else None


def _unreadable(why: str, pr=None) -> dict:
    return {"pr": pr, "repo": None, "env": {}, "cwd": None, "skip": False,
            "unreadable": why}


def merge_targets(cmd: str, cwd, env=None, cwd_why="") -> list:
    """Every `gh pr merge` in cmd, each with the context it would run in.

    Returns dicts with: pr (the PR argument as typed: a number, a URL, a branch,
    or None for the current branch), repo (-R/--repo), env (GH_REPO and GH_HOST
    as assigned in the command), cwd (the directory gh would run in, None when
    it cannot be known), skip (SKIP_REVIEW_GATE=1 was really assigned for this
    merge), unreadable (None, or a sentence saying what could not be read).

    ponytail: this walks shell words, it does not parse shell. Known ceilings:
    `popd` makes the directory unknown instead of tracking the stack, a cd
    inside `if`/`for` counts as taken, and a heredoc body is read as commands,
    so a merge line written into a file is judged as a merge (a false block
    1.6.0 had too). Each errs toward blocking, never toward a guess. Upgrade
    path is a real shell parser, and nothing measured so far justifies one.
    """
    env = dict(env or {})
    # `2>&1` would otherwise leave a bare "2" that reads as a PR number.
    text = re.sub(r"(?<=\s)\d+(?=[<>])", "", cmd.replace("\\\n", " "))
    # Backticks are a subshell. Written as `$(` and `)`, the walk below already
    # handles them: the inside is judged as a command, and used as an argument
    # it leaves a `$` behind, which is not a literal.
    ticks = iter(range(text.count("`")))
    text = re.sub("`", lambda _m: " $( " if next(ticks) % 2 == 0 else " ) ", text)
    # shlex treats a newline as plain whitespace, and a newline ends a command.
    lex = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""   # a `#` in a PR URL fragment or a body is not a comment
    try:
        tokens = list(lex)
    except ValueError:
        # The words cannot be trusted, so neither can a cd, a -R or an override
        # among them. The digits are kept for the message only.
        m = re.search(r"\bpr\s+merge\s+(\d+)", _plain(cmd))
        return [_unreadable("the command has unbalanced quotes, so its words "
                            "cannot be read", m.group(1) if m else None)]

    found, subshells, seg = [], [], []
    data_seen = switched = skip_next = False
    for tok in tokens + [";"]:
        if skip_next:                       # the file name after a redirect
            skip_next = False
            continue
        if not all(c in "();<>|&" for c in tok):
            seg.append(tok)
            continue
        if "<" in tok or ">" in tok:
            skip_next = True
            continue

        # --- one simple command is complete: judge it -----------------------
        raw, seg = seg, []
        words = list(raw)
        while words and (words[0] in SHELL_PREFIXES or ASSIGNMENT.match(words[0])):
            words.pop(0)
        name = os.path.basename(words[0]) if words else ""
        mentions = bool(MERGE_TEXT.search(" ".join(raw)))
        here = []

        if name in ("cd", "pushd", "popd"):
            cwd = _cd(words[1:], cwd) if name != "popd" else None
            cwd_why = ("`%s` leaves the shell in a directory that cannot be "
                       "read from the command text" % " ".join(words))
        elif name == "export":
            for w in words[1:]:
                key, _, value = w.partition("=")
                if key in TRACKED_ENV:
                    env[key] = value
        if "checkout" in words or "switch" in words:
            switched = True   # git switch, git checkout, gh pr checkout

        if name in DATA_COMMANDS:
            data_seen = data_seen or mentions
        else:
            # The merge itself, judged where the shell is standing right now.
            # `gh` is looked for anywhere in the words, so that `timeout 60 gh`,
            # `env X=1 gh`, `xargs gh` and `watch gh` are all seen.
            for j, w in enumerate(raw):
                if os.path.basename(w) != "gh":
                    continue
                target = {"pr": None, "repo": None, "cwd": cwd, "unreadable": None}
                k = j + 1                    # gh's own flags, before the subcommand
                while k < len(raw) and raw[k].startswith("-"):
                    repo, used = _repo_flag(raw, k)
                    if used:
                        target["repo"] = repo
                    k += used or 1
                if raw[k:k + 2] != ["pr", "merge"]:
                    continue
                args = raw[k + 2:]
                k = 0
                while k < len(args):
                    repo, used = _repo_flag(args, k)
                    if used:
                        target["repo"] = repo
                    elif not args[k].startswith("-") and target["pr"] is None:
                        target["pr"] = args[k]
                    k += used or (2 if args[k] in MERGE_VALUE_FLAGS else 1)
                # Assignments in front of gh: a prefix, or arguments of `env`.
                scoped = dict(env)
                for w2 in raw[:j]:
                    key, _, value = w2.partition("=")
                    if key in TRACKED_ENV:
                        scoped[key] = value
                target["skip"] = scoped.pop("SKIP_REVIEW_GATE", "") == "1"
                target["env"] = scoped
                here.append(target)

            # A quoted string holding a merge is a command line for whatever
            # runs it (bash -c, sudo sh -c, ssh, eval, watch). gh's own quoted
            # arguments are the exception: a --body is data.
            for w in raw:
                if name != "gh" and re.search(r"\s", w) and MERGE_TEXT.search(_plain(w)):
                    here += merge_targets(w, cwd, env, cwd_why)
            # For gh, only its own words can be a merge. A mention that sits
            # wholly inside a quoted argument is data.
            bare = MERGE_TEXT.search(" ".join(w for w in raw if not re.search(r"\s", w)))
            if name == "gh" and mentions and not bare:
                data_seen = True

            # Fail closed: this command mentions a merge and none was read.
            if mentions and not here and (name != "gh" or bare):
                here.append(_unreadable(
                    "`%s` holds a merge in a form that cannot be read" % " ".join(raw)))

        for target in here:
            if target["unreadable"]:
                pass
            elif target["pr"] is not None and not LITERAL_PR.match(target["pr"]):
                target["unreadable"] = ("the PR is written as `%s`, which is not a "
                                        "literal number, URL or branch" % target["pr"])
            elif target["repo"] is not None and not LITERAL_REPO.match(target["repo"]):
                target["unreadable"] = ("the repo is written as `%s`, which is not "
                                        "a literal owner/repo" % target["repo"])
            elif "GH_REPO" in target["env"] and not LITERAL_REPO.match(target["env"]["GH_REPO"]):
                target["unreadable"] = ("GH_REPO is set to `%s`, which is not a "
                                        "literal owner/repo" % target["env"]["GH_REPO"])
            elif "GH_HOST" in target["env"] and not LITERAL_HOST.match(target["env"]["GH_HOST"]):
                target["unreadable"] = ("GH_HOST is set to `%s`, which is not a "
                                        "literal host" % target["env"]["GH_HOST"])
            elif target["pr"] is None and switched:
                # "The current branch" is read now, and the command changes the
                # branch before the merge runs.
                target["unreadable"] = ("the merge names no PR, and a `git switch`, "
                                        "`git checkout` or `gh pr checkout` earlier "
                                        "in the command changes which branch that means")
            elif not target_known(target):
                target["unreadable"] = cwd_why or "the directory it runs in is unknown"
        found += here

        # A subshell's cd ends with the subshell. Per character, because shlex
        # hands back a run of punctuation such as `);` as one token.
        for c in tok:
            if c == "(":
                subshells.append(cwd)
            elif c == ")" and subshells:
                cwd = subshells.pop()

    # The fallback that makes unknown shapes fail closed: the prefilter saw a
    # merge, and the walk neither read one nor put it down to data.
    if not found and not data_seen and MERGE_TEXT.search(_plain(cmd)):
        found.append(_unreadable("the command holds a merge in a form that "
                                 "cannot be read"))
    return found


def target_known(target: dict) -> bool:
    """Can gh be pointed at the same repo the merge will hit? Yes when anything
    names the repo outright, or when the directory gh would run in is known."""
    return bool(
        target["cwd"] or target["repo"] or target["env"].get("GH_REPO")
        or os.environ.get("GH_REPO")
        or re.match(r"https?://", target["pr"] or "")
    )


def describe(target: dict) -> str:
    """The PR and where the hook looked for it. A block that does not say which
    repo it asked is how a wrong-repo lookup stayed invisible until 2026-09-17."""
    pr = target["pr"]
    if re.match(r"https?://", pr or ""):
        return pr
    name = ("PR #" + pr) if (pr or "").isdigit() else (
        "the PR for branch " + pr if pr else "the current branch's PR")
    where = (target["repo"] or target["env"].get("GH_REPO")
             or os.environ.get("GH_REPO") or target["cwd"])
    return f"{name} in {where}"


def gh(sub: str, target: dict, *args: str) -> str:
    """Run `gh pr <sub>` against the merge's own target: same PR argument, same
    -R, same GH_REPO and GH_HOST, same directory. See the block comment above."""
    argv = ["gh", "pr", sub]
    if target["pr"]:
        argv.append(target["pr"])
    if target["repo"]:
        argv += ["-R", target["repo"]]
    try:
        out = subprocess.run(
            argv + list(args), capture_output=True, text=True, timeout=25,
            cwd=target["cwd"], env=dict(os.environ, **target["env"]),
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def review_status(target: dict):
    """Gate 2 as a query: has anything reviewed the PR this target names?

    Returns (verdict, code_lines) where verdict is one of:
      "ok"        nothing to stop: trivial, docs-only, or already reviewed
      "unreviewed" a non-trivial code diff with no review and no verdict comment
      "unknown"   the gh lookup came back empty, so the question is unanswered

    The hook treats "unknown" as ok, because a network blip must not wedge a
    local merge. CI treats it as a failure: a check that cannot see the PR has
    proved nothing, and passing on it is how a required gate becomes a rubber
    stamp.
    """
    files = gh("view", target, "--json", "files",
               "--jq", ".files[] | \"\\(.path) \\(.additions) \\(.deletions)\"")
    if not files.strip():
        return "unknown", 0

    code_lines = 0
    for line in files.strip().splitlines():
        parts = line.rsplit(" ", 2)
        if len(parts) != 3:
            continue
        path, add, dele = parts
        if path.endswith(CODE_SUFFIXES):
            try:
                code_lines += int(add) + int(dele)
            except ValueError:
                pass

    if code_lines == 0:
        return "ok", 0            # docs or data only
    if code_lines < TRIVIAL_LINES:
        return "ok", code_lines   # trivial code change

    states = gh("view", target, "--json", "reviews",
                "--jq", "[.reviews[].state] | join(\" \")")
    if "APPROVED" in states or "CHANGES_REQUESTED" in states:
        return "ok", code_lines

    body = gh("view", target, "--json", "comments", "--jq", ".comments[].body")
    if has_verdict(body or ""):
        return "ok", code_lines

    return "unreviewed", code_lines


def check_pr(pr: str) -> int:
    """CI mode: fail the job when PR #pr carries an unreviewed code diff.

    Gate 1 (every check green) is deliberately NOT run here. In CI this check is
    itself one of those checks, so asking whether all checks are green would
    always find this one in progress and fail every time.
    """
    # CI names its repo through GH_REPO in the job's environment (see the guards
    # action), which gh reads by itself. cwd None means "wherever the job runs".
    verdict, code_lines = review_status(
        {"pr": pr, "repo": None, "env": {}, "cwd": None})
    if verdict == "ok":
        return 0
    if verdict == "unknown":
        print(
            "BLOCKED: could not read PR #%s from the GitHub API, so whether it "
            "was reviewed is unknown. Check the job's token permissions "
            "(pull-requests: read)." % pr,
            file=sys.stderr,
        )
        return 1
    print(
        "BLOCKED: PR #%s changes %d lines of code and nothing has reviewed it.\n"
        "Green CI proves the tests pass. It does not prove the change matches "
        "its issue, and it does not catch a bad design decision.\n"
        "Approve it on GitHub, or post a review verdict as a PR comment."
        % (pr, code_lines),
        file=sys.stderr,
    )
    return 1


def deny(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    # check-pr takes a PR number on argv and never reads stdin. The mode is
    # matched on its own, before the argument count: falling through to the hook
    # path on a missing number reads an empty stdin and exits 0, so a broken
    # invocation would look like a pass.
    if len(sys.argv) > 1 and sys.argv[1] == "check-pr":
        if len(sys.argv) < 3:
            print("usage: require-code-review.py check-pr <pr-number>",
                  file=sys.stderr)
            sys.exit(1)
        sys.exit(check_pr(sys.argv[2]))

    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (event.get("tool_input") or {}).get("command", "")

    if not MERGE_TEXT.search(_plain(cmd)):
        sys.exit(0)
    # The override in the hook's own environment covers the session. Written in
    # the command, it counts only as a real assignment for the merge it fronts
    # (a prefix, an `env` argument, an earlier `export`), which merge_targets
    # reads. Until 2026-09-17 the text anywhere in the command was enough, so
    # `--body "SKIP_REVIEW_GATE=1"` or a trailing comment switched the gate off
    # without the shell ever setting anything.
    if os.environ.get("SKIP_REVIEW_GATE") == "1":
        sys.exit(0)

    # The event's cwd is where the Bash tool's shell stands now. An earlier call
    # may have cd'd it away from the folder this process was started in.
    start = event.get("cwd") or os.getcwd()
    # Every merge in the command is judged, each against its own target. The
    # first one that fails blocks the whole command, because the command runs
    # as a whole or not at all.
    for target in merge_targets(cmd, start):
        check_merge(target)
    sys.exit(0)


def check_merge(target: dict) -> None:
    """Both gates for one `gh pr merge`. Returns when it may go ahead."""
    if target["skip"]:
        return

    # --- Gate 0: the target has to be readable ------------------------------
    # Added 2026-09-17. `cd "$DIR" && gh pr merge 24` names a PR in a repo the
    # hook cannot see from the text, and `gh pr merge $n` names a PR it cannot
    # see at all. It must not fall back to the session's repo: that is the
    # defect this gate exists for, and it fails in both directions. It also must
    # not pass the way a failed lookup does below. A failed lookup is a network
    # blip, it is transient, and nothing the caller types will fix it. An
    # unreadable target is permanent for that command and costs one literal to
    # fix. A gate that waves through what it cannot see is a rubber stamp, so
    # this one blocks, says what it could not read, and says what to type.
    if target["unreadable"]:
        deny(
            f"BLOCKED: this command runs `gh pr merge` and the review check "
            f"cannot tell which PR in which repo it means: "
            f"{target['unreadable']}.\n\n"
            f"Looking up a guess would check the wrong PR, so write the merge "
            f"with literal values, one command per PR:\n"
            f"  gh pr merge {target['pr'] if (target['pr'] or '').isdigit() else '<number>'}"
            f" -R owner/repo ...\n\n"
            f"Deliberate override, as a prefix on the merge itself: "
            f"SKIP_REVIEW_GATE=1 gh pr merge ...\n"
        )

    pr = target["pr"] or ""
    label = describe(target)

    # --- Gate 1: every check must be passing -------------------------------
    # Added 2026-08-04. The review gate below is not enough on its own: a PR
    # can be reviewed and still be red, or still have a check pending that
    # nobody waited for. "100% green" means zero failing AND zero pending, not
    # "green apart from the one we know about".
    #
    # This runs BEFORE the triviality check on purpose. A one-line change that
    # turns CI red is exactly the merge worth stopping, and skipping the gate
    # for small diffs would let the most common red slip through.
    checks = gh("checks", target, "--json", "name,state",
                "--jq", '.[] | "\\(.state) \\(.name)"')
    if checks.strip():
        bad = []
        for line in checks.strip().splitlines():
            state, _, name = line.partition(" ")
            if state.upper() not in ("SUCCESS", "SKIPPED", "NEUTRAL"):
                bad.append(f"  {state.lower():<12} {name}")
        if bad:
            deny(
                f"BLOCKED: {label} is not 100% green.\n\n"
                + "\n".join(bad)
                + "\n\nA pending check is not a passing check: wait for it "
                "rather than merging past it.\n"
                f"  gh pr checks {pr} --watch\n\n"
                f"Deliberate override: SKIP_REVIEW_GATE=1 gh pr merge {pr} ...\n"
            )

    # --- Gate 2: a code review must have run -------------------------------
    verdict, code_lines = review_status(target)
    if verdict in ("ok", "unknown"):
        return  # "unknown" = broken lookup; the hook does not block on one

    deny(
        f"BLOCKED: {label} changes {code_lines} lines of code and nothing has "
        f"reviewed it.\n\n"
        f"CLAUDE.md Section 2 step 3: run the code-review skill on non-trivial "
        f"diffs before calling anything done. Green CI proves the tests pass. "
        f"It does not prove the change matches its issue, and it does not catch "
        f"a bad design decision.\n\n"
        f"Do one of:\n"
        f"  1. Run an independent code-review on it, post the verdict as a PR "
        f"comment, then merge.\n"
        f"  2. Approve it on GitHub if a human read it.\n"
        f"  3. SKIP_REVIEW_GATE=1 gh pr merge {pr} ...  (deliberate, and it shows)\n"
    )


if __name__ == "__main__":
    main()
