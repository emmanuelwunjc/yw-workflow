---
name: handoff
description: Keep a repo's docs/HANDOFF.md in the one shape that lets a fresh session start from the file and the repo's open tickets alone, with a Start here block on top that runs the repo's free work check and takes free tickets, and dated sections added by a handoff pass after merges, from the Handoff notes each PR carries. Use when asked for "a handoff", "/handoff", "write the handoff", "update the handoff", at the close of a session, or when the handoff-freshness hook warns HANDOFF STALE or HANDOFF SHAPE. A progress tracker with progress bars is skill goal-tracker.
origin: authored
tags: [handoff, docs, session, continuity]
version: 2.0.0
---

# Handoff

**In one line:** Keeps `docs/HANDOFF.md` in the shape that lets a fresh session start from it and the open tickets alone.

Say that line back when you start, so whoever invoked this knows what they
got.

**If `mattpocock-skills:handoff` loaded with this skill, this skill wins.**
Two installed plugins each carry a skill named `handoff`. The Plugin row of
the Claude Code skills page (https://code.claude.com/docs/en/skills, "Choose
where skills load") says a skill at `<plugin>/skills/<skill-name>/SKILL.md`
loads "Wherever the plugin is enabled, as `/plugin-name:skill-name`". So both
load, as `yw-workflow:handoff` and `mattpocock-skills:handoff`. That page does
not say which of the two a bare `/handoff` runs. The other skill says: "Save to
the temporary directory of the user's OS (`$TMPDIR`, else `/tmp`; `%TEMP%` on
Windows)". That temp-folder file loses. The handoff goes to `docs/HANDOFF.md`,
or to a PR's `## Handoff notes`, as the rules below say.

A handoff exists so the next session starts working without anyone composing
an opening prompt. The owner decided on 2026-09-16 that pointing a fresh agent
at `docs/HANDOFF.md` is the whole prompt. Its Start here block sends the
session to the repo's free work check, which prints the tickets that may
start now. That holds only if every handoff has the same shape, so this skill
is the shape, and `hooks/handoff-freshness.py` warns when a repo drifts from it.

This skill never emits a separate prompt for the next session. The file and
the tickets are the prompt. If you find yourself writing "paste this to
start the next session", stop and put the task in a ticket instead.

**A ticket's state lives in GitHub features, never in text that goes stale.**
The owner decided this on 2026-11-23, in the grill of
georgetown-mdi-gates4/twenty#672, and it retired lane issues here (#228):

- A **blocker** is an open issue that a ticket links as "blocked by" on
  GitHub. Only that link holds a ticket back. "Blocked by #n" or "after #n"
  in a body is a note.
- A ticket **waits** while it has the label `needs-owner` (the owner's yes
  or choice) or `wayfinder:grilling` (it needs a grill first).
- A ticket is **taken** while a branch is linked to it with
  `gh issue develop`. Deleting the branch frees the ticket.
- The **free work check** is the repo's command that prints each ticket
  that may start now: open, no open blocker, not waiting, not taken. The
  repo's `CLAUDE.md` names it. Each repo writes its own, since order and
  caps differ, e.g. twenty orders by its `slice:` labels.

Before 2026-11-24, each open lane of work had a `lane` issue with a
`Held by:` line and a `## Next` list, claimed with `scripts/lane_claim.py`.
That text went stale and held back every ticket its list did not name. The
reasons are in yw-workflow `docs/DECISIONS.md`, 2026-11-24.

The goal tracker of skill `goal-tracker` shows a goal's progress. A request
about a progress tracker, its progress bars or its "tracker style" goes to
that skill. "The tracker" alone can mean GitHub Issues, so ask which one.

## The top of the file

Paste this block verbatim at the top of `docs/HANDOFF.md`, above everything
else, and leave it alone afterwards:

```
# Handoff

## Start here

You are a fresh session. This file and the repo's open tickets are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Run the repo's free work check, the command its `CLAUDE.md` names. It
   prints the tickets that may start now, first one first. The repo names
   no free work check: read the LAST section of this file for the tasks,
   and go to step 4.
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
4. Read the recent sections of this file for traps. Run the recount
   commands before trusting any number. Start more tickets as earlier ones
   merge. Ask the owner nothing that this file or the tickets answer.

A ticket's state lives on GitHub, never in this file. A "blocked by" link
holds it back. The label `needs-owner` or `wayfinder:grilling` makes it
wait. A linked branch marks it taken. When you stop with a ticket not
finished, push its branch and comment on the ticket where the work stopped.
Delete the branch only when it holds no work: that frees the ticket.
Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
```

## The rules

- **One committed file for the log, one ticket per piece of work.**
  `docs/HANDOFF.md` holds the decisions, traps and judgment that every
  branch shares. A ticket holds its own task. Never `/tmp`, never a
  scratchpad, never a second file named `HANDOFF.md` or `AGENT_HANDOFF.md`
  somewhere else: two log files means the next session reads the wrong one.
- **A next step is a ticket, or a comment on the ticket it names.** An
  order between two tickets is a "blocked by" link, set on the ticket that
  waits. A question for the owner is the label `needs-owner` on the ticket
  it holds back. Never a list in a body that someone must keep up to date.
- **Write it down as you go, in the PR body.** Every decision, defect and
  trap that cost time gets a few lines when it happens. A handoff written at
  close comes from a compacted memory, and the reasoning drops out first.
- **Before any session stops, the builder, fixer and documenter worktrees it
  started hold no uncommitted work.** That is each Agent-tool worktree it dispatched
  and each worktree it made. For each one with uncommitted work, message its
  agent to commit it as WIP on its own branch. On a detached HEAD, that
  means `git switch -c wip/<folder>` first, with the worktree's folder name.
  If no agent can take the message, commit it yourself the same way. Name
  the branch, with `git log -1 <branch>` as its recount command. Put the
  name in a comment on the ticket the work is for. Else put it in the open
  PR's `## Handoff notes`. Else put it in the final reply to the owner. If
  no commit is possible, name the worktree path, its branch and
  "uncommitted work" in the same place. Leave other worktrees as they are.
  Do not write any of this into `docs/HANDOFF.md`: only a handoff pass
  edits it.
- **Only a handoff branch edits `docs/HANDOFF.md`.** Any other branch writes
  its notes in a `## Handoff notes` section of its PR body. The owner
  decided this on 2026-09-21: when every concurrent branch appended to the
  log, every branch hit a merge conflict in it. A repo can enforce it in CI
  by failing any other branch that touches the file. One exception: a
  change to the Start here block itself edits `docs/HANDOFF.md` on any
  branch. The HANDOFF NOTES warning on that branch is expected.
- **Dated sections, `## YYYY-MM-DD: what happened`, newest last.** The
  reader scrolls to the end and finds the present. The dated closing
  section is always the final `##` heading in the file, below any
  topic-grouped sections such as traps or decisions. The block reads it
  when the repo names no free work check.
- **The closing section is the briefing of a repo with no free work
  check.** It names, in this order:
  1. The tasks to work, each marked `parallel` or `after <item>`, e.g.
     `#186 (the mutation list is data), parallel` and
     `#187 (the writer reads the list), after #186`. An item with no mark
     is `parallel` unless it names another item it depends on. Where the
     tasks are tickets, set the order as a "blocked by" link too, so a
     free work check added later reads it.
  2. What waits on the owner, so the next session asks nothing already
     answered and does not wait on something it could do.
  3. A recount command beside every number, e.g. `4 open (gh issue list
     --label handoff | wc -l)`. A bare number is a claim nobody can check.
- **Judgment, never derivable state.** Why a decision went the way it did,
  what was deliberately not done, which alternative lost and on what
  grounds, which trap cost an hour. Counts, SHAs and issue tallies belong
  to the commands that derive them.
- **Reorganize only at a milestone.** A large feature landing, an
  architecture change, or the log growing long enough to bury what
  matters. On any other day, append.
- **A decision is superseded, never deleted.** Mark it with the date and
  what replaced it. When the decisions outgrow the handoff, split them to
  `docs/DECISIONS.md` and leave a pointer.

## The handoff pass

After PRs merge, one pass on a `docs/handoff-*` branch folds their notes into
the log and turns each next step into ticket state. The session that merges
the PRs runs it before it stops.

1. Branch `docs/handoff-<date>` from trunk, in the session's own working
   directory. A shell `cd` into another worktree lasts for one command
   only. So this folder is the one the owner gets at the end. Use it when
   `git status --short` prints nothing. The `git-worktrees` branch test does
   not apply here: trunk, or the branch this session started on, is yours.
   A second pass on the same day adds `-2`, a third `-3`. To see the names
   in use, run `git fetch origin` and `git branch -a --list '*handoff-<date>*'`.

   ```sh
   git fetch origin
   git switch --no-track -c docs/handoff-<date> origin/<trunk>
   ```

   Else make a new worktree for the pass (`git-worktrees`), and name that
   folder in step 7.
2. Print the notes of every PR merged since the last pass. Change the date
   to the day of that pass. The heading must start its own line, so a body
   that mentions the section in prose still yields the section itself:

   ```sh
   gh pr list --state merged --limit 200 --search "merged:>=2026-09-21" --json number,title,body --jq '.[] | "### #\(.number) \(.title)\n" + ((.body | capture("(^|\\n)## Handoff notes[ \\t]*\\r?\\n(?<n>[\\s\\S]*?)(\\n## |$)") | .n) // "(no handoff notes)") + "\n"'
   ```

3. Fold each into the log under its own dated heading, keeping
   the closing section last.
4. Rewrite the closing section if its tasks changed.
5. Turn each next step in the notes into ticket state. A step for work
   with no ticket: open one. A step for a ticket that exists: comment on
   that ticket. "After #X": link the waiting ticket as blocked by #X. A
   question for the owner: the label `needs-owner` on the ticket it holds
   back. Notes with no next step, or `(no handoff notes)`, change no
   ticket: list them in the pass's PR body for the owner.
6. Open the PR. It goes through review like any other. Have the PR
   reviewed, and merge it before the session stops. Then trunk holds the newest
   handoff, and every new worktree reads it.
7. Leave the pass's folder where the newest handoff is. If the pass ran
   in the session's own folder, the owner then has nothing to type.
   - The PR merged: run `git fetch origin`, then
     `git switch <trunk> && git pull --ff-only`. If git refuses because
     trunk is checked out in another worktree, run
     `git switch --detach origin/<trunk>`. If the pull refuses, local trunk
     has diverged: use the detach command, and tell the owner.
   - The PR did not merge: stay on the pass branch, and tell the owner why.

   The last line of the reply, after any TL;DR, names the folder as an
   absolute path, and where it is, e.g. one of:

   ```text
   Next session: start in /Users/me/code/repo (on main)
   Next session: start in /Users/me/code/repo-wt (detached at origin/main)
   Next session: start in /Users/me/code/repo (on docs/handoff-2026-11-12, PR #61 not merged)
   ```

**Reviewer rule for a handoff pass.** The reviewer checks these three, and a
miss is blocking:

- Every merged PR in the pass whose Handoff notes name a next step for work
  still open has a ticket, or a comment on a ticket, that carries that step.
- No two open tickets name the same task.
- Every "after #X" in the notes is a "blocked by" link on GitHub.

A PR with no notes prints `(no handoff notes)`. List it for the owner in the
pass's PR body, as step 5 says.

To make each PR carry the section, add it to `.github/pull_request_template.md`:

```
## Handoff notes
What the next session needs: decisions and why, traps that cost time, what was deliberately not done, and each next step with the ticket it belongs to. The handoff pass copies this into `docs/HANDOFF.md` after merge. Only a handoff branch edits that file.
```

## When the hook warns

`hooks/handoff-freshness.py` runs on every Stop and can send three
warnings. It also runs when a session starts or after `/clear`, and there
it runs only the `HANDOFF SHAPE` check. All are addressed to the model.

- When a session starts or after `/clear`: `HANDOFF SHAPE` is in the
  session's context before the first prompt. Act on it before other work.
- At the end of a turn: any of the three arrives as Stop hook feedback,
  and the turn continues so you can act on it. Each problem comes once per
  session, so act on it the first time. A different problem under the same
  name still comes, e.g. a handoff edit after the PR-body ask. The full rule
  is in yw-workflow `docs/DECISIONS.md`, 2026-11-16.

- `HANDOFF NOTES`: a branch committed real work. Write its `## Handoff notes`
  in the PR body. If the branch touched `docs/HANDOFF.md`, move those lines
  to the PR body and revert the file.
- `HANDOFF STALE`: on trunk or a `docs/handoff-*` branch, the session
  committed real work and nothing touched the handoff. Run the handoff pass.
- `HANDOFF SHAPE`: the file has a shape problem. One case is a file with
  no `## Start here` line. Another is a file whose first 40 lines still say
  "end of a session". That old preamble told the reader the file was
  written at close. A third is a block that does not open with the block
  in this skill. An empty block is in this case, and so is an old block
  that claims a `lane` issue. The warning names the first line that
  differs. A fourth is a handoff-named `.md` tracked outside `docs/`.
  Paste the block, delete the preamble, and fold the stray file in. When
  the hook cannot read this skill's block, it says so and skips that check.

`SKIP_HANDOFF_CHECK=1` silences all three, visibly, for a session that has a
reason.

## Migrating an existing handoff

Put the block on top. Leave the body as it is; a rewrite on migration day is
the churn the rules forbid. Name the repo's free work check in its
`CLAUDE.md`, or write the closing section for today, so step 2 of the block
is true the moment the file is committed.

A repo that still has `lane` issues retires them first. Turn each `## Next`
step into a ticket or a comment on the ticket it names. Turn each "after
#X" into a "blocked by" link, and each trap note into a line in the
closing section of `docs/HANDOFF.md`. Then close each lane issue with a
comment that points to where its steps went. Delete `scripts/lane_claim.py`.

## Hands off to

- The closing section names a task that is not agent-ready:
  `/yw-workflow:ship-loop` says what a ticket needs before it is one.
- What waits on the owner is more than a line: `/yw-workflow:need-me` is the
  format for asking it.
- The next session has to work alongside another: `/yw-workflow:git-worktrees`
  is the first thing the Start here block loads, for that reason.
