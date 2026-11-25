---
name: orca-loop
description: The Orca work loop for any repo listed in projects.json. A free work check lists the tickets a bot may start, a sweep starts one worker per free ticket inside the worker and PR caps, an open PR check finds PRs that wait on nobody, a stall alarm fires when free work starts nothing, and a cleanup closes the terminals of finished workspaces. Use when an Orca bot runs a check-in, a sweep, a cleanup, or starts a worker or reviewer for a project, or when the owner asks to "add a project to the loop".
---

# orca-loop

**In one line:** Lets an Orca bot run the work loop for any repo in `projects.json`: free work check, sweep, open PR check, cleanup. It lives in `orca/`, mapped in `orca/README.md`.

`<loop>` below is the folder that holds this file. Every script takes `--project <name>`, a key of `projects.json`. With one project in the file the flag is optional. With two or more, a script without it stops and names them. `cleanup.sh`, `status-sync.sh` and `load.sh` also take `--all-projects`.

Every script needs `BOT_HOME`, the bot's home folder (e.g. `~/.orca/bots/twenty`). Start locks live in `$BOT_HOME/locks`. The cleanup ledger and `starts.log` live in `$BOT_HOME/logs` (move them with `CLEANUP_LEDGER` and `STARTS_LOG`). The projects file is `PROJECTS_JSON`, else `$BOT_HOME/projects.json` when it exists, else `<loop>/projects.json` (a sample).

GitHub holds the state. A ticket waits only on a "blocked by" link or a label. Text such as "after #n" in an issue body holds nothing. Never write state into prose: no claim comments, no lists of who works on what.

## The files

| File | What it does |
|---|---|
| `projects.json`, `projects.py`, `project.sh` | One entry per project: repo, Orca repo id, workspace root, git dir, labels, worker cap, PR cap, review and worker rules. No script names a repo. |
| `free_tickets.py`, `free_tickets.sh` | Prints every free ticket, best first, and the files busy in open PRs and branches. It does not cut the list at the worker cap. |
| `slots.py`, `slot.sh`, `precheck.sh` | `SLOTS` = worker cap less held tickets less live workers. `slot.sh` re-counts right before a start. `precheck.sh` passes when there is a free ticket and a slot. |
| `start-guard.sh`, `start.sh`, `stall.sh`, `pr_wait.sh` | The sweep: one sweep at a time, a start lock per ticket, the stall alarm, the open PR check. |
| `review-spec.sh`, `reviewer-*.txt`, `worker-rules.txt`, `merge.sh` | Worker and reviewer specs, and the merge after a pass. |
| `cleanup.sh`, `load.sh`, `status-sync.sh` | Close finished workspaces (dry run unless `--apply`), the load check that starts a cleanup, and the sidebar status. |
| `test-*.sh`, `selftest.sh` | The tests. `bash <loop>/selftest.sh` runs them all on fake projects, with no network. |

The head comment of each script says what each output line means. Read it before you act on a line.

## Sweep

1. Run `python3 -I <loop>/slots.py --project <p>`. It prints the free work check, then the slot count. Read the `FREE:`, `BUSY:`, `NO SLICE:` and `SLOTS:` lines. With no `SLOTS:` line, or an error line, start nothing and report the error.
2. Owner waits: each open ticket with the project's `owner_wait` label gets one bot item with one ask. Do the owner-free prep first, so the answer is the only thing left.
3. Go down the `FREE:` lines in order. Read each ticket and name the files it changes. Drop it on a clash with a `BUSY:` file or a ticket kept before it, when it has a worker, or when it waits on the owner (add the `owner_wait` label). Stop at `SLOTS` kept tickets.
4. Take the guard: `bash <loop>/start-guard.sh take`. For each kept ticket: `gh issue develop --list` (a branch means another sweep took it), `gh issue develop <n> --name ticket-<n>`, `bash <loop>/slot.sh --project <p> <n>`, write the spec, then `bash <loop>/start.sh --project <p> <item|-> <spec> <n> <n>`. On a failed start, delete the `ticket-<n>` branch to free the ticket. Release the guard at the end.
5. Run `bash <loop>/stall.sh --project <p> <free> <started> <room> <explained>`. On a `STALL:` line, set the first free ticket's item to Needs you, once.
6. Run `bash <loop>/pr_wait.sh --project <p>`. Act on each `WAIT <pr> <reason>` line: `no-reviewer` and `fix-review` start reviewers from `review-spec.sh`, `conflict` starts one conflict worker, `idle` sets the item to Needs you.
7. Print one line per started ticket, one per dropped ticket with its reason, and one per WAIT action.

Comment on an item only when its state changes: a new question, a merge, a blocked or failed worker, or done.

## Cleanup

Run `bash <loop>/load.sh --all-projects` and `bash <loop>/cleanup.sh --all-projects` (a dry run). It prints `CLOSE` and `KEEP` lines with reasons, and writes them to the ledger. Close with `--apply`. Remove clean, retired, held workspaces with `--apply --remove`. A worker's `worker_done` carries `kind: pr|report|review`, and the kind decides when its terminal may close.

## Add a project

1. Find the labels the repo uses for work tickets, owner waits and grills (`gh label list -R <repo>`).
2. Add an entry to the projects file the scripts read (see the top of this file), with the keys of the `twenty` entry. No script reads `live_agent_cap`, `labels.grill` or `gcp` yet. Put project rules in the file its `worker_rules` key names, never in `worker-rules.txt`.
3. Dry run: `bash <loop>/free_tickets.sh --project <p>` and `bash <loop>/cleanup.sh --project <p>` print a list with no error.

## Lessons (2026-11-24)

- List every candidate. Cap only the starts. A list cut at the worker cap held five unstartable tickets, and the sweep started nothing for hours while 32 were free.
- A gh error must never read as a number. `$(gh ... || echo 0)` captures the error JSON and then the `0`.
- Test with the real field formats of `orca worktree ps`: prompts cut to 200 characters, branch as `refs/heads/<name>`.
- A squash-merged branch's old commits exist on no remote, so "is this commit pushed" is the wrong test for a merged branch.
- `timeout` does not exist on macOS.
