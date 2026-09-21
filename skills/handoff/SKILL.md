---
name: handoff
description: Keep a repo's docs/HANDOFF.md in the one shape that lets a fresh session start from the file alone, with a Start here block on top and dated sections added by a handoff pass after merges, from the Handoff notes each lane PR carries. Use when asked for "a handoff", "/handoff", "write the handoff", "update the handoff", at the close of a session, or when the handoff-freshness hook warns HANDOFF STALE or HANDOFF SHAPE.
origin: authored
tags: [handoff, docs, session, continuity]
version: 1.1.0
---

# Handoff

**In one line:** Keeps `docs/HANDOFF.md` in the shape that lets a fresh session start from the file alone.

Say that line back when you start, so whoever invoked this knows what they
got.


A handoff exists so the next session starts working without anyone composing
an opening prompt. The owner decided on 2026-09-16 that pointing a fresh agent
at `docs/HANDOFF.md` is the whole prompt. That holds only if every handoff has
the same shape, so this skill is the shape, and
`hooks/handoff-freshness.py` warns when a repo drifts from it.

This skill never emits a separate prompt for the next session. The file is
the prompt. If you find yourself writing "paste this to start the next
session", stop and put it in the file's last section instead.

## The top of the file

Paste this block verbatim at the top of `docs/HANDOFF.md`, above everything
else, and leave it alone afterwards:

```
# Handoff

## Start here

You are a fresh session and this file is your whole briefing. Nobody
writes you a separate prompt. Do these in order, then work.

1. Load skills `ship-loop`, `git-lanes` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Read the LAST section of this file (the most recent date). It names
   the first task, the tickets in order, and what waits on the owner.
3. Run the recount commands that section carries before trusting any
   number in it.
4. Start the first task it names. Ask the owner nothing that section
   already answers.

The handoff pass rewrites the last section (`## Next`, or the closing
section) so step 2 stays true, and leaves this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
```

## The rules

- **One file, `docs/HANDOFF.md`, committed.** Never `/tmp`, never a
  scratchpad, never a second file named `HANDOFF.md` or `AGENT_HANDOFF.md`
  somewhere else. Two handoffs means the next session reads the wrong one.
- **Write it down as you go, in the PR body.** Every decision, defect and
  trap that cost time gets a few lines when it happens. A handoff written at
  close comes from a compacted memory, and the reasoning drops out first.
- **Lanes do not edit `docs/HANDOFF.md`.** A lane (any branch that is not a
  handoff branch) writes its notes in a `## Handoff notes` section of its PR
  body. The owner decided this on 2026-09-21: when every concurrent lane
  appended to the log, every lane hit a merge conflict in it. A repo can
  enforce it in CI by failing any other branch that touches the file.
- **Dated sections, `## YYYY-MM-DD: what happened`, newest last.** The
  reader scrolls to the end and finds the present. The dated closing
  section is always the final `##` heading in the file, below any
  topic-grouped sections such as traps or decisions, so step 2 of the block
  ("read the LAST section") stays true.
- **The closing section is the briefing.** The handoff pass rewrites
  `## Next` (or the closing section) so it names, in this order:
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
the log. The session that merges the PRs runs it before it stops.

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
5. Open the PR. It goes through review like any other.

A PR with no notes prints `(no handoff notes)`. That is a finding about the
PR, so ask its author before guessing.

To make lanes carry the section, add it to `.github/pull_request_template.md`:

```
## Handoff notes
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
  file was written at close), or a handoff-named `.md` is tracked outside
  `docs/`. Paste the block, delete the preamble, fold the stray file in.

`SKIP_HANDOFF_CHECK=1` silences all three, visibly, for a session that has a
reason.

## Migrating an existing handoff

Put the block on top. Leave the body as it is; a rewrite on migration day is
the churn the rules forbid. Then write the closing section for today so
step 2 of the block is true the moment the file is committed.

## Hands off to

- The closing section names a task that is not agent-ready:
  `/yw-workflow:ship-loop` says what a ticket needs before it is one.
- What waits on the owner is more than a line: `/yw-workflow:need-me` is the
  format for asking it.
- The next session has to work alongside another: `/yw-workflow:git-lanes`
  is the first thing the Start here block loads, for that reason.
