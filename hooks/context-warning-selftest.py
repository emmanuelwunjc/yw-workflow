#!/usr/bin/env python3
"""Self-test for context-warning.py. Run it after any edit to that hook.

Each case writes a fake transcript, runs the hook on it the way Claude Code
does (JSON on stdin), and compares what reaches the model with what the owner
decided on 2026-09-21: one warning at 120k tokens, then one per 100k step.

HOME points at a temp directory for the whole run, so the per-session state
file and any config are fixtures and never the real ones.

Run: ./hooks/context-warning-selftest.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HOOK = str(pathlib.Path(__file__).with_name("context-warning.py"))

failures = []
cases = 0


def usage_line(tokens, sidechain=False):
    """One assistant transcript line whose three input fields sum to tokens."""
    return json.dumps({
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "usage": {
            "input_tokens": 4,
            "cache_creation_input_tokens": 1000,
            "cache_read_input_tokens": tokens - 1004,
            "output_tokens": 999999,  # never part of the context size
        }},
    })


def user_line():
    return json.dumps({"type": "user", "message": {"role": "user", "content": "x"}})


class Env:
    def __init__(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.transcript = self.tmp / "t.jsonl"

    def write(self, *lines):
        self.transcript.write_text("\n".join(lines) + "\n")

    def run(self, session="s1", event="PostToolBatch", extra=None, raw=None):
        payload = {"session_id": session, "transcript_path": str(self.transcript),
                   "hook_event_name": event, "cwd": str(self.tmp)}
        payload.update(extra or {})
        env = dict(os.environ, HOME=str(self.home))
        done = subprocess.run([sys.executable, HOOK], cwd=self.tmp, env=env,
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        return done.returncode, done.stdout, done.stderr

    def at(self, tokens, **kw):
        self.write(user_line(), usage_line(tokens))
        return self.run(**kw)


def check(name, got, want):
    global cases
    cases += 1
    if got != want:
        failures.append("FAIL %s: want %r, got %r" % (name, want, got))


def context(stdout):
    """The text that reaches the model, or "" when the hook said nothing."""
    return output(stdout).get("additionalContext", "")


def output(stdout):
    """The hookSpecificOutput object, or {} when there is none or it is not JSON."""
    try:
        return json.loads(stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return {}


def warned(result):
    code, out, _ = result
    return code == 0 and "Context is at" in context(out)


def silent(result):
    code, out, err = result
    return code == 0 and out == "" and err == ""


# --- thresholds and steps ------------------------------------------------
e = Env()
check("119,999 tokens: below the threshold, silent", silent(e.at(119_999)), True)
r = e.at(120_000)
check("120,000 tokens: at the threshold, warns", warned(r), True)
check("the warning names the size", "120k" in context(r[1]), True)
check("the warning names the threshold", "~120k" in context(r[1]), True)
check("the warning says to run the handoff pass",
      "handoff pass" in context(r[1]) and "fresh session" in context(r[1]), True)
check("the warning waits for running agents",
      "agents you are waiting on" in context(r[1]), True)
check("150k, same step: no second warning", silent(e.at(150_000)), True)
check("219,999: still step 0, silent", silent(e.at(219_999)), True)
r = e.at(220_000)
check("220k: next step, warns", warned(r), True)
check("220k warning names 220k", "220k" in context(r[1]), True)
check("250k: same step, silent", silent(e.at(250_000)), True)
r = e.at(480_000)
check("480k: jumps three steps, warns once", warned(r), True)
check("490k: same step, silent", silent(e.at(490_000)), True)

# a different session keeps its own state
check("another session at 130k warns on its own", warned(e.at(130_000, session="s2")), True)

# after /compact the context drops; crossing again later is news again
e = Env()
check("compact: warn at 130k", warned(e.at(130_000)), True)
check("compact: drop to 40k is silent", silent(e.at(40_000)), True)
check("compact: back over 120k warns again", warned(e.at(125_000)), True)

# --- which usage counts --------------------------------------------------
e = Env()
e.write(usage_line(300_000), user_line(), usage_line(50_000))
check("the most recent assistant usage is the size", silent(e.run()), True)

e = Env()
e.write(usage_line(130_000), usage_line(900_000, sidechain=True))
r = e.run()
check("a sidechain line is skipped; the main-thread one counts",
      warned(r) and "130k" in context(r[1]), True)

e = Env()
e.write(usage_line(130_000))
check("inside a subagent (agent_id present): silent",
      silent(e.run(extra={"agent_id": "a1"})), True)
check("the subagent call did not use up the step",
      warned(e.run()), True)

# Claude Code writes synthetic assistant lines (API errors, usage-limit notices,
# "No response requested.") with every usage field 0. Read as a size, one looks
# like a /compact and the same step warns twice.
def synthetic_line(model="<synthetic>"):
    return json.dumps({"type": "assistant", "isSidechain": False, "message": {
        "model": model, "role": "assistant", "usage": {
            "input_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": 0}}})


e = Env()
check("synthetic: 130k warns", warned(e.at(130_000)), True)
e.write(usage_line(130_000), synthetic_line())
check("synthetic: a <synthetic> line after it is silent", silent(e.run()), True)
e.write(usage_line(130_000), synthetic_line(), usage_line(135_000))
check("synthetic: 135k after it stays silent, same step", silent(e.run()), True)
e.write(usage_line(135_000), synthetic_line(model="claude-opus-5"))
check("a zero-sum line from a real model is skipped too", silent(e.run()), True)
e.write(usage_line(140_000))
check("after the zero lines, 140k is still the same step", silent(e.run()), True)
e = Env()
e.write(usage_line(130_000), synthetic_line())
r = e.run()
check("synthetic last: the real line before it is the size",
      warned(r) and "130k" in context(r[1]), True)

# --- state cleanup -----------------------------------------------------------
e = Env()
state_dir = e.home / ".claude" / "state" / "context-warning"
state_dir.mkdir(parents=True)
old, fresh = state_dir / "old-session", state_dir / "fresh-session"
old.write_text("0")
fresh.write_text("0")
eight_days = 8 * 24 * 3600
os.utime(old, (os.path.getmtime(old) - eight_days,) * 2)
e.at(130_000)
check("state older than 7 days is removed when state is written", old.exists(), False)
check("recent state from another session is kept", fresh.exists(), True)

# --- output shape ---------------------------------------------------------
e = Env()
code, out, _ = e.at(130_000, event="UserPromptSubmit")
check("hookEventName echoes the event that fired",
      output(out).get("hookEventName"), "UserPromptSubmit")

# --- never fail the turn ---------------------------------------------------
e = Env()
e.transcript.write_text("{not json\n\x00\x01garbage\n")
check("malformed transcript: exit 0, silent", silent(e.run()), True)
e = Env()
check("missing transcript file: exit 0, silent", silent(e.run()), True)
check("malformed stdin: exit 0, silent", silent(e.run(raw="{nope")), True)
e = Env()
e.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": "x"}}}))
check("non-numeric usage: exit 0, silent", silent(e.run()), True)
e = Env()
e.write(usage_line(130_000))
check("no session_id: exit 0, silent",
      silent(e.run(raw=json.dumps({"transcript_path": str(e.transcript)}))), True)

# --- config ------------------------------------------------------------------
e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_warning": {"first": 50_000, "step": 10_000}}))
r = e.at(50_000)
check("config first=50k: warns at 50k", warned(r), True)
check("config threshold is named in the text", "~50k" in context(r[1]), True)
check("config step=10k: 55k silent", silent(e.at(55_000)), True)
check("config step=10k: 60k warns", warned(e.at(60_000)), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps({"rules": {"context_warning": False}}))
check("user config switches it off: silent at 500k", silent(e.at(500_000)), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_warning": {"first": "lots", "step": 0}}))
check("nonsense config values fall back to defaults: 119k silent",
      silent(e.at(119_000)), True)
check("nonsense config values fall back to defaults: 120k warns",
      warned(e.at(120_000)), True)

e = Env()
(e.home / ".handrail.json").write_text("{broken")
check("unreadable config: defaults still warn at 120k", warned(e.at(120_000)), True)

for f in failures:
    print(f)
print("context-warning selftest: %d cases, %d failed" % (cases, len(failures)))
sys.exit(1 if failures else 0)
