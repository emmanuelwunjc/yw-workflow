#!/usr/bin/env python3
"""Warn when a session commits real work and never touches docs/HANDOFF.md.

CLAUDE.md Section 6 says the handoff is written down AS WORK HAPPENS. An
end-of-session handoff is composed from a compacted, lossy memory of the
session, and the reasoning that mattered (why an alternative was rejected, what
trap cost an hour) is exactly what drops out first.

Where it is written depends on the branch. The owner decided on 2026-09-21
that lanes do not edit docs/HANDOFF.md, because every concurrent lane that
appended to it hit a merge conflict there. A lane writes its notes in a
"## Handoff notes" section of its PR body. After merges, one handoff pass on a
docs/handoff-* branch copies those notes into the log.

That rule was prose. On 2026-08-05 a session merged five PRs, filed sixteen
issues and made a dozen judgment calls before anyone asked whether a handoff
existed. It did not. So this is the mechanism, per CLAUDE.md's own rule that a
broken rule gets a hook rather than a stronger sentence.

WARNS, does not block. Blocking a Stop on a documentation rule would strand
real work over a doc, and some sessions legitimately commit nothing worth
handing off (a one-line typo fix, a revert). The warning is addressed to the
model, which can act on it in the same turn.

Fires on Stop, in a git repo. What it checks depends on the branch.

Trunk is main, master, and whatever refs/remotes/origin/HEAD names if that
ref exists. A lane is any other branch, and a detached HEAD too. A lane is
judged by its net diff from a base, never by its commits one at a time, so
a lane that reverts a handoff edit is clean again:
  - named lane: base is the merge-base with the closest trunk ref (origin/
    or local, whichever is nearer HEAD)
  - detached HEAD (a reviewer worktree, by design): only commits on no
    branch and no remote are its own; base is the parent of the oldest
  - no base (a shallow clone, no trunk ref): the hook says nothing
There is no time window for lanes.

A named lane whose diff changes real files gets HANDOFF NOTES: put the notes
in the PR body's "## Handoff notes" section. Any lane whose diff changes the
handoff is told lanes do not edit it. A detached HEAD hears only that second
part. The hook does not look at the PR itself, because that needs the
network and a Stop hook must work offline.

On trunk or a docs/handoff-* branch it prints HANDOFF STALE, as before, only
when ALL of these hold:
  - the last 8 hours hold MIN_COMMITS commits touching real files
  - none of those commits touched the handoff
  - the handoff was not modified in the working tree either

A second check runs on the same Stop whenever the cwd is a git repo, whatever
the commit count. The owner decided on 2026-09-16 that pointing a fresh agent
at docs/HANDOFF.md is the whole prompt, which only works if the file has the
shape skills/handoff/SKILL.md describes. So it warns when:
  - docs/HANDOFF.md exists and has no "## Start here" line
  - its first 40 lines still carry the old "end of a session" preamble, which
    told the reader the file was written at close and contradicts the block
  - a file named like a handoff (HANDOFF.md, AGENT_HANDOFF.md, *handoff*.md,
    any case) is tracked anywhere outside docs/, because two handoffs means
    the next session reads the wrong one

Escape hatch: SKIP_HANDOFF_CHECK=1 in the environment, for all of it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HANDOFF = "docs/HANDOFF.md"

# A commit touching only these is not "real work" needing a handoff entry.
DOC_SUFFIXES = (".md", ".txt", ".rst")

# Below this, a session is too small to be worth a handoff entry.
MIN_COMMITS = 2

# Branches where the handoff itself is written. Anything else is a lane.
# Fallback trunk names, used only when refs/remotes/origin/HEAD is not set.
FALLBACK_TRUNKS = ("main", "master")
HANDOFF_BRANCH_PREFIX = "docs/handoff-"
NOTES_HEADING = "## Handoff notes"

START_HERE = "## Start here"
OLD_PREAMBLE = ("end of a session", "end of the session")
PREAMBLE_LINES = 40
SHAPE_HELP = ("The shape, with the block to paste, is in the yw-workflow skill "
              "skills/handoff (invoke /yw-workflow:handoff).")


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=15
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def shape_problems(top: str) -> list[str]:
    """Each string is one warning; empty means the handoff has the right shape."""
    problems = []
    handoff = os.path.join(top, HANDOFF)
    if os.path.isfile(handoff):
        try:
            with open(handoff, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
        if not any(ln.strip() == START_HERE for ln in lines):
            problems.append(
                f"{HANDOFF} has no `{START_HERE}` line. A fresh session reads this "
                f"file as its whole prompt, so paste the Start here block at the "
                f"top, above everything else.")
        head = "\n".join(lines[:PREAMBLE_LINES]).lower()
        hit = next((p for p in OLD_PREAMBLE if p in head), None)
        if hit:
            problems.append(
                f"{HANDOFF} still says \"{hit}\" in its first {PREAMBLE_LINES} "
                f"lines. That preamble told the reader the file was written at "
                f"close; the file is written as work happens. Delete it.")
    tracked = git("-C", top, "ls-files", "-z").split("\0")
    stray = [f for f in tracked
             if "handoff" in os.path.basename(f).lower()
             and f.lower().endswith(".md")
             and not f.startswith("docs/")]
    if stray:
        problems.append(
            f"handoff-named files tracked outside docs/: {', '.join(sorted(stray))}. "
            f"The one handoff lives at {HANDOFF}. Fold these into it and delete them.")
    return problems


def trunks() -> set[str]:
    """main, master, and origin/HEAD's target if that ref really exists."""
    names = set(FALLBACK_TRUNKS)
    ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    if "/" in ref and git("rev-parse", "--verify", "--quiet", ref).strip():
        names.add(ref.split("/", 1)[1])
    return names


def lane_base(branch: str, names: set[str]) -> str:
    """The commit a lane's own work is diffed from, or "" when none exists."""
    if not branch:
        # ponytail: a detached HEAD that merged another unpushed line is
        # judged from its oldest unpushed commit; fine for reviewer worktrees
        own = git("rev-list", "--reverse", "--topo-order", "HEAD",
                  "--not", "--branches", "--remotes").split()
        start = own[0] + "^" if own else "HEAD"
        return git("rev-parse", "--verify", "--quiet", start).strip()
    best, best_n = "", -1
    for ref in [f"{r}{n}" for n in sorted(names) for r in ("origin/", "")]:
        base = git("merge-base", "HEAD", ref).strip()
        if base:
            n = int(git("rev-list", "--count", f"{base}..HEAD").strip() or 0)
            if best_n < 0 or n < best_n:
                best, best_n = base, n
    return best


def lane_notes(touched_handoff: bool) -> None:
    edited = (f"Lanes do not edit {HANDOFF}: this branch touched it, and every "
              f"concurrent lane that does hits a merge conflict there. Move "
              f"those lines into the PR body and revert the file.\n\n"
              if touched_handoff else "")
    print(
        f"HANDOFF NOTES: this lane changes real files.\n\n"
        f"{edited}"
        f"Write what the next session needs in a `{NOTES_HEADING}` section of "
        f"this branch's PR body, now, while you still remember why: decisions "
        f"and why, what was deliberately not done, which alternative lost, what "
        f"trap cost time. No test counts, no SHAs. After merge, a handoff pass "
        f"on a {HANDOFF_BRANCH_PREFIX}* branch copies it into {HANDOFF}.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n",
        file=sys.stderr,
    )


def main() -> None:
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)

    if os.environ.get("SKIP_HANDOFF_CHECK") == "1":
        sys.exit(0)
    top = git("rev-parse", "--show-toplevel").strip()
    if not top:
        sys.exit(0)

    for problem in shape_problems(top):
        print(f"HANDOFF SHAPE: {problem}\n{SHAPE_HELP}\n"
              f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n", file=sys.stderr)

    branch = git("branch", "--show-current").strip()
    names = trunks()
    if branch not in names and not branch.startswith(HANDOFF_BRANCH_PREFIX):
        base = lane_base(branch, names)
        if not base:
            sys.exit(0)
        files = git("diff", "--name-only", f"{base}..HEAD").split()
        touched = HANDOFF in files
        real = any(not f.endswith(DOC_SUFFIXES) for f in files)
        if touched or (branch and real):
            lane_notes(touched)
        sys.exit(0)

    # Trunk or a handoff branch: commits made in roughly this session.
    # Wall-clock is the only signal available here, so it is deliberately
    # generous: a false negative (no warning) is much cheaper than nagging a
    # session that did nothing.
    log = git("log", "--since=8.hours", "--pretty=%H", "--no-merges")
    shas = [s for s in log.split() if s]

    touched_handoff = False
    real_work = 0
    for sha in shas:
        files = [f for f in git("show", "--name-only", "--pretty=", sha).split() if f]
        if any(f.endswith(HANDOFF) for f in files):
            touched_handoff = True
        if any(not f.endswith(DOC_SUFFIXES) for f in files):
            real_work += 1

    if touched_handoff or real_work < MIN_COMMITS:
        sys.exit(0)

    # Uncommitted edit to the handoff counts: the session is mid-update.
    if HANDOFF in git("status", "--porcelain"):
        sys.exit(0)

    exists = bool(git("ls-files", HANDOFF).strip())
    if exists:
        what = (f"run the handoff pass now, on a {HANDOFF_BRANCH_PREFIX}* "
                f"branch: copy the `{NOTES_HEADING}` of each PR merged since "
                f"the last pass into {HANDOFF}, and rewrite `## Next` (or the closing section) "
                f"if the first task changed")
    else:
        what = (f"{HANDOFF} does not exist yet. Create it in a handoff pass "
                f"on a {HANDOFF_BRANCH_PREFIX}* branch")

    print(
        f"HANDOFF STALE: {real_work} commits of real work this session and "
        f"nothing touched {HANDOFF}.\n\n"
        f"CLAUDE.md Section 6: the handoff is written down AS WORK HAPPENS. "
        f"Written at the end, it is composed from a compacted memory of the "
        f"session, and the reasoning that mattered is what drops out first.\n\n"
        f"So: {what}. A few lines per meaningful step. Judgment, not derivable "
        f"state: why a decision went the way it did, what was deliberately not "
        f"done, which alternative was rejected and why, what trap cost time. "
        f"No test counts, no SHAs, no issue counts.\n\n"
        f"Reorganize only at a real milestone, not on every touch.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n",
        file=sys.stderr,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
