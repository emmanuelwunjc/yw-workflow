#!/usr/bin/env python3
"""Shared fixtures for hooks/bot-handover-selftest.py (issue #336).

Each Env() makes a temp HOME with one bot home at ~/.orca/bots/twenty/, a
fake transcript, and a stub `orca` (through ORCA_CLI_COMMAND) that answers
`orca bot chats --all --json` the way Orca does from inside a bot's chat.
run() calls the hook's main(stdin_text, now) the way Claude Code calls it.
The name has no `-selftest.` in it, so the CI loop over
./hooks/*-selftest.* never runs this file on its own.
"""
import atexit
import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

HOOK = pathlib.Path(__file__).with_name("bot-handover.py")
LIMIT = 300000   # the wind-down line: 30% of the 1M window of MODEL
MODEL = "claude-opus-5-5"
NEAR = 250000    # past near_percent (80) of the limit, under the limit
HOUR = 3600
T0 = 1_790_000_000.0
NEW_CHAT = "orca bot new-chat"
FILE = "handoff-2026-11-25.md"

failures = []
cases = 0

# What `orca bot chats --all --json` says about the chat it runs from.
SELF_ROWS = {
    "home": {"home": True, "self": True, "closed": False},
    "side": {"home": False, "self": True, "closed": False},
    # Read from Orca 1.4.274 on 2026-11-25: the old Twenty Home Chat 7c98ce01,
    # after its new-chat ran, is home false and closed true.
    "replaced": {"home": False, "self": True, "closed": True},
    "closed_home": {"home": True, "self": True, "closed": True},
    "no_self": {"home": True, "self": False, "closed": False},
}


def load_hook():
    spec = importlib.util.spec_from_file_location("bot_handover", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def usage_line(tokens, model=MODEL):
    return json.dumps({"type": "assistant", "timestamp": iso(T0), "message": {
        "role": "assistant", "model": model,
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 4, "cache_creation_input_tokens": 1000,
                  "cache_read_input_tokens": tokens - 1004}}})


class Env:
    """A temp HOME with bot `twenty`, its memory folder, a transcript and a
    stub orca. `chat` is a SELF_ROWS key, or "fail" for an orca that errors."""

    def __init__(self, tokens, chat_age_hours, chat="home", start_stamp=None,
                 model=MODEL):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        atexit.register(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.bot = self.home / ".orca" / "bots" / "twenty"
        (self.bot / "memory").mkdir(parents=True)
        (self.bot / "bot.json").write_text('{"name": "Twenty"}')
        (self.bot / "MEMORY.md").write_text("# Memory\n")
        self.start = T0 - chat_age_hours * HOUR
        first = json.dumps({"type": "user",
                            "timestamp": start_stamp or iso(self.start),
                            "message": {"role": "user", "content": "hi"}})
        self.transcript = self.tmp / "t.jsonl"
        self.transcript.write_text(first + "\n" + usage_line(tokens, model) + "\n")
        self.orca = self.tmp / "orca"
        self.calls = self.tmp / "orca-calls"
        self.set_chat(chat)

    def set_chat(self, chat, extra_rows=(), hang=False):
        """`chat` is a SELF_ROWS key, or "fail". extra_rows are added as they
        are. hang makes the stub sleep before it answers."""
        if chat == "fail":
            body = '{"ok": false, "error": {"code": "invalid_argument"}}'
        else:
            rows = [{"id": "other", "title": "Home" if chat != "home" else "x",
                     "home": chat != "home", "self": False, "closed": False},
                    dict(SELF_ROWS[chat], id="me", title="this chat"),
                    *extra_rows]
            body = json.dumps({"ok": True, "result": {"bot": "Twenty",
                                                      "chats": rows}})
        self.orca.write_text("#!/bin/sh\necho \"$*\" >> '%s'\n%scat <<'END'\n"
                             "%s\nEND\n" % (self.calls, "sleep 5\n" * hang, body))
        self.orca.chmod(0o755)

    def config(self, text):
        (self.home / ".handrail.toml").write_text(text)

    def handoff(self, name=FILE, age_hours=0.5, pointer=True):
        path = self.bot / "memory" / name
        path.write_text("# Handoff\n")
        mtime = T0 - age_hours * HOUR
        os.utime(path, (mtime, mtime))
        if pointer:
            with open(self.bot / "MEMORY.md", "a") as fh:
                fh.write("- 2026-11-25 Home Chat handover: memory/%s\n" % name)

    def orca_calls(self):
        return self.calls.read_text().count("\n") if self.calls.exists() else 0

    def run(self, cwd=None, event="UserPromptSubmit", hook_attrs=None,
            **extra):
        data = {"session_id": "s1", "transcript_path": str(self.transcript),
                "cwd": str(cwd or self.bot), "hook_event_name": event}
        data.update(extra)
        saved = {k: os.environ.get(k) for k in ("HOME", "ORCA_CLI_COMMAND")}
        os.environ["HOME"] = str(self.home)
        os.environ["ORCA_CLI_COMMAND"] = str(self.orca)
        try:
            hook = load_hook()
            for key, val in (hook_attrs or {}).items():
                setattr(hook, key, val)
            out = hook.main(json.dumps(data), T0)
        finally:
            for key, val in saved.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val
        if not out:
            return None
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def check(name, cond, detail=""):
    global cases
    cases += 1
    failures.extend([] if cond else ["%s %s" % (name, detail)])


def finish():
    if failures:
        print("bot-handover-selftest: %d of %d cases failed"
              % (len(failures), cases))
        for f in failures:
            print("  FAIL " + f)
        sys.exit(1)
    print("bot-handover-selftest: %d cases pass" % cases)


def asks_file(text):
    return text is not None and "memory/handoff" in text and NEW_CHAT not in text


def asks_new_chat(text, name=FILE):
    return text is not None and NEW_CHAT in text and "memory/" + name in text


