#!/usr/bin/env python3
"""Self-test for context-handoff.py: the Stop block, and a missing or broken
helper module.

Fixtures and check() live in context_handoff_testkit.py.

Run: ./hooks/context-handoff-stop-selftest.py
"""
import json
import pathlib
import shutil
import time

from context_handoff_testkit import (
    HOOK, MIN, T0, Env, blocked, check, finish, silent, usage_line, warned)

# --- a missing or broken helper module -------------------------------------------
# An install can lose handoff_touch.py or carry a broken one. The hook must still
# exit 0 silently, give the wind-down notice (it needs no detector), and never
# block a Stop or claim no handoff was written, since it cannot tell.
for label, helper in (("missing", None), ("raises", "raise RuntimeError('broken')\n")):
    e = Env()
    copy = e.tmp / "plugin"
    copy.mkdir()
    shutil.copy(HOOK, copy / "context-handoff.py")
    shutil.copy(pathlib.Path(HOOK).with_name("handrail_config.py"), copy)
    if helper:
        (copy / "handoff_touch.py").write_text(helper)
    hook = str(copy / "context-handoff.py")
    check("helper %s: the wind-down notice still arrives" % label,
          warned(e.at(130_000, now=T0, hook=hook)), True)
    check("helper %s: no deadline notice" % label,
          silent(e.at(131_000, now=T0 + 15 * MIN, hook=hook)), True)
    check("helper %s: Stop is allowed, silently" % label,
          silent(e.stop(T0 + 16 * MIN, hook=hook)), True)
    check("helper %s: the script itself exits 0 silently on Stop" % label,
          silent(e.run(event="Stop", hook=hook)), True)

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
e.repo()  # the repo wording names the branch and the PR body
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
check("the Stop block names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in reason, True)
check("the reason lets a thread waiting on subagents stop again",
      "stop again and wait for them" in reason, True)
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
check("the Stop block after the deadline names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in reason, True)
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

finish("stop")
