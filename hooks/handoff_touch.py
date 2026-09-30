#!/usr/bin/env python3
"""Has the handoff been written lately? One answer, shared by two hooks.

handoff-freshness.py asks it about the last 8 hours. context-handoff.py asks
it about the time since its wind-down notice. Both must agree on what counts,
so the test lives here once.

Counts as written: a non-merge commit newer than `since` that changes
docs/HANDOFF.md, or an uncommitted change to it in the working tree, a new
untracked file included. The commit must be in HEAD's history, or with
all_refs=True on any ref (another branch or worktree, a fetched one, a stash).
handoff-freshness.py judges trunk by trunk's own history, so it keeps HEAD.
context-handoff.py asks whether anyone wrote the handoff after its notice, so
it passes all_refs=True.

Cannot count: a lane's `## Handoff notes` in its PR body, since seeing that
needs the network and a hook must work offline; and anything outside a git
repo, since there is no history to ask.

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


def touched_since(since: str, all_refs: bool = False) -> bool:
    """`since` is anything `git log --since` takes: "8.hours", "@1790000000"."""
    refs = ["--all"] if all_refs else []
    for sha in git("log", *refs, "--since=" + since, "--pretty=%H",
                   "--no-merges").split():
        if any(f.endswith(HANDOFF)
               for f in git("show", "--name-only", "--pretty=", sha).split()):
            return True
    # ponytail: an uncommitted edit carries no time, so one made before `since`
    # counts too. Compare the file's mtime if that ever matters.
    return HANDOFF in git("status", "--porcelain", "--untracked-files=all")


def in_repo() -> bool:
    return bool(git("rev-parse", "--show-toplevel").strip())
