#!/usr/bin/env python3
"""Tell an Orca bot Home Chat to hand over and run `orca bot new-chat` itself.

Issue #336. A bot Home Chat gets mail all day, so it never has the one long
turn that context-handoff.py's wind-down expects. Only the bot's own Home Chat
can run `orca bot new-chat`. On 2026-11-25 the Twenty bot reached that line,
said so twice, and waited, because its own note said "at most once every 4
hours". This hook makes the handover happen, and the limit wins over that
guard.

The limit is context-handoff.py's wind-down line: `first_percent` (30) of the
model's context window, read through that hook's own settings(), window() and
context_tokens(), so a change there moves this line too. Two lines:

- near: `near_percent` of the limit (80% by default). From here, a notice,
  but only when this chat is at least `min_hours` old (4 by default). The chat
  starts at a handover, so its age is the time since the last one.
- limit: from here, a notice whatever the chat's age.

The notice has two stages:

1. No dated handoff file in memory/ newer than this chat's start, or MEMORY.md does
   not name it: write the file and its pointer. It does not name the new-chat
   command, so the bot cannot clear before the handoff exists.
2. Both exist: finish the turn, then run `orca bot new-chat` as its last step.

It is given on each UserPromptSubmit (the next turn) while the context stays
past the line, and stage 2 once on PostToolBatch, so the bot can clear in the
same turn it wrote the handoff.

A bot Home Chat is a main-thread session whose cwd is a bot home (a folder
~/.orca/bots/<name>/ that holds bot.json) and that
`orca bot chats --all --json` marks `self` and `home`. Every chat of a bot runs in its bot home: automation
runs and side chats too, so the folder alone is not enough. After this chat
ran `orca bot new-chat`, it is no longer the Home Chat, and the hook says
nothing more in it. Workers run in worktrees, and the owner's own sessions run
in their repos, so neither is touched. When `orca bot chats` fails, the notice
still comes, with a line that says the hook could not tell.

Never fails the turn: any error prints nothing.
Config: [rules] bot_handover, and [bot_handover] near_percent / min_hours /
handoff_glob, in .handrail.toml (see handrail_config.py).
"""
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import handrail_config
except Exception:  # a broken config module still leaves the defaults below
    handrail_config = None

try:  # the context reading and the limit come from context-handoff.py
    _spec = importlib.util.spec_from_file_location(
        "context_handoff", HERE / "context-handoff.py")
    context_handoff = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(context_handoff)
except Exception:  # without it there is no size to read: see respond()
    context_handoff = None

RULE = "bot_handover"
# The same values as handrail_config.VALUE_DEFAULTS, for when it fails to load.
DEFAULTS = {"near_percent": 80, "min_hours": 4,
            "handoff_glob": "memory/handoff-20*.md"}
VALID = {"near_percent": lambda v: type(v) is int and 0 < v <= 100,
         "min_hours": lambda v: type(v) is int and v >= 0,
         "handoff_glob": lambda v: (isinstance(v, str) and v.strip() != ""
                                    and not v.startswith("/"))}
HEAD_LINES = 50  # the chat's start time is on one of its first lines
CHATS_TIMEOUT = 10  # seconds; `orca bot chats --json` takes about 0.3

WRITE = (
    "This bot Home Chat is at %(size)dk tokens of context%(why)s. Hand over "
    "now. Finish or park the step in hand, and put open work on items. Then "
    "write a handoff file at %(glob)s in this bot home (e.g. "
    "memory/handoff-<date>.md): what is done, what waits on the owner, what "
    "you wait on and the event that wakes it, the first three steps for the "
    "next chat. Write the command that derives a number, never the number. "
    "Then add a dated line to MEMORY.md that names that file. The next notice "
    "gives the command that starts the new chat.")
CLEAR = (
    "This bot Home Chat is at %(size)dk tokens of context%(why)s, and the "
    "handoff file %(file)s is written and named in MEMORY.md. Finish this "
    "turn: wait for every tool call and worker reply in it. Then, as the "
    "last step of the turn, run `orca bot new-chat` from this Home Chat. "
    "Only this chat can run it.")
# context-handoff.py gives its own wind-down notice at the same limit. Its
# text is for a work session, so a Home Chat is told which one to follow.
FOLLOW = (" In a bot Home Chat, this handover is how you follow the wind-down "
          "notice: the handoff goes in this bot home, and the new chat is the "
          "fresh session.")
UNSURE = (" This hook could not ask `orca bot chats --all --json` whether "
          "this chat is the Home Chat. Run `\"${ORCA_CLI_COMMAND:-orca}\" bot "
          "chats --json` and read the row marked self: act on this notice "
          "only when that row is home.")
AT_LIMIT = (", at or past the ~%(limit)dk limit. The limit wins over the "
            "once-every-%(hours)d-hours guard")
NEAR = ", near the ~%(limit)dk limit, and this chat is over %(hours)d hours old"


def settings():
    """(enabled, values). A config that cannot be read means defaults."""
    try:
        cfg = handrail_config.load()
        enabled = cfg.enabled(RULE)
        values = {key: cfg.value(RULE, key) for key in DEFAULTS}
    except Exception:
        return True, dict(DEFAULTS)
    return enabled, {key: val if VALID[key](val) else DEFAULTS[key]
                     for key, val in values.items()}


def bot_home(cwd):
    """The bot home this cwd is, or None."""
    if not cwd:
        return None
    # ponytail: the cwd must be the bot home itself. A Home Chat that has cd'd
    # into a subfolder gets no notice that turn. Read the transcript's project
    # folder instead if that ever happens.
    path = Path(cwd).resolve()
    bots = (Path.home() / ".orca" / "bots").resolve()
    if path.parent == bots and (path / "bot.json").is_file():
        return path
    return None


def is_home_chat():
    """True or False from `orca bot chats --json`, or None when it fails.
    Run from a bot's chat, it marks that chat `self`, and the Home Chat
    `home`."""
    command = os.environ.get("ORCA_CLI_COMMAND") or "orca"
    try:
        out = subprocess.run([command, "bot", "chats", "--all", "--json"],
                             capture_output=True, text=True,
                             timeout=CHATS_TIMEOUT).stdout
        chats = json.loads(out)["result"]["chats"]
        mine = [c for c in chats if c.get("self") is True]
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError):
        return None
    if len(mine) != 1:
        return None
    return mine[0].get("home") is True and mine[0].get("closed") is not True


def chat_start(transcript):
    """Epoch seconds of the transcript's first timestamp, else its mtime."""
    with open(transcript) as fh:
        for _, raw in zip(range(HEAD_LINES), fh):
            try:
                stamp = json.loads(raw).get("timestamp")
                # Python before 3.11 reads no "Z" suffix.
                stamp = stamp.replace("Z", "+00:00")
                return datetime.datetime.fromisoformat(stamp).timestamp()
            except (ValueError, TypeError, AttributeError):
                continue
    # ponytail: the mtime is about now, so below the limit the age guard holds
    # the notice back. At the limit it still comes.
    return Path(transcript).stat().st_mtime


def fresh_handoff(home, glob, since):
    """The newest handoff file newer than `since` that MEMORY.md names."""
    try:
        memory = (home / "MEMORY.md").read_text()
    except OSError:
        return None
    files = sorted((p for p in home.glob(glob) if p.stat().st_mtime > since),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        if path.relative_to(home).as_posix() in memory:
            return path.relative_to(home).as_posix()
    return None


def state_path(session):
    name = "".join(c for c in str(session) if c.isalnum() or c in "-_")
    return name and Path.home() / ".claude" / "state" / "bot-handover" / name


def respond(data, now):
    """The JSON object to print for this event, or None to stay silent."""
    session = data.get("session_id")
    if not session or data.get("agent_id") or context_handoff is None:
        return None
    home = bot_home(data.get("cwd"))
    if home is None:
        return None
    enabled, cfg = settings()
    if not enabled:
        return None
    transcript = data["transcript_path"]
    found = context_handoff.context_tokens(transcript)
    if found is None:
        return None
    tokens, model = found
    wind = context_handoff.settings()[1]
    limit = context_handoff.window(wind, model) * wind["first_percent"] // 100
    if tokens * 100 < limit * cfg["near_percent"]:
        return None
    start = chat_start(transcript)
    at_limit = tokens >= limit
    if not at_limit and now - start < cfg["min_hours"] * 3600:
        return None
    handoff = fresh_handoff(home, cfg["handoff_glob"], start)
    event = data.get("hook_event_name", "UserPromptSubmit")
    state = state_path(session)
    # PostToolBatch: once per chat, and only stage 2. Stage 1 waits for the
    # next turn.
    if event == "PostToolBatch" and (not handoff or not state
                                     or state.exists()):
        return None
    home_chat = is_home_chat()  # the one slow check: every return above it is cheap
    if home_chat is False:
        return None
    if event == "PostToolBatch":
        context_handoff.write_state(state, {"asked": now}, now)
    fill = {"size": tokens // 1000, "limit": limit // 1000, "file": handoff,
            "hours": cfg["min_hours"], "glob": cfg["handoff_glob"]}
    fill["why"] = (AT_LIMIT if at_limit else NEAR) % fill
    text = (CLEAR if fill["file"] else WRITE) % fill
    if at_limit:
        text += FOLLOW
    if home_chat is None:
        text += UNSURE
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
