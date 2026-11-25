# Handoff

## Start here

You are a fresh session. This file and the repo's open tickets are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Run the repo's free work check, the command its `CLAUDE.md` names. It
   prints the tickets that may start now, first one first. The repo names
   no free work check: read `## Next` in this file for the tasks, and go
   to step 4.
3. Take tickets. The owner named one: take it. If the check does not print
   it, tell the owner why, and stop. Else take the first two to four the
   check prints. It prints none: tell the owner, and stop. Take each
   ticket with a branch linked to it, in its own worktree (`git-worktrees`):
   `gh issue develop <N> --name <type>/<N>-<short> --base <trunk> --checkout --worktree .worktrees/<NN>-<short>`
   The linked branch marks the ticket taken. If gh refuses, change
   nothing, stop, and tell the owner. Then run `gh issue develop --list <N>`.
   It lists a branch other than yours: another session took the ticket at
   the same time. Delete your branch on GitHub and your worktree, and take
   the next ticket.
4. Read `## Now` in this file. Run the recount commands before trusting
   any number. Start more tickets as earlier ones merge. Ask the owner
   nothing that this file or the tickets answer.

A ticket's state lives on GitHub, never in this file. A "blocked by" link
holds it back. The label `needs-owner` or `wayfinder:grilling` makes it
wait. A linked branch marks it taken. When you stop with a ticket not
finished, push its branch and comment on the ticket where the work stopped.
Delete the branch only when it holds no work: that frees the ticket.
Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.

## Now

This repo is Yiming's engineering workflow, packaged as a Claude Code
plugin. `README.md` says what each skill and hook does, and `docs/HOOKS.md`
holds the full hook rules. The counts live in the README, and
`tools/check-repo.py` checks them against the skills on every run.

The gate is these commands. CI (`.github/workflows/ci.yml`) runs the first
two, word for word:

```bash
(for t in ./hooks/*-selftest.*; do "$t" || exit 1; done)  # do the guards work
./tools/check-repo.py                 # do the repo checks pass
git log --oneline main..HEAD          # what is unmerged
claude plugin validate .              # whether it installs
npx skills add . -l                   # what the skills path would serve
```

- **Lane issues are retired** (2026-11-24, #228). A ticket's state lives on
  GitHub, as the Start here block says. Some `lane` issues are still open
  until their steps move to tickets: `gh issue list --label lane --state open`.
- **This repo names no free work check.** It has no root `CLAUDE.md` yet.
  So step 2 of the block sends a session to `## Next` below. #238 (move the
  Orca free-work, sweep and cleanup scripts into this repo) brings one.
- **The handoff layout is short now** (map #193). This file holds only the
  block, `## Now`, `## Next` and `## Read next`. A decision that passes the
  three ADR tests goes to `docs/adr/`. `docs/DECISIONS.md` is frozen.
- **Every PR raises the plugin version.** Each merge makes the next open
  branch rebase and take the next version. Before you bump, read the version
  on trunk: `git show origin/main:.claude-plugin/plugin.json`.

## Next

1. `parallel`: finish the lane retirement. For each open `lane` issue,
   copy each `## Next` step that is still open to its ticket as a comment,
   or open a ticket for it. Make each "after #X" a "blocked by" link. Then
   close the lane issue with a pointer to where its steps went. List them:
   `gh issue list --label lane --state open`.
2. `parallel`: the rest of handoff layer 3 (#196). #202: each of the 9
   old traps gets a check, a ticket or a `LESSONS.md` line, and its
   comment says where each went. #200: the Handoff docs part of
   `~/CLAUDE.md`.
3. `after the owner reads this file`: #204 (move twenty,
   sals-day-in-life-dryrun and reimburse to this layout).
4. `parallel`: any other open ticket with no linked branch, no open
   blocker, and no `needs-owner` or `wayfinder:grilling` label:
   `gh issue list --state open --json number,title,labels`.

Waits on the owner:

- **Read this file, the pilot of the short layout, and say go or change
  for #204.**
- #159 (a CI step that runs recorded mutations) adds to a workflow. Ask
  before you add it.

## Read next

- `docs/adr/`: one file per decision, and why it went that way.
- `docs/DECISIONS.md`: older decisions and measurements, frozen on
  2026-11-24.
- `gh pr list --state merged --limit 50`: what merged. Each PR body's
  `## Handoff notes` says why.
- `git log -p -- docs/HANDOFF.md`: every earlier version of this file.
