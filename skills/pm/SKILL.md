---
name: pm
description: The one chat the owner talks to. Status mode answers "what changed, where is this heading, what does it lack, who holds which lane" from git, gh, docs/HANDOFF.md and the open lane issues. Batch mode writes a spec per ticket, starts builder and reviewer agents, loops until review is clean, and reports once per batch; it never edits files itself. Batch mode wants Orca (the `orca` CLI) and falls back to the yw-workflow builder, reviewer and fixer subagents without it. Use when asked for project status, what happened, what to work on next, to "run these tickets", "run a batch", or "be the PM".
origin: authored
tags: [project-management, orchestration, orca, status, coordination]
version: 1.0.0
---

# PM

**In one line:** Gives you one chat that reports status and runs builder and reviewer agents, through Orca when it is installed and subagents when not.

Say that line back when you start, so whoever invoked this knows what they
got.

Two modes. Status mode reads. Batch mode runs other agents and edits nothing.

## The one rule

**Derivable state is computed, never stored. Authored judgment is the only
thing written down.** A count, a SHA or a test total read out of a doc is a
claim with a timer on it. Run the command instead.

## Status mode

Answer four questions: what changed, where is it heading, what does it lack,
who holds which lane. Read from the primary checkout, because a worktree can
lag trunk:

```bash
MAIN=$(git worktree list --porcelain | head -1 | cut -d' ' -f2)
git -C "$MAIN" fetch origin --quiet
gh pr list --state merged --limit 15          # what changed
gh pr list --state open                       # what is in flight
gh issue list --state open --limit 50         # what it lacks
git -C "$MAIN" worktree list                  # which folders hold work
```

Then read authored judgment:

| Question | Source |
|---|---|
| Where is it heading | the last section of `$MAIN/docs/HANDOFF.md`, and each open lane issue's `## Next` |
| Who holds which lane | the lane list command in step 3 of the `## Start here` block of `$MAIN/docs/HANDOFF.md`. Run it from there. A copy here would drift from the one the hook checks |
| Who is live now | ListAgents, if the harness has it |
| Why a decision went that way | `$MAIN/docs/DECISIONS.md`, if it exists |

In the answer, keep a derived fact ("4 PRs open") apart from a judgment ("the
weakest area is X"), and name whose judgment it is. Name the source of each
claim. Say which source was missing, in one line. To rewrite the handoff,
load `/yw-workflow:handoff`. Status mode does not write it.

## Batch mode

**Rule 1: the PM edits no files.** Not code, not docs, not the handoff. It
writes specs into commands, starts workers, answers them and reports. Every
change to the repo is a worker's commit. A PM that edits is a builder that
nobody reviews.

### 1. Pick the path, and say it

```bash
command -v orca >/dev/null && orca status | grep -qx "runtimeReachable: true" \
  && orca skills list | grep -q "^orchestration:" && echo orca || echo fallback
```

It prints `orca`: use the Orca path. It prints `fallback`: say this one line to
the owner before anything else, then use the fallback path:

    Orca is missing or not reachable, so this batch runs on subagents. They skip your SessionStart and Stop hooks.

### 2. Write one spec per ticket

A spec stands alone. The worker sees nothing else. It holds:

- the ticket number and its acceptance boxes, copied in;
- the branch name, `type/short-description`;
- what the worker may edit, and what it must not touch;
- the evidence that proves it is done: the literal commands and their expected result;
- the rules a worker must keep that no hook will check for it (see the fallback cost below);
- the last line, for a builder or fixer: "commit your work on your own branch before you return (on a detached HEAD, `git switch -c wip/<folder>` first), as a WIP commit if it is unfinished, and report the branch and SHA".

A reviewer spec is the `fresh-eye` prompt skeleton, filled in for this branch.
It ends with "Do not fix anything. Do not commit."

### 3. Run each ticket as a `ship-loop`

Builder, then a reviewer that did not write the change, then fixes, then a
new reviewer at the fixed commit. Stop on a clean round, as `ship-loop` step 6
defines it. Keep the `Rounds:` line in the PR body. Tickets that touch
different files run in parallel. Two to four at once, per `git-lanes`.

### 4. Answer the workers

A worker question that `CLAUDE.md`, the ticket or the repo answers: answer it,
and cite where. Ask the owner only for a call none of those settle. Batch
those calls into one AskUserQuestion, each with a recommended option.

### 5. Report once per batch

One digest when every ticket has settled. Per ticket: the outcome, the
evidence (PR, review verdict, the command output that proves it), and what is
still open. Bold only what the owner must do.

## Orca path

Orca workers are full Claude Code sessions. Each one loads `CLAUDE.md`, the
skills and every hook, including the SessionStart and Stop hooks.

1. Load Orca's own guide once: `orca skills get orchestration`. Follow it for
   the commands. It changes with each Orca release, so it is not copied here.
2. Find the repo id. Register the repo once if the line prints nothing:

   ```bash
   orca repo list --json | jq -r --arg p "$MAIN" '.result.repos[] | select(.path == $p) | .id'
   orca repo add --path "$MAIN"
   ```

3. Start the builder, then end the turn. Orca wakes the PM:

   ```bash
   orca orchestration worker-start --agent claude --worktree new-top-level \
     --repo id:<id> --name <short> --spec-file - <<'SPEC'
   <the spec from step 2>
   SPEC
   ```

4. On the builder's `worker_done`, start the reviewer the same way, with
   `--base-branch <the branch the builder's report names>`, so it reviews in its
   own worktree. Orca gives each new worktree its own branch, so take the
   branch from the report, never from the worktree name.
5. Send fixes to the builder that wrote the code:
   `orca orchestration send --to dispatch:<id> --subject fix --body "<findings>"`.
6. Answer a worker `question` with `orca orchestration reply --id <message_id> --body "<answer>"`.
7. When the batch is done, release each worker that started in a new
   worktree: `orca orchestration worker-release`. Then remove its worktree
   once its branch is merged.

**Known gap.** An Orca worker has every tool. The reviewer's "do not edit
files" is a sentence in its spec, and nothing enforces it. The fallback
reviewer has no Write or Edit tool. If a review commit shows up on the
branch, throw that round away and start a new reviewer.

## Fallback path

Use the Agent tool, one worktree per agent (`isolation: "worktree"`, per
`git-lanes`):

| Role | `subagent_type` |
|---|---|
| Builder | `yw-workflow:builder` |
| Reviewer | `yw-workflow:reviewer` (no Write or Edit tool) |
| Fixer | `yw-workflow:fixer` |

**The cost.** A subagent does not run SessionStart hooks, and the Stop hook
does not check its output. So it starts without the rules those hooks inject,
and nothing blocks a reply that breaks them. The PreToolUse hooks still fire
on its tool calls. Put the rules it must keep into the spec, in full: e.g. the
writing rules, the commit rules, the no-attribution rule.

## Hands off to

- A ticket is not ready to build: `/yw-workflow:grill` first.
- The review loop itself: `/yw-workflow:ship-loop` and `/yw-workflow:fresh-eye`.
- A call only the owner can make: `/yw-workflow:need-me`.
- The handoff after the batch merges: `/yw-workflow:handoff`.
