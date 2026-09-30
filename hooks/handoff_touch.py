#!/usr/bin/env python3
"""Has the handoff been written lately? One answer, shared by two hooks.

handoff-freshness.py asks it about the last 8 hours. context-handoff.py asks
it about the time since its wind-down notice. Both must agree on what counts,
so the test lives here once.

Counts as written: a non-merge commit newer than `since` that changes
docs/HANDOFF.md, or an uncommitted change to it in the working tree.

Does not count: a lane's `## Handoff notes` in its PR body. Seeing that needs
the network, and a hook must work offline.

git runs in the process's working directory, which is the session's.
"""
import subprocess

HANDOFF = "docs/HANDOFF.md"


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=15
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def touched_since(since: str) -> bool:
    """`since` is anything `git log --since` takes: "8.hours", "@1790000000"."""
    for sha in git("log", "--since=" + since, "--pretty=%H", "--no-merges").split():
        if any(f.endswith(HANDOFF)
               for f in git("show", "--name-only", "--pretty=", sha).split()):
            return True
    # ponytail: an uncommitted edit carries no time, so one made before `since`
    # counts too. Compare the file's mtime if that ever matters.
    return HANDOFF in git("status", "--porcelain")
