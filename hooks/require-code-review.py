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
`-R owner/repo` instead of guessing. See the two-jobs comment below.

Escape hatch: SKIP_REVIEW_GATE=1, as a real assignment. In the hook's own
environment it covers the session. In the command it counts as a prefix on the
merge, an `env` argument, or an `export` earlier in the same command. The text
appearing elsewhere (inside a --body, in a trailing comment) does not count.
When it is honored the hook says so on stderr, so a skipped gate is visible
after the fact rather than only in the shell history.
"""

from __future__ import annotations

import collections
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


# --- Two jobs, kept apart ---------------------------------------------------
#
# DETECTION decides whether a command holds a merge, and of which PR. It is a
# text pattern run over the raw command, and it is 1.6.0's pattern. That is
# crude on purpose: it never asks what runs the text, so it sees a merge inside
# `bash -c`, inside `$( )`, piped to `sh`, handed to `git rebase --exec`. Its
# price is known and unchanged: a command that only MENTIONS `gh pr merge 24`
# is judged as if it merged PR 24. Quoting is what usually saves an ordinary
# command, because the pattern needs whitespace and a number right after
# `merge`, so `grep -rn "gh pr merge" hooks/` never matches.
#
# TARGET RESOLUTION decides which repo to ask about each merge detection found.
# That is the only job of the word walk below.
#
# The history, because the split was learned the hard way. Until 2026-09-17
# every gh call here ran in the hook's own working directory, the folder the
# session started in. That day a session started in one repo ran `cd <a second
# repo> && gh pr merge 24 --squash`. The hook looked up PR 24 of the SESSION's
# repo, an old unreviewed PR, and blocked, although the second repo's PR 24
# carried a posted "Verdict: PASS". The mirror is worse: when the session
# repo's PR with that number is reviewed, the hook passes an unreviewed merge
# somewhere else. The defect was WHICH REPO gets asked. It was never WHETHER a
# merge is seen.
#
# The first two attempts at the fix replaced detection with the word walk.
# Review round 1 found three false passes. The rewrite that answered them was
# reviewed again and round 2 found four more: merges 1.6.0 caught now passed
# (`echo "out: $(gh pr merge 24)"`, `echo '<merge>' | sh`, `git rebase --exec`),
# and read-only commands 1.6.0 allowed now blocked (23 of 48 realistic non-merge
# commands, against 11 for 1.6.0). Blocking findings went 3, then 4. A word walk
# that has to decide what is and is not a merge is a shell parser, and each
# exception added to it opened the next hole. So detection went back to the text
# pattern and the walk answers one question about merges the pattern found.
#
# Three additions to 1.6.0's pattern, each measured against those 48 commands
# for new false blocks (none, 22 of 48 match either way):
#   - `-R`/`--repo` between `gh` and `pr`, which gh accepts
#   - flags between `merge` and the number (`gh pr merge --squash 24`), with a
#     value flag's value skipped so it is never read as the number
#   - a PR URL in place of the number, and a backslash-newline read as the
#     space the shell makes of it
#
# Deliberately NOT handled, as in 1.6.0, because a text pattern cannot see them:
#   - a merge with no number at all (`gh pr merge --squash`, the current branch)
#   - a variable or a command substitution as the number (`gh pr merge $PR`,
#     `gh pr merge $(cat n)`), and `xargs gh pr merge` fed numbers on stdin
#   - `gh api -X PUT repos/o/r/pulls/N/merge`, which merges without `pr merge`
#   - quoting or a variable that spells the words (`"gh" pr merge`, `$G pr
#     merge`), a shell function, an alias, a `gh alias`, a gh extension
#   - a script file, or a subprocess argv list, that runs the merge
# The first, second and fourth are emmanuelwunjc/yw-workflow#17, with a
# reproduction and the false-block numbers any fix has to beat.
#
# The number must not run into another token, so `gh pr merge --squash 2>&1`
# does not read the redirect's `2` as PR 2.
# A flag's value cannot itself start with `-`. Without that, one flag can be
# read as the previous flag's value, the pattern has two paths per word, and a
# line of 40 flag-shaped words takes exponential time to fail.
_SKIP_FLAGS = r"(?:-[\w-]+(?:=[^\s;|&]+)?[ \t]+(?:[\w./:@][^\s;|&]*[ \t]+)?)*"
DETECT = re.compile(
    r"\bgh\s+" + _SKIP_FLAGS + r"pr\s+merge\s+" + _SKIP_FLAGS
    + r"(\d+(?![\w<>=/.-])|https?://\S+?/pull/\d+)"
)
# When the walk reads no merge at all, these in the text mean the merge may be
# aimed somewhere other than the session's repo, so the session's repo is no
# longer a safe answer.
REDIRECT_HINT = re.compile(
    r"\b(?:cd|pushd|popd)\b|(?:^|\s)(?:-R|--repo)|\bGH_REPO\b|\bGH_HOST\b|https?://")
# gh flags that take a value, so the value is never mistaken for the PR.
MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t",
                     "--subject", "-A", "--author-email", "--match-head-commit"}
# Words that can stand in front of a command without changing what it is.
# Without these, `{ cd /elsewhere; gh pr merge 5; }` hides its cd behind the `{`.
SHELL_PREFIXES = {"{", "}", "!", "then", "do", "else", "elif", "if", "while",
                  "until", "time", "command", "builtin", "exec"}
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
# Environment names copied from the command onto the hook's own gh calls, plus
# the override, which counts only as a real assignment.
TRACKED_ENV = ("GH_REPO", "GH_HOST", "SKIP_REVIEW_GATE")
OVERRIDE = "SKIP_REVIEW_GATE=1"
# The override in front of the whole command, the one spelling every block
# message gives, for the case where the words cannot be walked at all.
OVERRIDE_PREFIX = re.compile(r"^\s*(?:export\s+)?%s\b" % re.escape(OVERRIDE))
# What a literal looks like. Anything else (`$n`, `{}`, a backtick) is a value
# only the shell knows.
LITERAL_PR = re.compile(r"^(\d+|https?://[\w./:@-]+/pull/\d+\S*)$")
LITERAL_REPO = re.compile(r"^[\w.-]+(/[\w.-]+){1,2}$|^https?://[\w./:@-]+$")
LITERAL_HOST = re.compile(r"^[\w.-]+(:\d+)?$")


def _join_lines(cmd: str) -> str:
    """The shell removes a backslash-newline before anything sees the words."""
    return cmd.replace("\\\n", " ")


def _pr_key(pr: str) -> str:
    """One PR, however it was written. `.../pull/24` and `24` are the same PR
    for the purpose of counting what detection saw against what the walk read."""
    m = re.search(r"/pull/(\d+)", pr or "")
    return m.group(1) if m else (pr or "")


def _target(pr=None, repo=None, env=None, cwd=None, skip=False, unreadable=None):
    return {"pr": pr, "repo": repo, "env": dict(env or {}), "cwd": cwd,
            "skip": skip, "unreadable": unreadable}


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
    be known from the text alone.

    A path that does not exist is NOT unknown, it is unchanged. The `cd` fails,
    so with `;` the shell is still in the old directory, and with `&&` the merge
    never runs at all. Both answers are the old directory. Treating it as
    unknown instead cost a false block on ordinary text, e.g. a heredoc writing
    `cd other && gh pr merge 25` into a file. The ceiling: a directory this same
    command creates first (`git clone x && cd x && gh pr merge 25`) is judged in
    the old directory, which is 1.6.0's answer rather than a new hole.

    A variable, a glob, `cd -` and a bare `cd` are genuinely unknown, and those
    block.
    """
    args = [w for w in words if w not in ("--", "-P", "-L", "-e", "-@")]
    if len(args) != 1 or args[0] == "-" or any(c in args[0] for c in "$`*?"):
        return None
    path = os.path.expanduser(args[0])
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    return path if os.path.isdir(path) else cwd


def _blind(text: str, cwd, skip: bool) -> list:
    """Targets for the merges detection sees in text whose words cannot be read.

    1.6.0's answer stands, the directory the session is in, unless something in
    the text could aim the merge somewhere else, or a shell expansion is spliced
    onto the PR number.
    """
    hint = REDIRECT_HINT.search(text)
    out = []
    for m in DETECT.finditer(text):
        why = None
        if text[m.end():m.end() + 1] in ("$", "`"):
            why = ("the PR number runs into a shell expansion, so which PR is "
                   "meant is decided at run time")
        elif hint:
            why = ("the command's words cannot be read, and `%s` in it may aim "
                   "the merge at another repo" % hint.group(0).strip())
        out.append(_target(pr=m.group(1), cwd=cwd, skip=skip, unreadable=why))
    return out


def walk_targets(cmd: str, cwd, env=None, cwd_why="") -> list:
    """For each `gh pr merge` the words of cmd spell out, the context it would
    run in. Detection is NOT this function's job: see the comment above.

    Returns dicts with: pr (as typed), repo (-R/--repo, on either side of `pr
    merge`), env (GH_REPO and GH_HOST as assigned in the command), cwd (the
    directory gh would run in, None when that cannot be known), skip (the
    override was really assigned for this merge), unreadable (None, or a
    sentence saying what could not be read). Raises ValueError on unbalanced
    quotes.

    A merge with no PR argument yields no target, because detection cannot see
    one either, and a target detection never counted would be counted as
    missing further down.

    ponytail: this walks shell words, it does not parse shell. `popd` makes the
    directory unknown rather than tracking the stack, and a cd inside `if`/`for`
    counts as taken. Both err toward blocking. The upgrade path is a real shell
    parser, and two review rounds say to stay away from one.
    """
    env = dict(env or {})
    # `2>&1` would otherwise leave a bare "2" among the words.
    text = re.sub(r"(?<=\s)\d+(?=[<>])", "", _join_lines(cmd))
    # Backticks are a subshell. Written as `$(` and `)`, the walk handles them.
    ticks = iter(range(text.count("`")))
    text = re.sub("`", lambda _m: " $( " if next(ticks) % 2 == 0 else " ) ", text)
    # shlex treats a newline as plain whitespace, and a newline ends a command.
    lex = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""   # a `#` in a PR URL fragment or a body is not a comment
    tokens = list(lex)

    found, subshells, seg = [], [], []
    skip_next = False
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

        # --- one simple command is complete ---------------------------------
        raw, seg = seg, []
        words = list(raw)
        while words and (words[0] in SHELL_PREFIXES or ASSIGNMENT.match(words[0])):
            words.pop(0)
        name = os.path.basename(words[0]) if words else ""

        if name in ("cd", "pushd", "popd"):
            cwd = _cd(words[1:], cwd) if name != "popd" else None
            cwd_why = ("`%s` leaves the shell in a directory that cannot be "
                       "read from the command text" % " ".join(words))
        elif name == "export":
            for w in words[1:]:
                key, _, value = w.partition("=")
                if key in TRACKED_ENV:
                    env[key] = value

        here = []
        # `gh` is looked for anywhere in the words, so that `timeout 60 gh`,
        # `env X=1 gh`, `xargs gh` and `watch gh` are all tied to a target.
        for j, w in enumerate(raw):
            if os.path.basename(w) != "gh":
                continue
            target = _target(cwd=cwd)
            k = j + 1                        # gh's own flags, before the subcommand
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
            if target["pr"] is None:
                continue                     # numberless: detection cannot see it
            # posix shlex glues an adjacent quoted and bare run into one word,
            # so a merge written inside a data structure arrives as `25]]` from
            # `[["x", "gh pr merge 25"]]`. Trailing punctuation is that glue and
            # comes off. A `$` or a backtick is not glue, it is a value only the
            # shell knows, so it stays and the target reads as unreadable.
            target["pr"] = re.sub(r"[^\w$`/.:@-]+$", "", target["pr"])
            # Assignments in front of gh: a prefix, or arguments of `env`.
            scoped = dict(env)
            for w2 in raw[:j]:
                key, _, value = w2.partition("=")
                if key in TRACKED_ENV:
                    scoped[key] = value
            target["skip"] = scoped.pop("SKIP_REVIEW_GATE", "") == "1"
            target["env"] = scoped
            if any(os.path.basename(w2) == "xargs" for w2 in raw[:j]):
                target["unreadable"] = ("`xargs` adds arguments to the merge "
                                        "that the command text does not show")
            here.append(target)

        # A quoted string holding a merge is walked the same way, whatever it is
        # an argument of: `bash -c '...'`, `echo '<merge>' | sh`, `git rebase
        # --exec`, a commit message. Whether it counts as a merge was
        # detection's call, and detection already said yes.
        for w in raw:
            if re.search(r"\s", w) and DETECT.search(_join_lines(w)):
                try:
                    here += walk_targets(w, cwd, env, cwd_why)
                except ValueError:       # prose with an apostrophe, most often
                    here += _blind(_join_lines(w), cwd,
                                   env.get("SKIP_REVIEW_GATE") == "1")

        for target in here:
            if target["unreadable"]:
                pass
            elif not LITERAL_PR.match(target["pr"]):
                target["unreadable"] = ("the PR is written as `%s`, which is not "
                                        "a literal number or URL" % target["pr"])
            elif target["repo"] is not None and not LITERAL_REPO.match(target["repo"]):
                target["unreadable"] = ("the repo is written as `%s`, which is not "
                                        "a literal owner/repo" % target["repo"])
            elif "GH_REPO" in target["env"] and not LITERAL_REPO.match(target["env"]["GH_REPO"]):
                target["unreadable"] = ("GH_REPO is set to `%s`, which is not a "
                                        "literal owner/repo" % target["env"]["GH_REPO"])
            elif "GH_HOST" in target["env"] and not LITERAL_HOST.match(target["env"]["GH_HOST"]):
                target["unreadable"] = ("GH_HOST is set to `%s`, which is not a "
                                        "literal host" % target["env"]["GH_HOST"])
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
    return found


def merge_targets(cmd: str, start, hook_skip: bool) -> list:
    """Detection, then a target for every merge it found.

    The rule: a detected merge that cannot be tied to a fully literal target
    blocks. If the walk ties fewer merges than detection found, that blocks too,
    because the ones it did not tie are the ones nobody checked. If the walk
    reads no merge at all, 1.6.0's answer stands, the session's own repo, unless
    the text could aim the merge elsewhere.
    """
    text = _join_lines(cmd)
    detected = collections.Counter(_pr_key(m.group(1)) for m in DETECT.finditer(text))
    if not detected:
        return []
    try:
        walked = walk_targets(cmd, start, {"SKIP_REVIEW_GATE": "1"} if hook_skip else None)
    except ValueError:
        walked = []
    if not walked:
        return _blind(text, start, hook_skip or bool(OVERRIDE_PREFIX.match(cmd)))
    missing = detected - collections.Counter(_pr_key(t["pr"]) for t in walked)
    for pr in sorted(missing.elements()):
        walked.append(_target(
            pr=pr, skip=hook_skip,
            unreadable="the text holds a merge of %s that could not be tied to "
                       "a command" % pr))
    return walked


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
    where = (target["repo"] or target["env"].get("GH_REPO")
             or os.environ.get("GH_REPO") or target["cwd"])
    return f"PR #{pr} in {where}"


def gh(sub: str, target: dict, *args: str) -> str:
    """Run `gh pr <sub>` against the merge's own target: same PR argument, same
    -R, same GH_REPO and GH_HOST, same directory. See the block comment above."""
    argv = ["gh", "pr", sub, target["pr"]]
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
    verdict, code_lines = review_status(_target(pr=pr))
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


# Every block message ends with this. `export ...;` in front of the whole
# command works for any command, including one that only mentions a merge and
# runs none, which a prefix on `gh pr merge` cannot do.
OVERRIDE_HELP = (
    "Deliberate override, and it shows: put `export SKIP_REVIEW_GATE=1;` in "
    "front of the whole command.\n"
    "If the command only mentions a merge and runs none, that works too, or "
    "break the text, e.g. grep 'gh pr [m]erge'.\n"
)


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

    if not DETECT.search(_join_lines(cmd)):
        sys.exit(0)
    # The event's cwd is where the Bash tool's shell stands now. An earlier call
    # may have cd'd it away from the folder this process was started in.
    start = event.get("cwd") or os.getcwd()
    # Every merge in the command is judged, each against its own target. The
    # first one that fails blocks the whole command, because the command runs
    # as a whole or not at all.
    hook_skip = os.environ.get("SKIP_REVIEW_GATE") == "1"
    for target in merge_targets(cmd, start, hook_skip):
        check_merge(target)
    sys.exit(0)


def check_merge(target: dict) -> None:
    """Both gates for one `gh pr merge`. Returns when it may go ahead."""
    if target["skip"]:
        # Said out loud, because an override nobody sees is an override nobody
        # reconsiders. Until 2026-09-17 the text SKIP_REVIEW_GATE=1 anywhere in
        # the command was enough, so a --body or a trailing comment holding those
        # words switched the gate off without the shell ever setting anything.
        print("review gate skipped: SKIP_REVIEW_GATE=1 is set for the merge of "
              "PR %s" % target["pr"], file=sys.stderr)
        return

    # --- Gate 0: the target has to be readable ------------------------------
    # Added 2026-09-17. `cd "$DIR" && gh pr merge 24` names a PR in a repo the
    # hook cannot see from the text. It must not fall back to the session's
    # repo: that is the defect this gate exists for, and it fails in both
    # directions. It also must not pass the way a failed lookup does below. A
    # failed lookup is a network blip, it is transient, and nothing the caller
    # types will fix it. An unreadable target is permanent for that command and
    # costs one literal to fix. A gate that waves through what it cannot see is
    # a rubber stamp, so this one blocks, says what it could not read, and says
    # what to type.
    if target["unreadable"]:
        deny(
            f"BLOCKED: this command runs `gh pr merge` and the review check "
            f"cannot tell which PR in which repo it means: "
            f"{target['unreadable']}.\n\n"
            f"Looking up a guess would check the wrong PR, so write the merge "
            f"with literal values, one command per PR:\n"
            f"  gh pr merge {target['pr'] if (target['pr'] or '').isdigit() else '<number>'}"
            f" -R owner/repo ...\n\n" + OVERRIDE_HELP
        )

    pr = target["pr"]
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
                f"  gh pr checks {pr} --watch\n\n" + OVERRIDE_HELP
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
        f"  3. " + OVERRIDE_HELP
    )


if __name__ == "__main__":
    main()
