#!/usr/bin/env python3
"""Self-test for context-handoff.py: which usage counts, state files, output
shape, bad input and config.

Fixtures and check() live in context_handoff_testkit.py.

Run: ./hooks/context-handoff-input-selftest.py
"""
import json
import os
import time

from context_handoff_testkit import (
    MIN, T0, Env, check, context, deadline, finish, silent, usage_line,
    user_line, warned)

# --- which usage counts --------------------------------------------------
e = Env()
e.write(usage_line(300_000), user_line(), usage_line(50_000))
check("the most recent assistant usage is the size", silent(e.run()), True)

e = Env()
e.write(usage_line(310_000), usage_line(900_000, sidechain=True))
r = e.run()
check("a sidechain line is skipped; the main-thread one counts",
      warned(r) and "310k" in context(r[1]), True)

e = Env()
e.write(usage_line(310_000))
check("inside a subagent (agent_id present): silent",
      silent(e.run(extra={"agent_id": "a1"})), True)
check("the subagent call did not use up the step",
      warned(e.run()), True)
check("inside a subagent past the deadline: still silent",
      silent(e.run(extra={"agent_id": "a1"}, now=time.time() + 99 * MIN)), True)

# Claude Code writes synthetic assistant lines (API errors, usage-limit notices,
# "No response requested.") with every usage field 0. Read as a size, one looks
# like a /compact and the same step warns twice.
def synthetic_line(model="<synthetic>"):
    return json.dumps({"type": "assistant", "isSidechain": False, "message": {
        "model": model, "role": "assistant", "usage": {
            "input_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": 0}}})


e = Env()
check("synthetic: 310k winds down", warned(e.at(310_000)), True)
e.write(usage_line(310_000), synthetic_line())
check("synthetic: a <synthetic> line after it is silent", silent(e.run()), True)
e.write(usage_line(310_000), synthetic_line(), usage_line(315_000))
check("synthetic: 315k after it stays silent, same step", silent(e.run()), True)
e.write(usage_line(315_000), synthetic_line(model="claude-opus-5"))
check("a zero-sum line from a real model is skipped too", silent(e.run()), True)
e.write(usage_line(320_000))
check("after the zero lines, 320k is still the same step", silent(e.run()), True)
e = Env()
e.write(usage_line(310_000), synthetic_line())
r = e.run()
check("synthetic last: the real line before it is the size",
      warned(r) and "310k" in context(r[1]), True)

# --- state cleanup -----------------------------------------------------------
e = Env()
state_dir = e.home / ".claude" / "state" / "context-handoff"
state_dir.mkdir(parents=True)
old, fresh = state_dir / "old-session", state_dir / "fresh-session"
old.write_text("{}")
fresh.write_text("{}")
eight_days = 8 * 24 * 3600
os.utime(old, (os.path.getmtime(old) - eight_days,) * 2)
e.at(310_000)
check("state older than 7 days is removed when state is written", old.exists(), False)
check("recent state from another session is kept", fresh.exists(), True)

e = Env()
state_dir = e.home / ".claude" / "state" / "context-handoff"
state_dir.mkdir(parents=True)
(state_dir / "s1").write_text("not json")
check("an unreadable state file is treated as no state", warned(e.at(310_000)), True)
(state_dir / "s1").write_text('["a list"]')
check("a state file of the wrong shape is treated as no state",
      warned(e.at(310_000)), True)

# --- output shape ---------------------------------------------------------
e = Env()
code, out, _ = e.at(310_000, event="UserPromptSubmit")
check("the notice is exactly the documented shape",
      json.loads(out or "{}"), {"hookSpecificOutput": {
          "hookEventName": "UserPromptSubmit",
          "additionalContext": context(out)}})

# --- never fail the turn ---------------------------------------------------
e = Env()
e.transcript.write_text("{not json\n\x00\x01garbage\n")
check("malformed transcript: exit 0, silent", silent(e.run()), True)
check("malformed transcript on Stop: exit 0, silent", silent(e.run(event="Stop")), True)
e = Env()
check("missing transcript file: exit 0, silent", silent(e.run()), True)
check("malformed stdin: exit 0, silent", silent(e.run(raw="{nope")), True)
e = Env()
e.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": "x"}}}))
check("non-numeric usage: exit 0, silent", silent(e.run()), True)
e = Env()
e.write(usage_line(310_000))
check("no session_id: exit 0, silent",
      silent(e.run(raw=json.dumps({"transcript_path": str(e.transcript)}))), True)

# --- config ------------------------------------------------------------------
e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first_percent": 5, "step_percent": 1, "grace_minutes": 5}}))
check("config first_percent=5: 49,999 on a 1M window is silent",
      silent(e.at(49_999, now=T0 - 1)), True)
r = e.at(50_000, now=T0)
check("config first_percent=5: winds down at 50k", warned(r), True)
check("config threshold is named in the text", "~50k" in context(r[1]), True)
check("config grace_minutes=5 is named, with its timer",
      "at most 5 minutes" in context(r[1]) and "`sleep 300`" in context(r[1]), True)
check("config step_percent=1: 55k silent", silent(e.at(55_000, now=T0 + 1)), True)
check("config grace_minutes=5: silent at 4:59",
      silent(e.at(55_000, now=T0 + 5 * MIN - 1)), True)
check("config grace_minutes=5: deadline notice at 5:00",
      deadline(e.at(55_000, now=T0 + 5 * MIN)), True)
check("config step_percent=1: 60k winds down again",
      warned(e.at(60_000, now=T0 + 6 * MIN)), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps({"rules": {"context_handoff": False}}))
check("user config switches it off: silent at 500k", silent(e.at(500_000)), True)
check("user config switches it off: Stop is allowed", silent(e.run(event="Stop")), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first_percent": "lots", "step_percent": 0,
                         "grace_minutes": -3, "default_window": -1,
                         "windows": {"claude-opus": "big"}}}))
check("nonsense config values fall back to defaults: 299k silent",
      silent(e.at(299_000)), True)
r = e.at(300_000, now=T0)
check("nonsense config values fall back to defaults: 300k winds down", warned(r), True)
check("nonsense grace_minutes falls back to 15",
      "at most 15 minutes" in context(r[1]), True)
check("default grace holds: silent at 14:59",
      silent(e.at(301_000, now=T0 + 15 * MIN - 1)), True)
check("default grace holds: deadline notice at 15:00",
      deadline(e.at(301_000, now=T0 + 15 * MIN)), True)

for bad in (True, 2.5, "15", None):
    e = Env()
    (e.home / ".handrail.json").write_text(json.dumps(
        {"context_handoff": {"grace_minutes": bad}}))
    check("grace_minutes=%r falls back to 15" % (bad,),
          "at most 15 minutes" in context(e.at(300_000)[1]), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first_percent": 101}}))
check("first_percent over 100 falls back to 30: 300k winds down",
      warned(e.at(300_000)), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first_percent": 100}}))
check("first_percent=100 is kept: 999,999 on a 1M window is silent",
      silent(e.at(999_999)), True)
check("first_percent=100 is kept: 1M winds down", warned(e.at(1_000_000)), True)

def windows_env():
    e = Env()
    (e.home / ".handrail.json").write_text(json.dumps(
        {"context_handoff": {"windows": {"claude-haiku": 1_000_000,
                                         "claude-haiku-old": 100_000},
                             "default_window": 500_000}}))
    return e


e = windows_env()
check("config windows: a haiku given 1M is silent at 299k",
      silent(e.at(299_000, model="claude-haiku-4-5")), True)
check("config windows: and winds down at 300k",
      warned(e.at(300_000, model="claude-haiku-4-5")), True)
e = windows_env()
check("config windows: the longest matching key wins (100k window): 29,999 silent",
      silent(e.at(29_999, model="claude-haiku-old-1")), True)
check("config windows: the longest matching key wins (100k window): 30k winds down",
      warned(e.at(30_000, model="claude-haiku-old-1")), True)
e = windows_env()
check("config windows add to the default table: opus keeps 1M, 299k silent",
      silent(e.at(299_000)), True)
e = windows_env()
check("config default_window=500k: an unknown model winds down at 150k",
      silent(e.at(149_999, model="gpt-x")) and warned(e.at(150_000, model="gpt-x")),
      True)

# The hook keeps a copy of the defaults for a broken config module.
import importlib.util
import pathlib
import sys
_dir = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_dir))
import handrail_config
_spec = importlib.util.spec_from_file_location("hook", _dir / "context-handoff.py")
_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook)
check("the hook's fallback defaults match handrail_config",
      _hook.DEFAULTS, handrail_config.VALUE_DEFAULTS["context_handoff"])

e = Env()
(e.home / ".handrail.json").write_text("{broken")
check("unreadable config: defaults still wind down at 300k", warned(e.at(300_000)), True)

finish("input")
