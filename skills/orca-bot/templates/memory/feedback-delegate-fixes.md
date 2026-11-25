---
name: feedback-delegate-fixes
description: Every edit, test or script change goes to a worker, even a small one in my own skills, so my context stays for coordinating.
metadata:
  type: feedback
---

Send every edit, test run and script change to a worker. This includes files in my own home, e.g. a script in my `skills/` folder. I do reads, status and digests myself.

**Why:** Owner, 2026-11-23: a bot that fixed six small items itself was told to send an agent instead. My context is for coordinating, and edits and tests fill it fast.

**How to apply:** Start a worker with `orca orchestration worker-start` for any change to a file. Close the worker's terminal after its `worker_done`. Never close one that still waits. Related: [[feedback-tell-agent-not-owner]].
