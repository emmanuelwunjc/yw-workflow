---
name: feedback-tell-agent-not-owner
description: Detail that only an agent acts on goes to that agent, never into the Home Chat reply to the owner.
metadata:
  type: feedback
---

When something is a note, a caveat or an instruction for a worker or another bot, send it to that agent with `orca orchestration send`, or put it on its item. Leave it out of the Home Chat reply.

**Why:** Owner, 2026-11-24: "Don't tell me, tell the agent." The Home Chat is for what the owner must read or decide. Worker caveats, mechanism detail and test counts are noise there.

**How to apply:** A Home Chat reply holds the outcome, what changed and what waits on the owner, as one digest per turn. Corrections, open nits and "check X" notes go to the worker. Related: [[feedback-delegate-fixes]].
