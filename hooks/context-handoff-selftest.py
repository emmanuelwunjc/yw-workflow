#!/usr/bin/env python3
"""Self-test for context-handoff.py. Run it after any edit to that hook.

Each case writes a fake transcript, runs the hook on it the way Claude Code
does (JSON on stdin), and compares what reaches the model with what the owner
decided on 2026-09-30: a wind-down notice at 120k tokens, a deadline notice
when the grace for running subagents is over, and one Stop block while no
handoff has been written.

HOME points at a temp directory for the whole run, so the per-session state
file and any config are fixtures and never the real ones.

Time is passed in, never slept through. A case that needs a clock calls the
hook's main(stdin_text, now) through DRIVER. A case without one runs the
script itself, which is what Claude Code runs.

Run: ./hooks/context-handoff-selftest.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

HOOK = str(pathlib.Path(__file__).with_name("context-handoff.py"))
DRIVER = ("import importlib.util, sys\n"
          "spec = importlib.util.spec_from_file_location('hook', sys.argv[1])\n"
          "hook = importlib.util.module_from_spec(spec)\n"
          "spec.loader.exec_module(hook)\n"
          "sys.stdout.write(hook.main(sys.stdin.read(), float(sys.argv[2])))\n")
T0 = 1_790_000_000.0  # any fixed clock
MIN = 60

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
        self.cwd = self.tmp

    def write(self, *lines):
        self.transcript.write_text("\n".join(lines) + "\n")

    def run(self, session="s1", event="PostToolBatch", extra=None, raw=None,
            now=None):
        payload = {"session_id": session, "transcript_path": str(self.transcript),
                   "hook_event_name": event, "cwd": str(self.cwd)}
        payload.update(extra or {})
        env = dict(os.environ, HOME=str(self.home))
        cmd = ([sys.executable, HOOK] if now is None
               else [sys.executable, "-c", DRIVER, HOOK, str(now)])
        done = subprocess.run(cmd, cwd=self.cwd, env=env,
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        return done.returncode, done.stdout, done.stderr

    def at(self, tokens, **kw):
        self.write(user_line(), usage_line(tokens))
        return self.run(**kw)

    def stop(self, now, **extra):
        return self.run(event="Stop", now=now, extra=extra)

    def state(self, session="s1"):
        path = self.home / ".claude" / "state" / "context-handoff" / session
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}

    def git(self, *args, when=None):
        env = dict(os.environ, HOME=str(self.home), GIT_CONFIG_GLOBAL="/dev/null",
                   GIT_CONFIG_SYSTEM="/dev/null")
        if when is not None:
            stamp = "@%d +0000" % when
            env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=self.cwd, env=env, check=True, capture_output=True)

    def repo(self):
        """Make the session's cwd a git repo on main with one old commit."""
        self.cwd = self.tmp / "repo"
        (self.cwd / "docs").mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        (self.cwd / "a.py").write_text("x\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init", when=T0 - 9999)

    def commit_handoff(self, when):
        with (self.cwd / "docs" / "HANDOFF.md").open("a") as fh:
            fh.write("a line\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "docs: handoff", when=when)


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
    return code == 0 and "Wind down now" in context(out)


def deadline(result):
    code, out, _ = result
    return code == 0 and "grace for running subagents is over" in context(out)


def blocked(result):
    """The reason a Stop was blocked with, or "" when it was allowed."""
    code, out, _ = result
    try:
        body = json.loads(out)
    except ValueError:
        return ""
    return body.get("reason", "") if code == 0 and body.get("decision") == "block" else ""


def silent(result):
    code, out, err = result
    return code == 0 and out == "" and err == ""


# --- thresholds and steps ------------------------------------------------
e = Env()
check("119,999 tokens: below the threshold, silent", silent(e.at(119_999)), True)
r = e.at(120_000, now=T0)
check("120,000 tokens: at the threshold, winds down", warned(r), True)
text = context(r[1])
check("the notice names the size", "120k" in text, True)
check("the notice names the threshold", "~120k" in text, True)
check("the notice stops new work and new subagents",
      "Start no new work and spawn no new subagents" in text, True)
check("the notice gives running subagents the grace",
      "at most 15 minutes from now" in text, True)
check("the notice says how to come back at the deadline",
      "`sleep 900`" in text and "run_in_background" in text, True)
check("the notice says where the handoff goes",
      "handoff skill" in text and "docs/HANDOFF.md" in text
      and "## Handoff notes" in text, True)
check("the notice ends with a fresh session", "fresh session" in text, True)
check("the time of the notice is recorded", e.state().get("noticed"), T0)
check("150k, same step: no second notice", silent(e.at(150_000, now=T0 + 1)), True)
check("219,999: still step 0, silent", silent(e.at(219_999, now=T0 + 2)), True)
r = e.at(220_000, now=T0 + 3)
check("220k: next step, winds down again", warned(r), True)
check("220k notice names 220k", "220k" in context(r[1]), True)
check("the repeat restarts the clock", e.state().get("noticed"), T0 + 3)
check("250k: same step, silent", silent(e.at(250_000, now=T0 + 4)), True)
r = e.at(480_000, now=T0 + 5)
check("480k: jumps three steps, one notice", warned(r), True)
check("490k: same step, silent", silent(e.at(490_000, now=T0 + 6)), True)

# a different session keeps its own state
check("another session at 130k is told on its own", warned(e.at(130_000, session="s2")), True)

# after /compact the context drops; crossing again later is news again
e = Env()
check("compact: notice at 130k", warned(e.at(130_000, now=T0)), True)
check("compact: drop to 40k is silent", silent(e.at(40_000, now=T0 + 1)), True)
check("compact: below the threshold the wind-down is off",
      e.state().get("noticed"), None)
check("compact: no deadline notice for a session back under the line",
      silent(e.at(40_000, now=T0 + 99 * MIN)), True)
check("compact: and no Stop block", silent(e.stop(T0 + 99 * MIN)), True)
check("compact: back over 120k winds down again",
      warned(e.at(125_000, now=T0 + 100 * MIN)), True)

# --- the deadline ------------------------------------------------------------
e = Env()
e.at(130_000, now=T0)
check("deadline: one second early, silent",
      silent(e.at(131_000, now=T0 + 15 * MIN - 1)), True)
r = e.at(131_000, now=T0 + 15 * MIN)
check("deadline: at 15 minutes, the deadline notice", deadline(r), True)
text = context(r[1])
check("the deadline notice saves each subagent's work",
      "its last report, its branch and worktree path, any files" in text, True)
check("the deadline notice stops them with TaskStop", "TaskStop" in text, True)
check("the deadline notice says write the handoff now",
      "write the handoff now" in text, True)
check("deadline: said once", silent(e.at(132_000, now=T0 + 16 * MIN)), True)
check("deadline: still once an hour later",
      silent(e.at(133_000, now=T0 + 60 * MIN)), True)
code, out, _ = e.at(131_000, now=T0 + 61 * MIN, event="UserPromptSubmit")
check("deadline: not repeated on the other event either", out, "")

e = Env()
e.at(130_000, now=T0)
r = e.at(131_000, now=T0 + 15 * MIN, event="UserPromptSubmit")
check("deadline: arrives on UserPromptSubmit too",
      deadline(r) and output(r[1]).get("hookEventName") == "UserPromptSubmit", True)

# a step crossed after the deadline starts a new wind-down with its own grace
e = Env()
e.at(130_000, now=T0)
r = e.at(230_000, now=T0 + 20 * MIN)
check("a new step past the deadline is a wind-down notice",
      warned(r) and not deadline(r), True)
check("and its own deadline follows", deadline(e.at(231_000, now=T0 + 35 * MIN)), True)

# --- handoff already written ---------------------------------------------------
e = Env()
e.repo()
e.at(130_000, now=T0)
e.commit_handoff(when=T0 + 5 * MIN)
check("handoff committed after the notice: no deadline notice",
      silent(e.at(131_000, now=T0 + 15 * MIN)), True)
check("handoff committed after the notice: Stop is allowed",
      silent(e.stop(T0 + 16 * MIN)), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(130_000, now=T0)
check("handoff committed before the notice does not count: deadline notice",
      deadline(e.at(131_000, now=T0 + 15 * MIN)), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(130_000, now=T0)
check("handoff committed before the notice does not count: Stop blocks",
      bool(blocked(e.stop(T0 + 1))), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(130_000, now=T0)
(e.cwd / "docs" / "HANDOFF.md").write_text("being written\n")
check("an uncommitted handoff edit counts: Stop is allowed",
      silent(e.stop(T0 + 1)), True)
check("an uncommitted handoff edit counts: no deadline notice",
      silent(e.at(131_000, now=T0 + 15 * MIN)), True)

# --- the Stop check ------------------------------------------------------------
e = Env()
check("Stop with no state at all: allowed", silent(e.stop(T0)), True)
e.write(usage_line(100_000))
check("Stop below the threshold: allowed", silent(e.stop(T0)), True)
e.write(usage_line(130_000))
check("Stop past the threshold but before any notice: allowed",
      silent(e.stop(T0)), True)
check("and Stop itself gives no notice and records nothing",
      (e.home / ".claude" / "state" / "context-handoff" / "s1").exists(), False)

e = Env()
e.at(130_000, now=T0)
r = e.stop(T0 + 1, stop_hook_active=False)
reason = blocked(r)
check("Stop after the notice, no handoff: blocked", bool(reason), True)
check("the Stop block is exactly the documented shape",
      json.loads(r[1] or "{}"), {"decision": "block", "reason": reason})
check("the Stop block exits 0 and keeps stderr empty", (r[0], r[2]), (0, ""))
check("the reason repeats the instruction",
      "spawn no new subagents" in reason and "docs/HANDOFF.md" in reason
      and "## Handoff notes" in reason and "fresh session" in reason, True)
check("the reason lets a thread waiting on subagents stop again",
      "stop again" in reason, True)
check("Stop blocks once: the next Stop is allowed", silent(e.stop(T0 + 2)), True)
check("Stop blocks once: also after the deadline",
      silent(e.stop(T0 + 99 * MIN)), True)

e = Env()
e.at(130_000, now=T0)
check("stop_hook_active true: never blocked",
      silent(e.stop(T0 + 1, stop_hook_active=True)), True)
check("and that Stop did not use up the block",
      bool(blocked(e.stop(T0 + 2, stop_hook_active=False))), True)

e = Env()
e.at(130_000, now=T0)
running = [{"id": "t1", "type": "subagent", "status": "running"}]
check("inside the grace with background work in flight: Stop is allowed",
      silent(e.stop(T0 + 1, background_tasks=running)), True)
check("the same once the grace is over: blocked",
      bool(blocked(e.stop(T0 + 15 * MIN, background_tasks=running))), True)

e = Env()
e.at(130_000, now=T0)
reason = blocked(e.stop(T0 + 15 * MIN))
check("Stop after the deadline blocks with the deadline instruction",
      "grace for running subagents is over" in reason and "TaskStop" in reason, True)
check("and the deadline notice is not said a second time",
      silent(e.at(131_000, now=T0 + 16 * MIN)), True)

e = Env()
e.at(130_000, now=T0)
e.write(usage_line(130_000))
check("Stop inside a subagent (agent_id): allowed",
      silent(e.stop(T0 + 1, agent_id="a1")), True)

e = Env()
e.at(130_000, now=T0)
e.write(usage_line(40_000))
check("Stop after a /compact back under the threshold: allowed",
      silent(e.stop(T0 + 1)), True)

e = Env()
e.at(130_000, now=T0)
e.stop(T0 + 1)
e.at(230_000, now=T0 + 2)
check("a new step's wind-down can block one Stop of its own",
      bool(blocked(e.stop(T0 + 3))), True)

# the script itself, on the real clock: what Claude Code runs
e = Env()
e.at(130_000)
check("the notice time defaults to the real clock",
      abs((e.state().get("noticed") or 0) - time.time()) < 60, True)
r = e.run(event="Stop")
check("the script prints the Stop block", bool(blocked(r)), True)

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
check("synthetic: 130k winds down", warned(e.at(130_000)), True)
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
state_dir = e.home / ".claude" / "state" / "context-handoff"
state_dir.mkdir(parents=True)
old, fresh = state_dir / "old-session", state_dir / "fresh-session"
old.write_text("{}")
fresh.write_text("{}")
eight_days = 8 * 24 * 3600
os.utime(old, (os.path.getmtime(old) - eight_days,) * 2)
e.at(130_000)
check("state older than 7 days is removed when state is written", old.exists(), False)
check("recent state from another session is kept", fresh.exists(), True)

e = Env()
state_dir = e.home / ".claude" / "state" / "context-handoff"
state_dir.mkdir(parents=True)
(state_dir / "s1").write_text("not json")
check("an unreadable state file is treated as no state", warned(e.at(130_000)), True)
(state_dir / "s1").write_text('["a list"]')
check("a state file of the wrong shape is treated as no state",
      warned(e.at(130_000)), True)

# --- output shape ---------------------------------------------------------
e = Env()
code, out, _ = e.at(130_000, event="UserPromptSubmit")
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
e.write(usage_line(130_000))
check("no session_id: exit 0, silent",
      silent(e.run(raw=json.dumps({"transcript_path": str(e.transcript)}))), True)

# --- config ------------------------------------------------------------------
e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first": 50_000, "step": 10_000, "grace_minutes": 5}}))
r = e.at(50_000, now=T0)
check("config first=50k: winds down at 50k", warned(r), True)
check("config threshold is named in the text", "~50k" in context(r[1]), True)
check("config grace_minutes=5 is named, with its timer",
      "at most 5 minutes" in context(r[1]) and "`sleep 300`" in context(r[1]), True)
check("config step=10k: 55k silent", silent(e.at(55_000, now=T0 + 1)), True)
check("config grace_minutes=5: silent at 4:59",
      silent(e.at(55_000, now=T0 + 5 * MIN - 1)), True)
check("config grace_minutes=5: deadline notice at 5:00",
      deadline(e.at(55_000, now=T0 + 5 * MIN)), True)
check("config step=10k: 60k winds down again",
      warned(e.at(60_000, now=T0 + 6 * MIN)), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps({"rules": {"context_handoff": False}}))
check("user config switches it off: silent at 500k", silent(e.at(500_000)), True)
check("user config switches it off: Stop is allowed", silent(e.run(event="Stop")), True)

e = Env()
(e.home / ".handrail.json").write_text(json.dumps(
    {"context_handoff": {"first": "lots", "step": 0, "grace_minutes": -3}}))
check("nonsense config values fall back to defaults: 119k silent",
      silent(e.at(119_000)), True)
r = e.at(120_000, now=T0)
check("nonsense config values fall back to defaults: 120k winds down", warned(r), True)
check("nonsense grace_minutes falls back to 15",
      "at most 15 minutes" in context(r[1]), True)
check("default grace holds: silent at 14:59",
      silent(e.at(121_000, now=T0 + 15 * MIN - 1)), True)
check("default grace holds: deadline notice at 15:00",
      deadline(e.at(121_000, now=T0 + 15 * MIN)), True)

for bad in (True, 2.5, "15", None):
    e = Env()
    (e.home / ".handrail.json").write_text(json.dumps(
        {"context_handoff": {"grace_minutes": bad}}))
    check("grace_minutes=%r falls back to 15" % (bad,),
          "at most 15 minutes" in context(e.at(120_000)[1]), True)

e = Env()
(e.home / ".handrail.json").write_text("{broken")
check("unreadable config: defaults still wind down at 120k", warned(e.at(120_000)), True)

for f in failures:
    print(f)
print("context-handoff selftest: %d cases, %d failed" % (cases, len(failures)))
sys.exit(1 if failures else 0)
