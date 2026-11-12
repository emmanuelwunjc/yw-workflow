---
name: handoff
description: Keep a repo's docs/HANDOFF.md in the one shape that lets a fresh session start from the file and the open lane issues alone, with a Start here block on top that has the session claim one open `lane` issue, and dated sections added by a handoff pass after merges, from the Handoff notes each lane PR carries. Use when asked for "a handoff", "/handoff", "write the handoff", "update the handoff", at the close of a session, or when the handoff-freshness hook warns HANDOFF STALE or HANDOFF SHAPE.
origin: authored
tags: [handoff, docs, session, continuity]
version: 1.4.0
---

# Handoff

**In one line:** Keeps `docs/HANDOFF.md` and the `lane` issues in the shape that lets a fresh session start from them alone.

Say that line back when you start, so whoever invoked this knows what they
got.


A handoff exists so the next session starts working without anyone composing
an opening prompt. The owner decided on 2026-09-16 that pointing a fresh agent
at `docs/HANDOFF.md` is the whole prompt. Since 2026-11-10 the file's Start
here block sends the session on to one open `lane` issue, and that issue's
`## Next` names its first task. That holds only if every handoff has the same
shape, so this skill is the shape, and `hooks/handoff-freshness.py` warns when
a repo drifts from it.

This skill never emits a separate prompt for the next session. The file and
the lane issues are the prompt. If you find yourself writing "paste this to
start the next session", stop and put it in the `## Next` of that lane's
issue instead.

Each open lane of work has its own next task, so each has its own GitHub
issue. On 2026-11-10 in EdSim, two lanes were open: a wage fix, run by a live
session, and drafts of redesign tickets. The file named one first task, the
wage fix, so a new session took the lane that was already taken. The drafts'
next step lived only in the Handoff notes of a merged PR. A lane issue gives
every session its own first task, and a `Held by:` line in the issue body
shows which lane is taken.
Issue edits cost no CI minutes unless a workflow runs `on: issues`, and
every machine and cloud routine can read them.

## The top of the file

Paste this block verbatim at the top of `docs/HANDOFF.md`, above everything
else, and leave it alone afterwards:

```
# Handoff

## Start here

You are a fresh session. This file and the open `lane` issues are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-lanes` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Check that the repo has the label. This prints `lane` if it does:
   `gh label list --search lane --json name --jq '.[] | select(.name == "lane") | .name'`
   It prints nothing: this repo has no lane label yet. Read the LAST
   section of this file for the first task, and go to step 6.
3. List the open lanes. Free lanes come first, lowest issue number
   first. Held lanes follow, oldest time first:

   gh issue list --label lane --state open --limit 100 --json number,title,body --jq '(now | strftime("%Y-%m-%dT%H:%MZ")) as $now | map(((.body // "") | split("\n") | first // "" | rtrimstr("\r")) as $h | {n: .number, t: .title, h: $h, s: (($h | capture("^Held by: (?<name>.+), since (?<time>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z)$") | select(.name != "nobody" and .time <= $now) | .time) // null)}) | sort_by(if .s then [1, .s, .n] else [0, .n] end) | .[] | "#\(.n) \(.t) | \(if .s or .h == "Held by: nobody" then .h else "Held by: (malformed)" end)"'

   No lines: no lane is open. Read the LAST section of this file for the
   first task, and go to step 6. 100 lines: raise `--limit`, list again.
4. Pick a lane. A lane is free when its `Held by:` line says nobody or
   is malformed, or its time is over 24 hours old and ListAgents does
   not show that session live. Else it is held. The owner named a lane:
   take it, and if it is held, tell the owner and stop. Else, one free
   lane: take it. More than one: ask the owner with one AskUserQuestion,
   one option per free lane in list order, the first recommended. No
   owner present (a cloud routine, a headless run): take the first free
   lane. No free lane: tell the owner, and stop.
5. Claim it, after any answer from the owner:
   `python3 scripts/lane_claim.py claim <N> "<name>"`. Add
   `--holder-not-live` only when step 4 found the lane free by its
   24-hour rule. Exit 0: you hold the lane. Exit 1: it says why. Change
   nothing. The owner named this lane: tell the owner and stop. Else go
   back to step 4. Any other exit, e.g. no `scripts/lane_claim.py` or a
   failed `gh`: change nothing, stop, and tell the owner. <name> is your
   session name as ListAgents prints it. With no ListAgents, use your
   harness and worktree, e.g. `laptop:04-handoff-lanes`. A cloud routine
   adds its run start, e.g. `cloud routine nightly 2026-11-10T06:17Z`.
6. Read the lane issue's `## Next`, or with no lane the LAST section.
   Read the recent sections of this file for traps. Run the recount
   commands before trusting any number. Start the first task it names.
   Ask the owner nothing it already answers.

Write a lane body only with `scripts/lane_claim.py write` or `release`,
and if it refuses, change nothing, stop, and tell the owner. Update
`## Next` with `python3 scripts/lane_claim.py write <N> "<name>" <file>`,
and free the lane with `python3 scripts/lane_claim.py release <N> "<name>"`
when you stop. Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
```

## The rules

- **One committed file for the log, one issue per lane for its next
  task.** `docs/HANDOFF.md` holds the decisions, traps and judgment that
  every lane shares. A `lane` issue holds one lane's `## Next`. Never
  `/tmp`, never a scratchpad, never a second file named `HANDOFF.md` or
  `AGENT_HANDOFF.md` somewhere else: two log files means the next session
  reads the wrong one.
- **One open issue per open lane, with label `lane`.** Create the label
  once per repo:
  `gh label create lane --description "One open lane of work. Its body holds the lane's ## Next." --color 0E8A16`.
  Open a lane with `gh issue create --label lane --title "<lane>" --body-file <file>`.
  The body's first line is the holder line, then a `## Next` section in
  the shape below. A new lane's body has `Held by: nobody` as its first
  line.
- **The holder rule.** The holder line is line one of the issue body,
  with a trailing CR stripped. `^Held by: nobody$` is free.
  `^Held by: (?<name>.+), since (?<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)$`,
  with a name other than `nobody` and a time not in the future, is a
  holder line. Anything else is malformed and free, and the list prints it
  as `(malformed)`. A holder line holds the lane while its time is under 24
  hours old, or while ListAgents shows that session live.
- **One script runs every lane body change.** A repo copies
  `skills/handoff/lane_claim.py` verbatim to `scripts/lane_claim.py`.
  `diff` against the plugin's file is the drift check. The script reads
  and writes in one process, so the gap between the read and the write is
  about one second. Its self-test is `hooks/lane-claim-selftest.py`.
- **To claim.** After any answer from the owner, run
  `python3 scripts/lane_claim.py claim <N> "<name>"`. It refuses a lane that
  another name holds. It refuses a holder line over 24 hours old unless you
  pass `--holder-not-live`, which you do only after ListAgents shows that
  session is not live. Else it writes your line as line one, waits, and
  reads again. Exit 0: you hold the lane. Exit 1: change nothing and pick
  again. Any other exit, e.g. no `scripts/lane_claim.py` or a failed `gh`:
  change nothing, stop, and tell the owner. The script exits 1 only on a
  refusal. The read and the edit share one budget of half the wait, and a
  run past it exits 2 without writing.
- **Session names are unique per run.** Use the name ListAgents prints.
  With no ListAgents, use the harness and worktree, e.g.
  `laptop:04-handoff-lanes`. A cloud routine adds its run start time, e.g.
  `cloud routine nightly 2026-11-10T06:17Z`.
- **The stop rule, for every write after a claim.** Write a lane body
  only with `scripts/lane_claim.py write` or `release`, and if it refuses,
  change nothing, stop, and tell the owner. `write <N> "<name>" <file>`
  replaces everything after line one with the file and puts a new time on
  line one. `release <N> "<name>"` sets line one to `Held by: nobody`. Both
  refuse when line one is not your own holder line. An edit replaces the
  whole body, so a write built from an older read would erase a claim made
  since.
- **Write it down as you go, in the PR body.** Every decision, defect and
  trap that cost time gets a few lines when it happens. A handoff written at
  close comes from a compacted memory, and the reasoning drops out first.
- **Before any session stops, the builder and fixer worktrees it started
  hold no uncommitted work.** That is each Agent-tool worktree it dispatched
  and each worktree it made. For each one with uncommitted work, message its
  agent to commit it as WIP on its own branch. On a detached HEAD, that
  means `git switch -c wip/<folder>` first, with the worktree's folder name.
  If no agent can take the message, commit it yourself the same way. Name
  the branch, with `git log -1 <branch>` as its recount command. Put the
  name in the `lane` issue's `## Next` with `lane_claim.py write`, if this
  session holds that issue. Else put it in the open PR's `## Handoff notes`.
  Else put it in the final reply to the owner. If no commit is possible,
  name the worktree path, its branch and "uncommitted work" in the same
  place. Leave other worktrees as they are. Do not write any of this into
  `docs/HANDOFF.md`: only a handoff pass edits it.
- **Lanes do not edit `docs/HANDOFF.md`.** A lane (any branch that is not a
  handoff branch) writes its notes in a `## Handoff notes` section of its PR
  body. The owner decided this on 2026-09-21: when every concurrent lane
  appended to the log, every lane hit a merge conflict in it. A repo can
  enforce it in CI by failing any other branch that touches the file. One
  exception: a change to the Start here block itself edits
  `docs/HANDOFF.md` on a lane. The HANDOFF NOTES warning on that lane is
  expected.
- **Dated sections, `## YYYY-MM-DD: what happened`, newest last.** The
  reader scrolls to the end and finds the present. The dated closing
  section is always the final `##` heading in the file, below any
  topic-grouped sections such as traps or decisions. The block reads it
  when the repo has no `lane` label or no open `lane` issue.
- **A lane issue's `## Next` is that lane's briefing.** The file's closing
  section keeps the same shape, for the case with no open lane. Each names,
  in this order:
  1. The one task to start first.
  2. The tickets to work, in order, e.g. `#186 (the mutation list is data)`.
  3. What waits on the owner, so the next session asks nothing already
     answered and does not wait on something it could do.
  4. A recount command beside every number, e.g. `4 open (gh issue list
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
the log and brings the lane issues up to date. The session that merges the
PRs runs it before it stops. A lane session never closes one this way.

1. Branch `docs/handoff-<date>` from trunk. Do it in the session's own
   working directory when its tree is clean. A shell `cd` into another
   worktree does not last past one command, so this folder is the one the
   owner gets at the end. A second pass on the same day adds `-2`.

   ```sh
   git fetch origin
   git switch --no-track -c docs/handoff-<date> origin/<trunk>
   ```

   The tree is not clean: make a new worktree for the pass (`git-lanes`),
   and name that folder in step 7.
2. Print the notes of every PR merged since the last pass. Change the date
   to the day of that pass. The heading must start its own line, so a body
   that mentions the section in prose still yields the section itself:

   ```sh
   gh pr list --state merged --limit 200 --search "merged:>=2026-09-21" --json number,title,body --jq '.[] | "### #\(.number) \(.title)\n" + ((.body | capture("(^|\\n)## Handoff notes[ \\t]*\\r?\\n(?<n>[\\s\\S]*?)(\\n## |$)") | .n) // "(no handoff notes)") + "\n"'
   ```

3. Fold each into the log under its own dated heading, keeping
   the `## Next` section (or the closing section, in repos whose handoff uses one) last.
4. Rewrite the `## Next` section (or the closing section, in repos whose handoff uses one) if the first task changed.
5. Bring the lane issues up to date. A note that names a next step for work
   still open goes into that lane's issue `## Next`. The pass writes a lane
   body only as its holder: it claims the lane with `lane_claim.py claim`,
   writes with `lane_claim.py write`, and releases with
   `lane_claim.py release`. The stop rule holds for it too. A lane held by another session:
   list the step in the pass's PR body for that session.
   No issue for that work yet: open one with label `lane`. Close a lane's
   issue only when a PR's notes have the exact line `Lane: #<N>. finished`
   with nothing after it, e.g. `Lane: #57. finished`, using
   `gh issue close <N> --comment "finished in #<PR>"`. A line with more
   text, e.g. `Lane: #57. finished the wage QC, next ...`, closes nothing.
   Notes with no `Lane:` line, with no next step, or `(no handoff notes)`
   close nothing either: list them in the pass's PR body for the owner.
   List the lanes, with the time each last changed:

   ```sh
   gh issue list --label lane --state open --limit 100 --json number,title,body,updatedAt
   ```

6. Open the PR. It goes through review like any other. Get the review and
   merge it before the session stops, so trunk holds the newest handoff
   and every new worktree reads it.
7. End the session in the pass's folder, back on trunk, so the owner can
   clear and start the next session there with nothing to type. Run
   `git fetch origin`, then `git switch <trunk> && git pull --ff-only`.
   Git refuses when trunk is checked out in another worktree. Then run
   `git switch --detach origin/<trunk>`. The last line of the reply names
   the folder as an absolute path, and the branch, e.g.
   `Next session: start in /Users/me/code/repo (on main)`.

**Reviewer rule for a handoff pass.** The reviewer checks these four, and a
miss is blocking:

- Every merged PR in the pass whose Handoff notes name a next step for work
  still open has an open `lane` issue that carries that step.
- No two open `lane` issues name the same first task.
- Every `lane` issue the pass closed cites a PR, in its closing comment,
  whose notes say `Lane: #<N>. finished` for that issue.
- A `lane` issue whose `updatedAt` and `Held by:` time are both over 7 days
  old is listed in the pass's PR body for the owner, who keeps it or closes
  it. When line one is `Held by: nobody` or malformed, `updatedAt` alone
  decides. Seven days is one working week: a lane idle that long has usually
  been finished or dropped.

A PR with no notes prints `(no handoff notes)`. List it for the owner in the
pass's PR body, as step 5 says.

To make lanes carry the section, add it to `.github/pull_request_template.md`:

```
## Handoff notes
Lane: #<lane issue>. <its next step>
To close the lane, write exactly `Lane: #<N>. finished` with nothing after it.
What the next session needs: decisions and why, traps that cost time, what was deliberately not done. The handoff pass copies this into `docs/HANDOFF.md` after merge. Lanes do not edit that file.
```

## When the hook warns

`hooks/handoff-freshness.py` runs on every Stop and prints one of three
warnings. All are addressed to the model and fix in the same turn.

- `HANDOFF NOTES`: a lane committed real work. Write its `## Handoff notes`
  in the PR body. If the lane touched `docs/HANDOFF.md`, move those lines to
  the PR body and revert the file.
- `HANDOFF STALE`: on trunk or a `docs/handoff-*` branch, the session
  committed real work and nothing touched the handoff. Run the handoff pass.
- `HANDOFF SHAPE`: the file has no `## Start here` line, its first 40 lines
  still say "end of a session" (the old preamble, which told the reader the
  file was written at close), its block has no command line that runs
  `gh issue list --label lane` within the first 40 lines, a step of its
  block opens with "Read the LAST section" (both are the block before
  2026-11-10, with one first task for every session), or a handoff-named
  `.md` is tracked outside `docs/`, or the block runs
  `scripts/lane_claim.py` and the repo has no such file. Paste the block,
  delete the preamble, fold the stray file in, copy the script with the
  command the warning prints.

`SKIP_HANDOFF_CHECK=1` silences all three, visibly, for a session that has a
reason.

## Migrating an existing handoff

Put the block on top. Leave the body as it is; a rewrite on migration day is
the churn the rules forbid. Copy `skills/handoff/lane_claim.py` to
`scripts/lane_claim.py`. Create the `lane` label. Open one `lane` issue
per open lane, each with its `## Next`. If no lane is open, write the closing
section for today, so step 3 of the block is true the moment the file is
committed.

## Hands off to

- A lane issue's `## Next`, or the closing section, names a task that is
  not agent-ready:
  `/yw-workflow:ship-loop` says what a ticket needs before it is one.
- What waits on the owner is more than a line: `/yw-workflow:need-me` is the
  format for asking it.
- The next session has to work alongside another: `/yw-workflow:git-lanes`
  is the first thing the Start here block loads, for that reason.
