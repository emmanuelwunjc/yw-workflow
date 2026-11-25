#!/usr/bin/env python3
"""Self-test for context-handoff.py: the wind-down and deadline notices,
and when a written handoff silences them.

Fixtures and check() live in context_handoff_testkit.py.

Run: ./hooks/context-handoff-notices-selftest.py
"""
from context_handoff_testkit import (
    MIN, T0, Env, blocked, check, context, deadline, finish,
    output, silent, warned)

# --- thresholds and steps ------------------------------------------------
e = Env()
e.repo()  # the repo wording names the branch and the PR body
check("120k, the old line: silent", silent(e.at(120_000)), True)
check("299,999 tokens: below the threshold, silent", silent(e.at(299_999)), True)
r = e.at(300_000, now=T0)
check("300,000 tokens: at the threshold, winds down", warned(r), True)
text = context(r[1])
check("the notice names the size", "300k" in text, True)
check("the notice names the threshold", "~300k" in text, True)
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
check("the notice names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in text, True)
check("the notice hands an unfinished ticket off on GitHub",
      "push its branch and comment on the ticket" in text, True)
check("the notice names no retired lane script (#228)",
      "lane_claim" in text, False)
check("the time of the notice is recorded", e.state().get("noticed"), T0)
check("330k, same step: no second notice", silent(e.at(330_000, now=T0 + 1)), True)
check("399,999: still step 0, silent", silent(e.at(399_999, now=T0 + 2)), True)
r = e.at(400_000, now=T0 + 3)
check("400k: next step, winds down again", warned(r), True)
check("400k notice names 400k", "400k" in context(r[1]), True)
check("the repeat restarts the clock", e.state().get("noticed"), T0 + 3)
check("430k: same step, silent", silent(e.at(430_000, now=T0 + 4)), True)
r = e.at(660_000, now=T0 + 5)
check("660k: jumps three steps, one notice", warned(r), True)
check("670k: same step, silent", silent(e.at(670_000, now=T0 + 6)), True)

# a different session keeps its own state
check("another session at 310k is told on its own", warned(e.at(310_000, session="s2")), True)

# after /compact the context drops; crossing again later is news again
e = Env()
check("compact: notice at 310k", warned(e.at(310_000, now=T0)), True)
check("compact: drop to 40k is silent", silent(e.at(40_000, now=T0 + 1)), True)
check("compact: below the threshold the wind-down is off",
      e.state().get("noticed"), None)
check("compact: no deadline notice for a session back under the line",
      silent(e.at(40_000, now=T0 + 99 * MIN)), True)
check("compact: and no Stop block", silent(e.stop(T0 + 99 * MIN)), True)
check("compact: back over 300k winds down again",
      warned(e.at(305_000, now=T0 + 100 * MIN)), True)

# --- the line is 30% of the session's window (#208) -------------------------
# The window comes from the model id on the last assistant message.
e = Env()
check("200k window: 59,999 is silent",
      silent(e.at(59_999, model="claude-haiku-4-5-20251001", now=T0)), True)
r = e.at(60_000, model="claude-haiku-4-5-20251001", now=T0 + 1)
check("200k window: 60k (30%) winds down", warned(r), True)
check("200k window: the notice names ~60k", "~60k" in context(r[1]), True)
check("200k window: 79,999 is the same step, silent",
      silent(e.at(79_999, model="claude-haiku-4-5-20251001", now=T0 + 2)), True)
check("200k window: 80k is the next step (10%), winds down again",
      warned(e.at(80_000, model="claude-haiku-4-5-20251001", now=T0 + 3)), True)

e = Env()
check("a 200k-window session at 190k gets the notice (the #208 case)",
      warned(e.at(190_000, model="claude-haiku-4-5-20251001")), True)
e = Env()
check("Sonnet has a 1M window: 299,999 is silent",
      silent(e.at(299_999, model="claude-sonnet-5-5", now=T0)), True)
check("Sonnet has a 1M window: 300k winds down",
      warned(e.at(300_000, model="claude-sonnet-5-5", now=T0 + 1)), True)

e = Env()
check("an unknown model falls back to a 200k window: 59k silent",
      silent(e.at(59_000, model="gpt-x", now=T0)), True)
check("an unknown model falls back to a 200k window: 60k winds down",
      warned(e.at(60_000, model="gpt-x", now=T0 + 1)), True)
e = Env()
check("no model on the line: the 200k fallback too",
      warned(e.at(60_000, model=None)), True)

e = Env()
check("switching to a smaller window past its line winds down",
      silent(e.at(150_000, now=T0)) and warned(
          e.at(150_000, model="claude-haiku-4-5-20251001", now=T0 + 1)), True)

# --- the deadline ------------------------------------------------------------
e = Env()
e.at(310_000, now=T0)
check("deadline: one second early, silent",
      silent(e.at(311_000, now=T0 + 15 * MIN - 1)), True)
r = e.at(311_000, now=T0 + 15 * MIN)
check("deadline: at 15 minutes, the deadline notice", deadline(r), True)
text = context(r[1])
check("the deadline notice saves each subagent's work",
      "its last report, its branch and worktree path, any files" in text, True)
check("the deadline notice stops them with TaskStop", "TaskStop" in text, True)
check("the deadline notice says write the handoff now",
      "write the handoff now" in text, True)
check("the deadline notice says what the check cannot see",
      "This check sees only docs/HANDOFF.md" in text, True)
check("deadline: said once", silent(e.at(312_000, now=T0 + 16 * MIN)), True)
check("deadline: still once an hour later",
      silent(e.at(313_000, now=T0 + 60 * MIN)), True)
code, out, _ = e.at(311_000, now=T0 + 61 * MIN, event="UserPromptSubmit")
check("deadline: not repeated on the other event either", out, "")

e = Env()
e.at(310_000, now=T0)
r = e.at(311_000, now=T0 + 15 * MIN, event="UserPromptSubmit")
check("deadline: arrives on UserPromptSubmit too",
      deadline(r) and output(r[1]).get("hookEventName") == "UserPromptSubmit", True)

# a step crossed after the deadline starts a new wind-down with its own grace
e = Env()
e.at(310_000, now=T0)
r = e.at(410_000, now=T0 + 20 * MIN)
check("a new step past the deadline is a wind-down notice",
      warned(r) and not deadline(r), True)
check("and its own deadline follows", deadline(e.at(411_000, now=T0 + 35 * MIN)), True)

# --- handoff already written ---------------------------------------------------
e = Env()
e.repo()
e.at(310_000, now=T0)
e.commit_handoff(when=T0 + 5 * MIN)
check("handoff committed after the notice: no deadline notice",
      silent(e.at(311_000, now=T0 + 15 * MIN)), True)
check("handoff committed after the notice: Stop is allowed",
      silent(e.stop(T0 + 16 * MIN)), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(310_000, now=T0)
check("handoff committed before the notice does not count: deadline notice",
      deadline(e.at(311_000, now=T0 + 15 * MIN)), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(310_000, now=T0)
check("handoff committed before the notice does not count: Stop blocks",
      bool(blocked(e.stop(T0 + 1))), True)

e = Env()
e.repo()
e.commit_handoff(when=T0 - 5 * MIN)
e.at(310_000, now=T0)
(e.cwd / "docs" / "HANDOFF.md").write_text("being written\n")
check("an uncommitted handoff edit counts: Stop is allowed",
      silent(e.stop(T0 + 1)), True)
check("an uncommitted handoff edit counts: no deadline notice",
      silent(e.at(311_000, now=T0 + 15 * MIN)), True)

e = Env()
e.repo()
e.at(310_000, now=T0)
e.git("checkout", "-q", "-b", "docs/handoff-x")
e.commit_handoff(when=T0 + 5 * MIN)
e.git("checkout", "-q", "main")
check("handoff committed on another branch after the notice: Stop is allowed",
      silent(e.stop(T0 + 6 * MIN)), True)

e = Env()
e.repo()
e.at(310_000, now=T0)
(e.cwd / "docs" / "HANDOFF.md").write_text("new, untracked\n")
check("a new untracked docs/HANDOFF.md counts: Stop is allowed",
      silent(e.stop(T0 + 1)), True)

# the branch case: the notes may be in a PR body the check cannot read
e = Env()
e.repo()
e.at(310_000, now=T0)
reason = blocked(e.stop(T0 + 1))
check("in a git repo the block says the notes may be in the PR body",
      "already in the PR body" in reason, True)
e = Env()
e.repo()
e.at(310_000, now=T0)
text = context(e.at(311_000, now=T0 + 15 * MIN)[1])
check("in a git repo the deadline notice names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in text, True)

# a plain folder: no repo, so no branch and no PR body either
e = Env()
text = context(e.at(310_000, now=T0)[1])
check("in a plain folder the wind-down notice never mentions a PR body",
      "PR body" not in text and "docs/handoff-" not in text, True)
check("in a plain folder the notice names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in text, True)
reason = blocked(e.stop(T0 + 1))
check("in a plain folder the block says it is no git repo",
      "not a git repo" in reason, True)
check("in a plain folder the block names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in reason, True)
check("in a plain folder the block never mentions a PR body",
      "PR body" not in reason and "docs/handoff-" not in reason, True)
text = context(e.at(311_000, now=T0 + 15 * MIN)[1])
check("in a plain folder the deadline notice says it is no git repo",
      "not a git repo" in text, True)
check("in a plain folder the deadline notice names the skill with its plugin prefix",
      "load the yw-workflow:handoff skill" in text, True)
check("in a plain folder the deadline notice never mentions a PR body",
      "PR body" not in text and "docs/handoff-" not in text, True)

finish("notices")
