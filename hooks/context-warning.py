#!/usr/bin/env python3
"""Tell the model when its context has grown past where it reasons well.

mattpocock's ask-matt skill puts the "smart zone" at about 120k tokens: "If a
session approaches it ... /handoff and continue in a fresh thread". A session
cannot see its own size, so it pushes on degraded. The owner decided on
2026-09-21: warn at 120k, then once more at every 100k past it (220k, 320k).

Fires on PostToolUse and UserPromptSubmit, main thread only. Both events hand
`hookSpecificOutput.additionalContext` to the model's next call, per the
Claude Code hooks docs. Stop was ruled out: its output reaches the debug log,
never the model, unless it blocks.

The size is the last main-thread assistant message's `usage` in the
transcript: input_tokens + cache_read_input_tokens +
cache_creation_input_tokens. The docs say the transcript may lag by a message,
which is fine at a 100k granularity.

Once per step per session, recorded in ~/.claude/state/context-warning/. A
drop below the recorded step (a /compact) lowers the record, so growing back
over the line warns again.

Never blocks, never fails the turn: any error exits 0 with nothing printed.
Config: [rules] context_warning, and [context_warning] first / step, in
.handrail.toml (see handrail_config.py).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import handrail_config
except Exception:  # a broken config module still leaves the defaults below
    handrail_config = None

DEFAULT_FIRST = 120000
DEFAULT_STEP = 100000
USAGE_FIELDS = ("input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")
STATE_DIR = Path.home() / ".claude" / "state" / "context-warning"
STATE_TTL_SECONDS = 7 * 24 * 3600
# ponytail: only the transcript's tail is read, because a long session's file
# is tens of MB and this runs after every tool call. A last assistant line
# further back than this is missed, and the hook stays silent.
TAIL_BYTES = 2 * 1024 * 1024


def settings():
    """(enabled, first, step). A config that cannot be read means defaults."""
    try:
        cfg = handrail_config.load()
        first = cfg.value("context_warning", "first")
        step = cfg.value("context_warning", "step")
        enabled = cfg.enabled("context_warning")
    except Exception:
        return True, DEFAULT_FIRST, DEFAULT_STEP
    ok = lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0
    return (enabled, first if ok(first) else DEFAULT_FIRST,
            step if ok(step) else DEFAULT_STEP)


def context_tokens(path):
    """The context size at the last main-thread assistant message, or None."""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - TAIL_BYTES))
        lines = fh.read().splitlines()
    for raw in reversed(lines):
        try:
            entry = json.loads(raw)
            if entry.get("type") != "assistant" or entry.get("isSidechain"):
                continue
            usage = entry["message"]["usage"]
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        values = [usage.get(k, 0) for k in USAGE_FIELDS]
        if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            return sum(values)
        return None
    return None


def last_step(state):
    try:
        return int(state.read_text())
    except (OSError, ValueError):
        return -1


def record(state, step):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state.write_text(str(step))
        cutoff = time.time() - STATE_TTL_SECONDS
        for old in STATE_DIR.glob("*"):
            if old.stat().st_mtime < cutoff:
                old.unlink()
    except OSError:
        pass


def main():
    data = json.loads(sys.stdin.read())
    session = data.get("session_id")
    # Inside a subagent the transcript is still the parent's, so a warning
    # there would go to the wrong model and use up the parent's step.
    if not session or data.get("agent_id"):
        return
    enabled, first, step_size = settings()
    if not enabled:
        return
    tokens = context_tokens(data["transcript_path"])
    if tokens is None:
        return

    step = (tokens - first) // step_size if tokens >= first else -1
    # the session id comes from Claude Code, but it names a file, so keep it one
    name = "".join(c for c in str(session) if c.isalnum() or c in "-_")
    if not name:
        return
    state = STATE_DIR / name
    previous = last_step(state)
    if step != previous:
        record(state, step)
    if step <= previous:
        return

    text = ("Context is at %dk tokens, past the ~%dk where reasoning stays "
            "sharp. When the agents you are waiting on report, run the handoff "
            "pass (docs/HANDOFF.md) and start a fresh session."
            % (tokens // 1000, first // 1000))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": data.get("hook_event_name", "PostToolUse"),
        "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a warning is never worth failing the turn over
    sys.exit(0)
