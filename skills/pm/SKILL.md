---
name: pm
description: The one chat the owner talks to. Status mode reports what changed, where it is heading, what it lacks and who holds which lane. It reads git, gh, docs/HANDOFF.md and the lane issues. Batch mode writes a spec per ticket, starts builder and reviewer agents, and loops to a clean review. It reports once per batch and never edits files itself. Batch mode wants Orca (the `orca` CLI) and falls back to the yw-workflow builder, reviewer and fixer subagents without it. Use when asked for project status, what happened, what to work on next, to "run these tickets", "run a batch", or "be the PM".
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

Batch mode runs from the repo's primary checkout. Every path below is
relative to it.

### 1. Pick the path, and say it

```bash
[ -n "$ORCA_WORKSPACE_ID" ] \
  && [ "${ORCA_WORKSPACE_ID#*::}" = "$(git worktree list --porcelain | sed -n '1s/^worktree //p')" ] \
  && command -v orca >/dev/null && orca status | grep -qx "runtimeReachable: true" \
  && orca skills list | grep -q "^orchestration:" && echo orca || echo fallback
```

Orca sets `ORCA_WORKSPACE_ID` in a chat that runs in an Orca terminal. Its
part after `::` is the chat's folder. The Orca path starts workers in that
folder, so it must be the repo's primary checkout. It prints `orca`: use the
Orca path. It prints `fallback`: say this one line to the owner before
anything else, then use the fallback path:

    Orca is missing, or this chat is not in an Orca terminal at the primary checkout, so this batch runs on subagents. They skip your SessionStart and Stop hooks.

### 2. Write one spec per ticket

A spec stands alone. The worker sees nothing else. It holds:

- the ticket number and its acceptance boxes, copied in.
- "The PM assigns your work, so skip the lane menu." Add "The PM holds lane #N for you" when the PM claimed one.
- the branch name, `type/short-description`.
- what the worker may edit, and what it must not touch.
- the evidence that proves it is done: the literal commands and their expected result.
- the rules a worker must keep that no hook will check for it (see the fallback cost below).
- the last line, for a builder or fixer: "commit your work on your own branch before you return (on a detached HEAD, `git switch -c wip/<folder>` first), as a WIP commit if it is unfinished, and report the branch and SHA".

A reviewer spec is the `fresh-eye` prompt skeleton, filled in for this branch.
It ends with "Do not fix anything. Do not commit."

### 3. Run each ticket as a `ship-loop`

When a ticket has a `lane` issue, the PM claims it before it starts the
builder, with step 5 of the `## Start here` block in `docs/HANDOFF.md`. That
step has the command, the name to use and what each exit code means. The PM
releases the lane when the ticket merges. A ticket with no lane issue needs
no claim.

`.worktrees/` must be in the repo's `.gitignore`, per `git-lanes`. When
`git check-ignore -q .worktrees/` exits 1, the first
builder spec adds it.

Builder, then a reviewer that did not write the change, then fixes, then a
new reviewer at the fixed commit. Stop on a clean round, as `ship-loop` step 6
defines it. Tickets that touch different files run in parallel. Two to four
at once, per `git-lanes`.

Who does what at the end:

| Step | Who |
|---|---|
| Push the branch and open the PR | the builder, once the PM tells it the review is clean. |
| The `Rounds:` line in the PR body | the PM, with `gh pr edit`. On the fallback path each round carries `subagent_tokens`. Orca reports no token count, so an Orca round is its verdict and count alone, e.g. `Rounds: BLOCK 2 · PASS` |
| Merge | the PM, with `gh pr merge`, under the owner's standing authorization: a clean review and CI clean at the same commit |
| The handoff pass after the merges | a documenter worker, in its own worktree like every worker, on a `docs/handoff-*` branch per `/yw-workflow:handoff`. It is reviewed like any other change |

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
2. Start each worker in the PM's folder, then end the turn. Orca wakes the
   PM. The quoted `'SPEC'` keeps every `$`, backtick and backslash of the
   spec as written:

   ```bash
   orca orchestration worker-start --agent claude --worktree current \
     --task-title "<ticket>" --spec-file - <<'SPEC'
   <the spec from step 2 of batch mode>
   SPEC
   ```

3. The worker starts in the primary checkout. The spec's first step makes
   its own worktree there, per `git-lanes`. The spec then runs every git
   command with `-C` and the full worktree path, without quotes. The PM writes
   that path into the spec:

   ```bash
   git worktree add .worktrees/<NN>-<slug> -b <branch> <base>
   git -C /full/path/.worktrees/<NN>-<slug> add <files>
   git -C /full/path/.worktrees/<NN>-<slug> commit -m "<message>"
   ```

   The git safety hook judges a commit by the session's start folder, unless
   the same command names a folder with `-C` or a leading `cd` (#16). It
   misreads a quoted path (#27). With a space in the repo path, the hook
   refuses the commit, so use the fallback path for that repo.

   The spec also says: edit only files under the worktree path. A reviewer
   makes a detached worktree at the SHA the builder reported:
   `git worktree add --detach .worktrees/<NN>-review-<slug> <sha>`.
4. Send fixes to the builder that wrote the code. Orca reopens a closed
   worker for it. Findings hold backticks and `$`, so pass them through a
   quoted heredoc:

   ```bash
   orca orchestration send --to dispatch:<dispatch_id> --subject fix --body "$(cat <<'BODY'
   <findings>
   BODY
   )"
   ```

5. Answer a worker `question` the same way, with
   `orca orchestration reply --id <message_id> --body "$(cat <<'BODY' ... )"`.
6. Clean up every worktree the batch made, from the primary checkout. A
   reviewer worktree can still hold a mutation test, so it takes `--force`:

   ```bash
   git worktree remove .worktrees/<NN>-<slug>
   git worktree remove --force .worktrees/<NN>-review-<slug>
   git branch -D <branch>      # after its PR merged, or for a throwaway branch
   ```

Orca's guide says to let `worker-start` make each worker's workspace. This
skill knowingly differs. A new Orca workspace needs `orca repo add`, and
`orca` 1.4.250 has no command that removes a repo. On the first smoke run
that left a record only `orca project setup-delete --force` could clear.
Workers that use git worktrees in the PM's folder leave nothing in Orca
that git cannot remove.

A worker started with `--worktree current` closes on its own when it reports.
A batch adds a Run and its Tasks to Orca's log, which `orca orchestration
run-list` shows. It adds no repo, no workspace and no folder to Orca, so git
removes all that the batch made.

**Known gap, on both paths.** A reviewer keeps Bash, and an Orca worker has
every tool, so the spec's "Do not fix anything. Do not commit." is a sentence
that nothing enforces. A reviewer also changes files in place for its
mutation tests, inside its own worktree. Note the local branch tip before the
review. When the review ends, the tip must be the same and
`git -C <builder worktree> status --short` must print nothing. Else throw that
round away and start a new reviewer.

Rule 1 has the same gap. The PM keeps its Write and Edit tools, so "the PM
edits no files" holds only as long as the PM keeps it. The check is the same:
`git status --short` in the PM's folder prints nothing at the end of a batch.

## Fallback path

Use the Agent tool, one worktree per agent (`isolation: "worktree"`, per
`git-lanes`):

| Role | `subagent_type` |
|---|---|
| Builder | `yw-workflow:builder` |
| Reviewer | `yw-workflow:reviewer` (no Write or Edit tool) |
| Fixer | `yw-workflow:fixer` |
| Documenter (the handoff pass) | `yw-workflow:documenter` |

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
