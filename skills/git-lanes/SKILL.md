---
name: git-lanes
description: Run concurrent agents in isolated git worktrees without them colliding. Use before starting multi-file work in a repo where another agent may be active, when asked to "run these in parallel", "spin up lanes", "use worktrees", when dispatching a reviewer, or when about to git checkout/pull/stash in a repo you did not just create. Also covers where built deliverables live and how lanes merge back to trunk.
origin: authored
tags: [git, worktree, concurrency, multi-agent, merge]
version: 1.0.0
---

# Git lanes

Two agents in one working directory is the failure. File ownership does not
prevent it: `checkout`, `pull` and `stash` move the entire working tree
regardless of who owns which file. Those are different problems and need
different mechanisms.

## Before touching git in a shared repo

Run `git status --short` and `git branch --show-current` first. Uncommitted
changes, or a branch you did not create, mean someone else is in there. Make a
worktree instead of switching.

A running mutation-testing harness makes this worse: it mutates tracked files
transiently, so a concurrent `checkout` can abort and a concurrent `git add -A`
can commit a mutation as if it were real work. Both have happened.
this plugin's `hooks/git-safety-guard.sh` blocks those commands while one runs.

## Worktrees live inside the repo, in one gitignored `.worktrees/`, numbered

```
# WRONG. The obvious command, and it scatters checkouts through the
# folder that holds real projects.
git worktree add ../gpu-wt-tone -b fix/tone
git worktree add ../gpu-worktrees/cites -b feat/cites
# ~/Edits/ now: gpu, gpu-wt-tone, gpu-worktrees, ... beside real repos

# RIGHT. From the repo root, one ignored container, zero-padded counter
# that never resets, lane named after its branch and not the repo.
cd ~/Edits/gpu
git worktree add .worktrees/01-tone  -b fix/tone
git worktree add .worktrees/02-cites -b feat/cites
echo '.worktrees/' >> .gitignore
# ~/Edits/ now: gpu.   ls .worktrees/ -> 01-tone  02-cites
```

The parent holds one folder per project however many lanes run. `ls .worktrees/`
gives the live count and the order lanes opened. A lane is addressable as "02"
in a dispatch note. Deleting the repo takes its worktrees with it.

Two to four concurrent lanes is the practical ceiling before coordination costs
more than the parallelism gains. The numbering makes exceeding it visible.

Never rename or move a worktree while an agent is working in it.

## Cwd drift is the recurring accident

A shell that has drifted into a worktree will run `git merge` against the wrong
branch. Use `git -C /abs/path` or an explicit absolute `cd` in every git command,
never a bare relative one. Creating a worktree from inside another worktree
nests it; both have happened in one session.

## A reviewer gets its own worktree, never the author's

Read-only intent is not isolation. A reviewer proves a guard fires by breaking
something and rebuilding, which writes generated files into the tree the author
is editing. Branch the reviewer's worktree from the commit under review, and it
can attack the build as hard as it likes without touching anyone's work.

See the `fresh-eye` skill for how to brief the reviewer.

## Merging back

Review the diff, run the checks fresh, then squash-merge to trunk. Never let two
agents run `git add`/`commit`/`push` against the same checkout at the same time,
even briefly: a commit can capture a half-written file.

Worktrees isolate the filesystem only. Ports, databases and external services
are still shared and need their own coordination.

A squash-merge leaves the source branch unmarked as merged, so `git branch
--merged` will not list it. Do not read that as "never merged".

## Built deliverables live in `deliverables/`, one folder, never the repo root

```
# WRONG. Generated files sit beside the code that makes them, so a reader
# cannot tell what is source and what is output, and a tracked .xlsx at
# root looks like something a person edited by hand.
repo/report.xlsx  repo/deck.html  repo/memo.md  repo/build_deck.py

# RIGHT.
repo/build_deck.py                 # source: the thing you edit
repo/deliverables/deck.html        # output: the thing you send
repo/deliverables/report.xlsx
```

The folder name answers "what do I open" and "what do I edit" without asking.
Keep filenames fully descriptive: `deliverables/gates4-compute-slides.html` is
what lands in an email attachment.

Track outputs when they are the product and someone needs the file without a
build. Gitignore them when they are large binaries that churn every build.
Either way they are generated: fix the input, never the output, and say so in
the folder's own README.

When the path changes, every documented build command changes with it, in
`CLAUDE.md`, `README` and `docs/HANDOFF.md`, or the docs send the next person to
a file that is no longer there.

A loose preview copy at the repo root gets swept into an unrelated lane's
`git add -A`. That has happened. Write previews to the scratchpad.

## Mechanism over prose

When a rule here gets broken, the fix is a mechanism. Prefer, in order: a hook
that blocks it, CI that fails on it, a config setting that forbids it, then
prose. The concurrency rule above was prose for months and broke the first time
it mattered. It is now this plugin's `hooks/git-safety-guard.sh`, which denies the
command.

For a repo meant to last: CI runs the repo's own documented checks on every push
and PR, and branch protection on trunk requires that CI to pass and blocks
force-push. Local pre-commit hooks are bypassed with `--no-verify`, so they
complement server-side protection rather than replace it.

## Hands off to

- A lane finishes: it does NOT merge on its own. `/yw-workflow:ship-loop` step 4 dispatches
  `/yw-workflow:fresh-eye` at the lane tip, and the lane merges only after a round comes
  back clean. A lane that merges unreviewed is the failure this whole set exists
  to prevent.
- Setting up a repo that has no CI or branch protection to merge into:
  `/yw-workflow:harden` first.
- The measured findings behind this skill (the venv benchmark, the worktrunk
  evaluation) live in `docs/DECISIONS.md` in this plugin, dated, because they
  age and this procedure does not.
