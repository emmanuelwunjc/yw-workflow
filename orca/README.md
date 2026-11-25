# The Orca workflow

Orca runs Claude Code sessions as workers, and an Orca bot is a chat that
starts and watches them. This folder holds the parts of yw-workflow that only
make sense inside Orca. Skill `pm` (in `skills/pm/`) runs one batch of tickets
through Orca workers. Skill `orca-bot` (in `skills/orca-bot/`) holds the rules
every bot follows. The loop below lets a bot keep a repo's free tickets moving
with no prompt.

## loop: the work loop of a bot

Skill `orca-loop` (`skills/orca-loop` links to `orca/loop`). Start at
[`loop/SKILL.md`](loop/SKILL.md). Each script takes `--project <name>`, a key
of [`loop/projects.json`](loop/projects.json), and needs `BOT_HOME`. Run every
test with `bash orca/loop/selftest.sh`.

Projects:

- [`loop/projects.json`](loop/projects.json): one entry per repo (repo, workspace root, labels, caps, rules).
- [`loop/projects.py`](loop/projects.py): reads it for the Python scripts.
- [`loop/project.sh`](loop/project.sh): reads it for the shell scripts, and takes `--project` and `--all-projects`.

Free work check:

- [`loop/free_tickets.py`](loop/free_tickets.py) and [`loop/free_tickets.sh`](loop/free_tickets.sh): every free ticket, best first, and the busy files.
- [`loop/slots.py`](loop/slots.py): how many workers the sweep may start now.
- [`loop/slot.sh`](loop/slot.sh): the re-count right before one start.
- [`loop/precheck.sh`](loop/precheck.sh): passes when a free ticket and a slot exist.

Sweep:

- [`loop/start-guard.sh`](loop/start-guard.sh): one sweep at a time starts workers.
- [`loop/start.sh`](loop/start.sh): starts one worker or reviewer, behind a lock per ticket or PR.
- [`loop/start-grill.sh`](loop/start-grill.sh): opens a grill chat on a ticket, one per ticket.
- [`loop/stall.sh`](loop/stall.sh): alarms when two sweeps in a row had free work and started nothing.
- [`loop/pr_wait.sh`](loop/pr_wait.sh): one line per open PR that waits on nobody.

Worker and reviewer specs:

- [`loop/worker-rules.txt`](loop/worker-rules.txt): the standing rules for every worker.
- [`loop/review-spec.sh`](loop/review-spec.sh): writes the two reviewer specs for a PR, from [`loop/reviewer-adversarial.txt`](loop/reviewer-adversarial.txt) and [`loop/reviewer-codereview.txt`](loop/reviewer-codereview.txt).
- [`loop/merge.sh`](loop/merge.sh): merges a PR after an independent pass.

Cleanup:

- [`loop/cleanup.sh`](loop/cleanup.sh): closes the terminals of finished workspaces, and with `--remove` removes held ones.
- [`loop/load.sh`](loop/load.sh): counts live terminals, to start a cleanup.
- [`loop/status-sync.sh`](loop/status-sync.sh): sets each workspace's sidebar status.

Tests:

- [`loop/selftest.sh`](loop/selftest.sh): runs every test below.
- [`loop/test-cleanup.sh`](loop/test-cleanup.sh), [`loop/test-free.sh`](loop/test-free.sh), [`loop/test-merge.sh`](loop/test-merge.sh), [`loop/test-pr-wait.sh`](loop/test-pr-wait.sh), [`loop/test-projects.sh`](loop/test-projects.sh), [`loop/test-review-spec.sh`](loop/test-review-spec.sh), [`loop/test-stall.sh`](loop/test-stall.sh), [`loop/test-start-guard.sh`](loop/test-start-guard.sh), [`loop/test-start.sh`](loop/test-start.sh), [`loop/test-start-grill.sh`](loop/test-start-grill.sh), [`loop/test-status.sh`](loop/test-status.sh): one per script, on fake projects, with no network.
