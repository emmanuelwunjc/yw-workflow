---
name: pm
description: The one chat the owner talks to. Status mode answers "what changed, where is this heading, what does it lack, who holds which lane" from git, gh, docs/HANDOFF.md and the open lane issues. Batch mode writes a spec per ticket, starts builder and reviewer agents, and loops until review is clean. It reports once per batch and never edits files itself. Batch mode wants Orca (the `orca` CLI) and falls back to the yw-workflow builder, reviewer and fixer subagents without it. Use when asked for project status, what happened, what to work on next, to "run these tickets", "run a batch", or "be the PM".
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
MAIN=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
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

**Rule 1: the PM edits no files.** It writes specs into commands, starts
workers, answers them, merges and reports. Every change to a file is a
worker's commit, the handoff included. A PM that edits is a builder that
nobody reviews.

Set `MAIN` first, with the same line as status mode:
`MAIN=$(git worktree list --porcelain | sed -n '1s/^worktree //p')`.

### 1. Pick the path, and say it

```bash
[ -n "$ORCA_WORKSPACE_ID" ] && command -v orca >/dev/null \
  && orca status | grep -qx "runtimeReachable: true" \
  && orca skills list | grep -q "^orchestration:" && echo orca || echo fallback
```

`ORCA_WORKSPACE_ID` is set only in a chat that runs in an Orca terminal, and the
Orca path starts workers in that chat's workspace. It prints `orca`: use the Orca path. It prints `fallback`: say this one line to
the owner before anything else, then use the fallback path:

    Orca is missing or not reachable, so this batch runs on subagents. They skip your SessionStart and Stop hooks.

### 2. Write one spec per ticket

A spec stands alone. The worker sees nothing else. It holds:

- the ticket number and its acceptance boxes, copied in.
- the lane issue the PM claimed for it, if the repo uses lanes. Say "the PM holds lane #N for you, so skip the lane menu".
- the branch name, `type/short-description`.
- what the worker may edit, and what it must not touch.
- the evidence that proves it is done: the literal commands and their expected result.
- the rules a worker must keep that no hook will check for it (see the fallback cost below).
- the last line, for a builder or fixer: "commit your work on your own branch before you return (on a detached HEAD, `git switch -c wip/<folder>` first), as a WIP commit if it is unfinished, and report the branch and SHA".

A reviewer spec is the `fresh-eye` prompt skeleton, filled in for this branch.
It ends with "Do not fix anything. Do not commit."

### 3. Run each ticket as a `ship-loop`

In a repo with `lane` issues, the PM claims each ticket's lane before it
starts the builder: `python3 scripts/lane_claim.py claim <N> "<pm name>"`.
It releases the lane when the ticket merges.

Builder, then a reviewer that did not write the change, then fixes, then a
new reviewer at the fixed commit. Stop on a clean round, as `ship-loop` step 6
defines it. Tickets that touch different files run in parallel. Two to four
at once, per `git-lanes`.

Who does what at the end:

| Step | Who |
|---|---|
| Push the branch and open the PR | the builder, once the PM tells it the review is clean |
| The `Rounds:` line in the PR body | the PM, with `gh pr edit`. On the fallback path each round carries `subagent_tokens`. Orca reports no token count, so an Orca round is its verdict and count alone, e.g. `Rounds: BLOCK 2 · PASS` |
| Merge | the PM, with `gh pr merge`, under the owner's standing authorization: a clean review and CI clean at the same commit |
| The handoff pass after the merges | a documenter worker on a `docs/handoff-*` branch, per `/yw-workflow:handoff`, reviewed like any other change |

### 4. Answer the workers

A worker question that `CLAUDE.md`, the ticket or the repo answers: answer it,
and cite where. Ask the owner only for a call none of those settle. Batch
those calls into one AskUserQuestion, each with a recommended option.

### 5. Report once per batch

One digest when every ticket has settled. Per ticket: the outcome, the
evidence (PR, review verdict, the command output that proves it), and what is
still open. Bold only what the owner must do.

## Orca path

Orca supplies the worker sessions and the wake-ups. Git supplies the
isolation. Each Orca worker is a full Claude Code session, so it loads
`CLAUDE.md`, the skills and every hook, including the SessionStart and Stop
hooks.

1. Load Orca's own guide once: `orca skills get orchestration`. Follow it for
   the commands. It changes with each Orca release, so it is not copied here.
2. Start each worker in the PM's own Orca workspace, then end the turn. Orca
   wakes the PM:

   ```bash
   orca orchestration worker-start --agent claude --worktree current \
     --task-title "<ticket>" --spec-file - <<'SPEC'
   <the spec from step 2 of batch mode>
   SPEC
   ```

3. The spec's first step makes the worker's own worktree with git, per
   `git-lanes`, and moves into it. The git safety hook judges a commit by the
   branch of the shell's folder, so every later command runs from there:

   ```bash
   git -C "$MAIN" worktree add "$MAIN/.worktrees/<NN>-<slug>" -b <branch> <base>
   cd "$MAIN/.worktrees/<NN>-<slug>"
   ```

   A reviewer makes a detached worktree at the branch the builder's report
   names: `git -C "$MAIN" worktree add --detach "$MAIN/.worktrees/<NN>-review-<slug>" <branch>`.
4. Send fixes to the builder that wrote the code:
   `orca orchestration send --to dispatch:<dispatch_id> --subject fix --body "<findings>"`.
5. Answer a worker `question` with `orca orchestration reply --id <message_id> --body "<answer>"`.
6. Clean up every worktree the batch made, reviewer ones included, with git. A worker started with
   `--worktree current` closes on its own when it reports, so the batch leaves
   no Orca state behind:

   ```bash
   git -C "$MAIN" worktree remove "$MAIN/.worktrees/<NN>-<slug>"
   git -C "$MAIN" branch -D <branch>      # after its PR merged, or for a throwaway branch
   ```

Every command in a batch that changes state outside the repo has its undo
written beside it, and the undo was run once. The PM's own workspace is the
only Orca record a batch uses.

**Known gap, on both paths.** A reviewer keeps Bash, and an Orca worker has
every tool, so the spec's "Do not fix anything. Do not commit." is a sentence
that nothing enforces. A reviewer also changes files in place for its
mutation tests, inside its own worktree. If a commit from a reviewer shows up
on the branch under review, throw that round away and start a new reviewer.

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
- The handoff after the batch merges: `/yw-workflow:handoff`, run by a documenter worker.
