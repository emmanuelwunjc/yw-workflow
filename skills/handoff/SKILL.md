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
every session its own first task, and a claim comment shows which lane is
taken. Issue edits and comments cost no CI minutes, and every machine and
cloud routine can read them.

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
3. List the open lanes. Each line ends with the lane's holder line, and
   the oldest comes first:

   gh issue list --label lane --state open --json number,title,comments --jq 'map({n: .number, t: .title, c: ([.comments[] | {at: .createdAt, l: (.body | split("\n")[0] | rtrimstr("\r"))} | select(.l | test("^(claimed|released) by .+, [0-9]{4}-[0-9]{2}-[0-9]{2}$"; "i"))] | last)}) | sort_by(.c.at // "") | .[] | "#\(.n) \(.t) | \(.c.at // "never") | \(.c.l // "no claim yet")"'

   No lines: no lane is open. Read the LAST section of this file for the
   first task, and go to step 6.
4. Pick a lane. A lane is held when its holder line is a claim under 24
   hours old, or a claim by a session ListAgents shows live. A release,
   no claim, or an older claim is free. Take the lane the owner named. Else, one free lane: take it.
   More than one: ask the owner with one AskUserQuestion, one option per
   free lane in list order, the first recommended. No owner present (a
   cloud routine, a headless run): take the first free lane. No free
   lane: tell the owner every lane is held, and stop.
5. Claim it: `gh issue comment <N> --body "claimed by <name>, <YYYY-MM-DD>"`.
   <name> is your session name as ListAgents prints it. With no
   ListAgents, name your harness and worktree, e.g. `cloud routine
   nightly` or `laptop:04-handoff-lanes`. Then run step 3 again. Lane
   <N>'s holder line is your claim: you hold it. It is another session's
   claim: that session holds it. Post nothing, and go back to step 4.
6. Read the lane issue's `## Next`, or with no lane the LAST section.
   Read the recent sections of this file for traps. Run the recount
   commands before trusting any number. Start the first task it names.
   Ask the owner nothing it already answers.

When you stop on a lane, rewrite its `## Next` with `gh issue edit` and
post `released by <name>, <YYYY-MM-DD>` on it. Leave this block alone.

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
  The body holds a `## Next` section in the shape below.
- **A claim and a release are issue comments.** Claim:
  `claimed by <name>, <YYYY-MM-DD>`. Release:
  `released by <name>, <YYYY-MM-DD>`. The name is the session name
  ListAgents prints. A session with no ListAgents tool names its harness
  and worktree, e.g. `cloud routine nightly` or `laptop:04-handoff-lanes`.
- **One holder rule, used by steps 3, 4 and 5 of the block.** A lane's
  holder line is its latest comment whose first line matches
  `^(claimed|released) by .+, \d{4}-\d{2}-\d{2}$`, case-insensitive. No
  other comment counts, so "Claimed by nobody yet, is this lane alive?" is
  ignored. The holder line is a release, or there is none: the lane is free.
  It is a claim under 24 hours old, or a claim by a session ListAgents
  shows live: the lane is held. Any other claim is free. ListAgents sees
  only one machine and one harness, so the 24 hours keep a claim by a cloud
  routine or another machine held for its first day.
- **After a claim, list again.** Step 5 reruns the list of step 3. Your
  claim is the lane's holder line: you hold it. Another session's claim is
  the holder line: that session holds it, so post nothing and pick again.
- **The session that stops on a lane hands it off on the issue.** Rewrite
  its `## Next` with `gh issue edit <N> --body-file <file>`, then post the
  release comment. A finished lane's issue is closed by the handoff pass,
  with `gh issue close <N>`.
- **Write it down as you go, in the PR body.** Every decision, defect and
  trap that cost time gets a few lines when it happens. A handoff written at
  close comes from a compacted memory, and the reasoning drops out first.
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

1. Branch `docs/handoff-<date>` from trunk.
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
   still open goes into that lane's issue `## Next`, with `gh issue edit`.
   No issue for that work yet: open one with label `lane`. Close a lane's
   issue only when a PR's notes carry `Lane: #<N>. finished`, e.g.
   `Lane: #57. finished`, with
   `gh issue close <N> --comment "finished in #<PR>"`. Notes with no
   `Lane:` line, with no next step, or `(no handoff notes)` close nothing:
   list them in the pass's PR body for the owner. List the lanes:

   ```sh
   gh issue list --label lane --state open --json number,title,body,comments
   ```

6. Open the PR. It goes through review like any other.

**Reviewer rule for a handoff pass.** The reviewer checks these four, and a
miss is blocking:

- Every merged PR in the pass whose Handoff notes name a next step for work
  still open has an open `lane` issue that carries that step.
- No two open `lane` issues name the same first task.
- Every `lane` issue the pass closed cites a PR, in its closing comment,
  whose notes say `Lane: #<N>. finished` for that issue.
- A `lane` issue with no claim or release comment in 7 days is listed in the
  pass's PR body for the owner, who keeps it or closes it. Seven days is one
  working week: a lane idle that long has usually been finished or dropped.

A PR with no notes prints `(no handoff notes)`. That is a finding about the
PR, so ask its author before guessing.

To make lanes carry the section, add it to `.github/pull_request_template.md`:

```
## Handoff notes
Lane: #<lane issue>. <its next step, or the word finished>
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
  `.md` is tracked outside `docs/`. Paste the block, delete the preamble,
  fold the stray file in.

`SKIP_HANDOFF_CHECK=1` silences all three, visibly, for a session that has a
reason.

## Migrating an existing handoff

Put the block on top. Leave the body as it is; a rewrite on migration day is
the churn the rules forbid. Create the `lane` label. Open one `lane` issue
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
