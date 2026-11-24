#!/usr/bin/env python3
"""Shared fixtures for the context-handoff self-tests.

The self-tests are cut by topic into hooks/context-handoff-<topic>-selftest.py.
Each one imports this module, runs its cases through check(), and ends
with finish(). The name has no `-selftest.` in it, so the CI loop over
./hooks/*-selftest.* never runs this file on its own.

Each case writes a fake transcript, runs the hook on it the way Claude Code
does (JSON on stdin), and compares what reaches the model with what the owner
decided on 2026-09-30, with the line raised on 2026-11-20: a wind-down
notice at 300k tokens, a deadline notice
when the grace for running subagents is over, and one Stop block while no
handoff has been written.

Each Env() makes its own temp directory and points HOME at it, so every
case starts with a fresh per-session state file and config, and never
touches the real ones.

Time is passed in, never slept through. A case that needs a clock calls the
hook's main(stdin_text, now) through DRIVER. A case without one runs the
script itself, which is what Claude Code runs.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

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
            now=None, hook=HOOK):
        payload = {"session_id": session, "transcript_path": str(self.transcript),
                   "hook_event_name": event, "cwd": str(self.cwd)}
        payload.update(extra or {})
        env = dict(os.environ, HOME=str(self.home))
        cmd = ([sys.executable, hook] if now is None
               else [sys.executable, "-c", DRIVER, hook, str(now)])
        done = subprocess.run(cmd, cwd=self.cwd, env=env,
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        return done.returncode, done.stdout, done.stderr

    def at(self, tokens, **kw):
        self.write(user_line(), usage_line(tokens))
        return self.run(**kw)

    def stop(self, now, hook=HOOK, **extra):
        return self.run(event="Stop", now=now, extra=extra, hook=hook)

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


def finish(topic):
    for f in failures:
        print(f)
    print("context-handoff selftest (%s): %d cases, %d failed"
          % (topic, cases, len(failures)))
    sys.exit(1 if failures else 0)
