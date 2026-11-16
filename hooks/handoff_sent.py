#!/usr/bin/env python3
"""Send each Stop warning of handoff-freshness.py once per session.

The rule, and why, is in docs/DECISIONS.md (issue #125). The record is one
file per worktree, in its git dir: one line per session id and variant key.
"""

from __future__ import annotations

import json
import os

from handoff_touch import git

# Per-worktree record, in the git dir, of which variant keys each session has
# been sent at Stop, so each one continues a session's turn only once.
SENT_FILE = "handoff-freshness-sent"


def send_once(session: str, warnings: list[tuple[str, str]]) -> None:
    """Print, as one Stop additionalContext, each (key, text) warning whose key
    this session has not been sent, then record those keys. A key names the
    variant (e.g. NOTES/real, one SHAPE problem), never the full text, since
    STALE's commit count changes on each commit. No session id, no git dir,
    or a record that cannot be read, decoded or written: nothing is held
    back."""
    gitdir = git("rev-parse", "--absolute-git-dir").strip() if session else ""
    path = os.path.join(gitdir, SENT_FILE) if gitdir else ""
    sent: set[str] = set()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                sent = set(f.read().split("\n"))
        except (OSError, UnicodeDecodeError):
            pass
    new = [(k, t) for k, t in warnings if f"{session} {k}" not in sent]
    if not new:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "Stop",
        "additionalContext": "".join(t for _, t in new)}}), flush=True)
    if path:
        try:
            # ponytail: one line per session and key, never trimmed. Trim it
            # if the file ever gets big.
            with open(path, "a", encoding="utf-8") as f:
                f.writelines(f"{session} {k}\n" for k, _ in new)
        except OSError:
            pass
