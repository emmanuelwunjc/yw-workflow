#!/usr/bin/env python3
"""Warn when a session commits real work and never touches docs/HANDOFF.md.

CLAUDE.md Section 6 says the handoff is appended to AS WORK HAPPENS, not
written at the end. The reason is that an end-of-session handoff is composed
from a compacted, lossy memory of the session, and the reasoning that mattered
(why an alternative was rejected, what trap cost an hour) is exactly what drops
out first.

That rule was prose. On 2026-08-05 a session merged five PRs, filed sixteen
issues and made a dozen judgment calls before anyone asked whether a handoff
existed. It did not. So this is the mechanism, per CLAUDE.md's own rule that a
broken rule gets a hook rather than a stronger sentence.

WARNS, does not block. Blocking a Stop on a documentation rule would strand
real work over a doc, and some sessions legitimately commit nothing worth
handing off (a one-line typo fix, a revert). The warning is addressed to the
model, which can act on it in the same turn.

Fires on Stop, only when ALL of these hold:
  - the cwd is a git repo
  - the session produced commits touching real files (not docs-only)
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
                f"close; the file is appended to as work happens. Delete it.")
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

    # Commits made in roughly this session. Wall-clock is the only signal
    # available here, so it is deliberately generous: a false negative (no
    # warning) is much cheaper than nagging a session that did nothing.
    log = git("log", "--since=8.hours", "--pretty=%H", "--no-merges")
    shas = [s for s in log.split() if s]
    if len(shas) < MIN_COMMITS:
        sys.exit(0)

    touched_handoff = False
    real_work = 0
    for sha in shas:
        files = [f for f in git("show", "--name-only", "--pretty=", sha).split() if f]
        if any(f.endswith(HANDOFF) for f in files):
            touched_handoff = True
            break
        if any(not f.endswith(DOC_SUFFIXES) for f in files):
            real_work += 1

    if touched_handoff or real_work < MIN_COMMITS:
        sys.exit(0)

    # Uncommitted edit to the handoff counts: the session is mid-update.
    if HANDOFF in git("status", "--porcelain"):
        sys.exit(0)

    exists = bool(git("ls-files", HANDOFF).strip())
    if exists:
        what = f"append to {HANDOFF} now, while you still remember why"
    else:
        what = f"{HANDOFF} does not exist yet. Create it"

    print(
        f"HANDOFF STALE: {real_work} commits of real work this session and "
        f"nothing touched {HANDOFF}.\n\n"
        f"CLAUDE.md Section 6: the handoff is appended to AS WORK HAPPENS. "
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
