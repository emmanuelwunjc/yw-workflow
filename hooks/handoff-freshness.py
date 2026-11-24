#!/usr/bin/env python3
"""Warn when a session commits real work and never touches docs/HANDOFF.md.

CLAUDE.md Section 6 says the handoff is written down AS WORK HAPPENS. An
end-of-session handoff is composed from a compacted, lossy memory of the
session, and the reasoning that mattered (why an alternative was rejected, what
trap cost an hour) is exactly what drops out first.

Where it is written depends on the branch. The owner decided on 2026-09-21
that only a handoff branch edits docs/HANDOFF.md, because every concurrent
branch that appended to it hit a merge conflict there. Any other branch writes
its notes in a
"## Handoff notes" section of its PR body. After merges, one handoff pass on a
docs/handoff-* branch copies those notes into the log.

That rule was prose. On 2026-08-05 a session merged five PRs, filed sixteen
issues and made a dozen judgment calls before anyone asked whether a handoff
existed. It did not. So this is the mechanism, per CLAUDE.md's own rule that a
broken rule gets a hook rather than a stronger sentence.

WARNS, and never holds a session back for good. Some sessions legitimately
commit nothing worth handing off (a one-line typo fix, a revert). At Stop the
warnings go out as Stop hookSpecificOutput.additionalContext JSON on stdout,
once per session per warning variant, through handoff_sent.py (issue #125).
The full rule, and why, is in docs/DECISIONS.md, 2026-11-16.

Fires on Stop, in a git repo. What it checks depends on the branch.

Trunk is main, master, and whatever refs/remotes/origin/HEAD names if that
ref exists. A work branch is any other branch, and a detached HEAD too. A
work branch is judged by its net diff from a base, never by its commits one
at a time, so a branch that reverts a handoff edit is clean again:
  - named branch: base is the merge-base with the closest trunk ref (origin/
    or local, whichever is nearer HEAD)
  - detached HEAD (a reviewer worktree, by design): only commits on no
    branch and no remote are its own; base is the parent of the oldest
  - no base (a shallow clone, no trunk ref): the hook says nothing
There is no time window for work branches.

A named work branch whose diff changes real files gets HANDOFF NOTES: put the notes
in the PR body's "## Handoff notes" section. A branch has edited the handoff
only when its copy differs from the copy in every trunk ref (a detached HEAD:
from its base), because the closest base can be a local trunk that diverged
from origin. A stale trunk ref, one whose merge-base with HEAD is an ancestor
of another's, is left out, since matching it would delete the newer passes.
Such a branch is told that only a handoff branch edits it, with the exact
command that restores the file from where the work left trunk. A detached
HEAD, or a branch that changes nothing but docs, hears only that warning. The hook does not look at the PR itself, because that needs the
network and a Stop hook must work offline.

On trunk or a docs/handoff-* branch it prints HANDOFF STALE, as before, only
when ALL of these hold:
  - the last 8 hours hold MIN_COMMITS commits touching real files
  - none of those commits touched the handoff
  - the handoff was not modified in the working tree either

A second check runs on the same Stop whenever the cwd is a git repo, whatever
the commit count: the shape check in handoff_shape.py. It warns when the
file lacks the Start here block, when that block differs from the plugin's
current copy (issue #118), and on a few other shape problems that module
lists.

The same script runs on SessionStart (issue #117), for a new session or a
/clear only. There it runs only the shape check, offline, and never the
branch checks. A problem goes out as additionalContext with one more step:
run a `gh pr list` command that finds an open PR changing the file, and with
none, migrate the file as the first task, before taking a ticket. So an old repo migrates when a session opens in it,
and the session does not follow the old block for its whole first turn.

Escape hatch: SKIP_HANDOFF_CHECK=1 in the environment, for all of it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from handoff_touch import HANDOFF, git, touched_since
    from handoff_shape import START_HERE, shape_problems
    from handoff_sent import send_once
except Exception:  # a missing or broken helper: no check, and never a crash
    sys.exit(0)

# A commit touching only these is not "real work" needing a handoff entry.
DOC_SUFFIXES = (".md", ".txt", ".rst")

# Below this, a session is too small to be worth a handoff entry.
MIN_COMMITS = 2

# Branches where the handoff itself is written. Anything else is a work branch.
# Fallback trunk names, used only when refs/remotes/origin/HEAD is not set.
FALLBACK_TRUNKS = ("main", "master")
HANDOFF_BRANCH_PREFIX = "docs/handoff-"
NOTES_HEADING = "## Handoff notes"

SHAPE_HELP = ("The shape, with the block to paste, is in the yw-workflow skill "
              "skills/handoff (invoke /yw-workflow:handoff).")
# Added at SessionStart, so an old repo migrates before it takes a ticket.
# The session runs the command. The hook itself makes no network call.
OPEN_PR_CMD = ("gh pr list --state open --limit 100 --json number,title,files "
               "--jq '.[] | select(any(.files[]; .path == \"" + HANDOFF + "\")) "
               "| \"#\\(.number) \\(.title)\"'")
FIRST_TASK = (f"First run `{OPEN_PR_CMD}`. It prints a PR: a migration is "
              f"open, so skip it. It prints nothing: migrate {HANDOFF} to this "
              f"shape as your first task, before you take a ticket or start any "
              f"other work.")


def is_ancestor(a: str, b: str) -> bool:
    try:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                              capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def trunks() -> set[str]:
    """main, master, and origin/HEAD's target if that ref really exists."""
    names = set(FALLBACK_TRUNKS)
    ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    if "/" in ref and git("rev-parse", "--verify", "--quiet", ref).strip():
        names.add(ref.split("/", 1)[1])
    return names


def branch_base(branch: str, names: set[str]) -> tuple[str, list[str]]:
    """The commit a branch's work is diffed from ("" when none exists), and the
    refs its handoff is compared with, closest first."""
    if not branch:
        # ponytail: a detached HEAD that merged another unpushed line is
        # judged from its oldest unpushed commit; fine for reviewer worktrees
        own = git("rev-list", "--reverse", "--topo-order", "HEAD",
                  "--not", "--branches", "--remotes").split()
        start = own[0] + "^" if own else "HEAD"
        base = git("rev-parse", "--verify", "--quiet", start).strip()
        return base, [base] if base else []
    found = []
    for ref in [f"{r}{n}" for n in sorted(names) for r in ("origin/", "")]:
        base = git("merge-base", "HEAD", ref).strip()
        if base:
            n = int(git("rev-list", "--count", f"{base}..HEAD").strip() or 0)
            found.append((n, ref, base))
    # A trunk ref whose merge-base is a strict ancestor of another's is stale
    # (e.g. a local main never pulled). Matching its handoff would delete the
    # passes the newer ref carries, so it drops out. The closest survives.
    keep = sorted((f for f in found if not any(
        o[2] != f[2] and is_ancestor(f[2], o[2]) for o in found)),
        key=lambda f: f[0])
    return (keep[0][2] if keep else ""), [ref for _, ref, _ in keep]


def branch_notes(touched_handoff: bool, real: bool, ref: str, detached: bool) -> str:
    who = "these commits" if detached else "this branch"
    edited = (f"Only a handoff branch edits {HANDOFF}: {who} touched it, and "
              f"every concurrent branch that does hits a merge conflict there. Move "
              f"those lines into the PR body and restore the file from where "
              f"this work left trunk:\n"
              f"  git checkout $(git merge-base HEAD {ref}) -- {HANDOFF}\n"
              f"One exception: a branch that changes the `{START_HERE}` block "
              f"itself edits {HANDOFF}, and this warning is expected there.\n\n"
              if touched_handoff else "")
    if not real:
        return f"HANDOFF NOTES: {edited}Deliberate skip: SKIP_HANDOFF_CHECK=1\n"
    return (
        f"HANDOFF NOTES: this branch changes real files.\n\n"
        f"{edited}"
        f"Write what the next session needs in a `{NOTES_HEADING}` section of "
        f"this branch's PR body, now, while you still remember why: decisions "
        f"and why, what was deliberately not done, which alternative lost, what "
        f"trap cost time. No test counts, no SHAs. After merge, a handoff pass "
        f"on a {HANDOFF_BRANCH_PREFIX}* branch copies it into {HANDOFF}.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n"
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        event = data.get("hook_event_name")
    except Exception:
        sys.exit(0)

    if os.environ.get("SKIP_HANDOFF_CHECK") == "1":
        sys.exit(0)
    top = git("rev-parse", "--show-toplevel").strip()
    if not top:
        sys.exit(0)

    problems = shape_problems(top)
    shape = [f"HANDOFF SHAPE: {problem}\n{SHAPE_HELP}\n"
             f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n\n"
             for problem in problems]
    if event == "SessionStart":
        if shape:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": "".join(shape) + FIRST_TASK}}))
        sys.exit(0)
    # Stop. A warning reaches the model only as JSON on stdout (issue #125):
    # Claude never sees stderr from a hook that exits 0. While a Stop hook
    # already keeps the turn going, say nothing, so this never loops.
    if data.get("stop_hook_active"):
        sys.exit(0)
    keyed = [(f"SHAPE/{p.splitlines()[0]}", w)
             for p, w in zip(problems, shape)] + branch_warning()
    send_once(str(data.get("session_id") or ""), keyed)
    sys.exit(0)


def branch_warning() -> list[tuple[str, str]]:
    """[(key, HANDOFF NOTES)] on a work branch, [(key, HANDOFF STALE)] on trunk, or
    [] for neither. The key names the variant send_once records."""
    branch = git("branch", "--show-current").strip()
    names = trunks()
    if branch not in names and not branch.startswith(HANDOFF_BRANCH_PREFIX):
        base, refs = branch_base(branch, names)
        if not base:
            return []
        files = git("diff", "--name-only", f"{base}..HEAD").splitlines()
        real = bool(branch) and any(not f.endswith(DOC_SUFFIXES) for f in files)
        # Edited only if the handoff differs from EVERY trunk ref. The closest
        # base can be a local trunk that diverged from origin, and a branch that
        # merged origin's handoff pass must not be told to revert it.
        touched = bool(refs) and all(
            git("diff", "--name-only", ref, "HEAD", "--", HANDOFF).strip()
            for ref in refs)
        if not (touched or real):
            return []
        key = "NOTES/" + "+".join(v for v, on in (("real", real), ("edited", touched)) if on)
        return [(key, branch_notes(touched, real, refs[0], not branch))]

    # Trunk or a handoff branch: commits made in roughly this session.
    # Wall-clock is the only signal available here, so it is deliberately
    # generous: a false negative (no warning) is much cheaper than nagging a
    # session that did nothing.
    log = git("log", "--since=8.hours", "--pretty=%H", "--no-merges")
    shas = [s for s in log.split() if s]

    real_work = 0
    for sha in shas:
        files = [f for f in git("show", "--name-only", "--pretty=", sha).split() if f]
        if any(not f.endswith(DOC_SUFFIXES) for f in files):
            real_work += 1

    # A commit in the window that touched the handoff, or an uncommitted edit
    # to it (the session is mid-update), means it is being kept.
    if real_work < MIN_COMMITS or touched_since("8.hours"):
        return []

    exists = bool(git("ls-files", HANDOFF).strip())
    if exists:
        what = (f"run the handoff pass now, on a {HANDOFF_BRANCH_PREFIX}* "
                f"branch: send each line of the `{NOTES_HEADING}` of each PR "
                f"merged since the last pass to one place, and rewrite "
                f"`## Now` and `## Next` in {HANDOFF}")
    else:
        what = (f"{HANDOFF} does not exist yet. Create it in a handoff pass "
                f"on a {HANDOFF_BRANCH_PREFIX}* branch")

    return [("STALE", (
        f"HANDOFF STALE: {real_work} commits of real work this session and "
        f"nothing touched {HANDOFF}.\n\n"
        f"CLAUDE.md Section 6: the handoff is written down AS WORK HAPPENS. "
        f"Written at the end, it is composed from a compacted memory of the "
        f"session, and the reasoning that mattered is what drops out first.\n\n"
        f"So: {what}. Turn each next step for open work into ticket state: "
        f"a ticket, or a comment on the ticket it names. Each \"after #X\" "
        f"is a \"blocked by\" link on GitHub, and a question for the owner is "
        f"the label `needs-owner` on the ticket it holds back. A few lines per "
        f"meaningful step. Judgment, not derivable "
        f"state: why a decision went the way it did, what was deliberately not "
        f"done, which alternative was rejected and why, what trap cost time. "
        f"No test counts, no SHAs, no issue counts.\n\n"
        f"Add no dated section: the pass rewrites the file in place.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n"
    ))]


if __name__ == "__main__":
    main()
