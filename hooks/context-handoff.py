#!/usr/bin/env python3
"""Wind a session down and get its handoff written once its context is large.

mattpocock's ask-matt skill puts the "smart zone" at about 120k tokens: "If a
session approaches it ... /handoff and continue in a fresh thread". A session
cannot see its own size, so it pushes on degraded. The owner decided on
2026-09-30 that a warning is too weak: past the line the session lets its
running subagents finish, for a bounded time, and writes the handoff either
way. The threshold is a token count, because that is the unit the source
gives. It is no percentage of any model's window.

This hook instructs and the model acts. It kills nothing itself. Three parts:

1. Wind-down notice. The first PostToolBatch or UserPromptSubmit at or past
   `first` tokens, and again at each `step` past it (220k, 320k): start no
   new work, spawn no subagents, let running ones finish for at most
   `grace_minutes`, set a background timer for the deadline, then write the
   handoff and tell the user to start a fresh session. The time is recorded.
2. Deadline notice. The first of those events at or after that time plus
   `grace_minutes`, when no handoff has been written since: save what each
   running subagent has, stop it (TaskStop), write the handoff now. Once.
3. Stop check. After a notice, with no handoff written since, one Stop is
   blocked with the same instruction. One only, per notice. `stop_hook_active`
   is honored, and inside the grace a Stop with background work in flight is
   let through, because a main thread waiting on subagents must go idle.

Notices go through `hookSpecificOutput.additionalContext`. PostToolBatch runs
once per batch of tool calls, before the next model call, where PostToolUse
would run once per call and race itself on parallel calls. Inside a subagent
the input carries `agent_id`, and the hook does nothing there.

"Handoff written" is handoff_touch.touched_since, the same test
handoff-freshness.py uses: a commit to docs/HANDOFF.md since the notice, or an
uncommitted edit to it. A lane's `## Handoff notes` in a PR body is invisible
to it, and so is everything in a folder that is not a git repo. There the
deadline notice and the one Stop block always arrive. Both say which case it
is, and the model answers by stopping again. With the detector missing or
broken, the hook gives neither, since it cannot tell.

The size is the last main-thread assistant message's `usage` in the
transcript: input_tokens + cache_read_input_tokens +
cache_creation_input_tokens. Lines that sum to 0 (synthetic ones) are skipped.
The docs say the transcript may lag the conversation, which is fine at a 100k
granularity.

State is one JSON file per session in ~/.claude/state/context-handoff/. A drop
below the recorded step (a /compact) lowers the record, so growing back over
the line gives the notice again. A drop below `first` ends the wind-down.

Never fails the turn: any error exits 0 with nothing printed. The one
deliberate block is the Stop check.
Config: [rules] context_handoff, and [context_handoff] first / step /
grace_minutes, in .handrail.toml (see handrail_config.py).
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
try:
    import handoff_touch
except Exception:  # a missing or broken helper leaves no detector: see respond()
    handoff_touch = None
HANDOFF = getattr(handoff_touch, "HANDOFF", "docs/HANDOFF.md")

RULE = "context_handoff"
DEFAULTS = {"first": 120000, "step": 100000, "grace_minutes": 15}
USAGE_FIELDS = ("input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")
STATE_TTL_SECONDS = 7 * 24 * 3600
# ponytail: only the transcript's tail is read, because a long session's file
# is tens of MB and this runs after every tool call. A last assistant line
# further back than this is missed, and the hook stays silent.
TAIL_BYTES = 2 * 1024 * 1024

WRITE = ("write the handoff now: load the handoff skill, then %s on a "
         "docs/handoff-* branch, or a `## Handoff notes` section in the PR "
         "body on a lane, per the repo's rules. Then tell the user to start a "
         "fresh session." % HANDOFF)
# A plain folder has no branch and no PR, so its text names neither.
WRITE_FOLDER = ("write the handoff now: load the handoff skill, and ask the "
                "user where it should live if that is not already clear. Then "
                "tell the user to start a fresh session.")
WIND_DOWN = (
    "Context is at %(size)dk tokens, past the ~%(first)dk where reasoning "
    "stays sharp. Wind down now. Start no new work and spawn no new "
    "subagents. Subagents already running may finish, for at most %(grace)d "
    "minutes from now. If any are still running, start one background timer "
    "so you are re-invoked at the deadline: Bash `sleep %(seconds)d` with "
    "run_in_background set to true. An idle main thread triggers no hook, so "
    "the timer is what brings you back. When they have all reported, or at "
    "the deadline, whichever comes first, %(write)s")
DEADLINE = (
    "The %(grace)d-minute grace for running subagents is over and no handoff "
    "has been written. For each subagent still running: save what it has "
    "produced so far into the handoff (its last report, its branch and "
    "worktree path, any files), then stop it with the TaskStop tool. Then "
    "%(write)s")
STOP = (
    "Context is past the ~%(first)dk tokens where reasoning stays sharp, and "
    "no handoff has been written since the wind-down notice. Start no new "
    "work and spawn no new subagents. If subagents are still running inside "
    "their %(grace)d-minute grace and your timer is set, stop again and wait "
    "for them. Otherwise %(write)s")
UNSEEN = (" This check sees only %s. If the handoff notes are already in the "
          "PR body, say so and stop again." % HANDOFF)
UNSEEN_FOLDER = (" This check sees only %s in a git repo, and this folder is "
                 "not a git repo. If you have written the handoff somewhere, "
                 "say where and stop again." % HANDOFF)


def settings():
    """(enabled, values). A config that cannot be read means defaults."""
    try:
        cfg = handrail_config.load()
        enabled = cfg.enabled(RULE)
        values = {key: cfg.value(RULE, key) for key in DEFAULTS}
    except Exception:
        return True, dict(DEFAULTS)
    ok = lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0
    return enabled, {key: val if ok(val) else DEFAULTS[key]
                     for key, val in values.items()}


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
            values = [entry["message"]["usage"].get(k, 0) for k in USAGE_FIELDS]
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            continue
        # Claude Code writes synthetic assistant lines (API errors, usage-limit
        # notices, "No response requested.") with every field 0. Read as a size,
        # one looks like a /compact and the same step warns twice.
        if sum(values):
            return sum(values)
    return None


def state_dir():
    return Path.home() / ".claude" / "state" / "context-handoff"


def read_state(path):
    """step: the last step a notice was given for (-1: none). noticed: when.
    deadline_sent / stop_blocked: each said once per notice."""
    state = {"step": -1, "noticed": None, "deadline_sent": False,
             "stop_blocked": False}
    try:
        saved = json.loads(path.read_text())
        if isinstance(saved.get("step"), int):
            state["step"] = saved["step"]
        if isinstance(saved.get("noticed"), (int, float)):
            state["noticed"] = saved["noticed"]
        state["deadline_sent"] = saved.get("deadline_sent") is True
        state["stop_blocked"] = saved.get("stop_blocked") is True
    except (OSError, ValueError, AttributeError):
        pass
    return state


def write_state(path, state, now):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
        cutoff = now - STATE_TTL_SECONDS
        for old in path.parent.glob("*"):
            if old.stat().st_mtime < cutoff:
                old.unlink()
    except OSError:
        pass


def wording():
    """(where to write, what the check cannot see) for this folder. Without
    the helper there is no way to tell, and the repo wording is used."""
    if handoff_touch is None or handoff_touch.in_repo():
        return WRITE, UNSEEN
    return WRITE_FOLDER, UNSEEN_FOLDER


def respond(data, now):
    """The JSON object to print for this event, or None to stay silent."""
    session = data.get("session_id")
    # Inside a subagent the transcript is still the parent's, so a notice
    # there would go to the wrong model and use up the parent's step.
    if not session or data.get("agent_id"):
        return None
    enabled, cfg = settings()
    if not enabled:
        return None
    tokens = context_tokens(data["transcript_path"])
    if tokens is None:
        return None
    # the session id comes from Claude Code, but it names a file, so keep it one
    name = "".join(c for c in str(session) if c.isalnum() or c in "-_")
    if not name:
        return None
    path = state_dir() / name
    state = read_state(path)
    first, grace = cfg["first"], cfg["grace_minutes"]
    fill = {"size": tokens // 1000, "first": first // 1000, "grace": grace,
            "seconds": grace * 60}
    event = data.get("hook_event_name", "PostToolBatch")
    noticed = state["noticed"]
    over = noticed is not None and now >= noticed + grace * 60

    if event == "Stop":
        if (noticed is None or tokens < first or state["stop_blocked"]
                or data.get("stop_hook_active")):
            return None
        # Waiting on subagents inside the grace is what the notice asked for.
        if not over and data.get("background_tasks"):
            return None
        # Without the detector the hook cannot tell, so it never blocks.
        if handoff_touch is None or handoff_touch.touched_since(
                "@%d" % noticed, all_refs=True):
            return None
        state["stop_blocked"] = True
        state["deadline_sent"] = state["deadline_sent"] or over
        write_state(path, state, now)
        fill["write"], tail = wording()
        return {"decision": "block",
                "reason": (DEADLINE if over else STOP) % fill + tail}

    step = (tokens - first) // cfg["step"] if tokens >= first else -1
    text = None
    if step > state["step"]:
        state = {"step": step, "noticed": now, "deadline_sent": False,
                 "stop_blocked": False}
        fill["write"] = wording()[0]
        text = WIND_DOWN % fill
    elif step < state["step"]:
        state["step"] = step
        if step < 0:
            state["noticed"] = None  # back under the line: nothing to wind down
    elif over and not state["deadline_sent"]:
        state["deadline_sent"] = True
        # Without the detector the hook cannot tell, so it says nothing.
        if (handoff_touch is not None
                and not handoff_touch.touched_since("@%d" % noticed,
                                                    all_refs=True)):
            fill["write"], tail = wording()
            text = DEADLINE % fill + tail
    else:
        return None
    write_state(path, state, now)
    if text is None:
        return None
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": text}}


def main(stdin_text, now):
    """What to print. Any failure prints nothing: it never fails the turn."""
    try:
        out = respond(json.loads(stdin_text), now)
        return json.dumps(out) if out else ""
    except Exception:
        return ""


if __name__ == "__main__":
    sys.stdout.write(main(sys.stdin.read(), time.time()))
    sys.exit(0)
