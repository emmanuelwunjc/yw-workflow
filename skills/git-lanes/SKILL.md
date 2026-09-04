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
`~/.claude/hooks/git-safety-guard.sh` blocks those commands while one runs.

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

## Never copy a venv between worktrees

Measured 2026-08-27 on a 72 MB, 3,134-file venv (pandas, numpy, requests,
pytest), macOS arm64:

```
reflink copy of .venv       0.35s   12 files broken
uv venv && uv pip install   0.08s    0 files broken
```

Rebuilding is four times faster AND correct, because `uv` hardlinks packages out
of `~/.cache/uv`, which every worktree on the machine shares. Copying wins only
on a cold cache, which happens once per machine.

The copy is also wrong in a way that hides. `bin/python` is a symlink out of the
tree, so `sys.prefix` relocates and `import pandas` works, which makes the copy
look fine. But `bin/activate` and every console script (`bin/pytest`,
`bin/f2py`, `bin/pygmentize`) hardcode the SOURCE worktree's absolute path on
line 2. So lane B runs lane A's interpreter for as long as lane A exists, and
`bin/pytest` dies with `No such file or directory` the moment lane A is removed.
That is cross-lane contamination, the one thing worktrees exist to prevent,
arriving through the cache optimisation meant to speed them up.

Build the venv fresh in each lane. Put it in a creation hook if your tooling has
one, never in a copy step.

## A git wrapper bypasses the safety hook

`~/.claude/hooks/git-safety-guard.sh` matches on the literal string `git `. Any
tool that wraps git (worktrunk's `wt`, lazygit, a Makefile target, a script)
runs its git operations as its own subprocesses and never presents a `git`
command to the Bash tool, so every rule in that hook silently stops applying:
no "do not move a tree while a mutation harness runs", no "no commit on main".

Adopting such a tool means adding matching rules for ITS command names to that
hook, in the same commit. A tool that is only a convenience layer over commands
the hook already guards is not neutral, it is a hole.

Evaluated 2026-08-27: worktrunk (`wt`, github.com/max-sixty/worktrunk) is a thin
Rust wrapper that reads worktrees straight from git, so lanes created by hand
with `git worktree add` appear in `wt list` with no migration. Two things it
does better than raw git: `wt switch` onto a branch another worktree holds
NAVIGATES there instead of failing or detaching, which removes the checkout
footgun this whole skill exists for, and `wt remove` detects a squash-merged
branch that `git branch --merged` does not list. Two things to refuse: `wt
merge` fast-forwards LOCAL trunk with commits that never passed a required
status check, and no config disables it, so block it in the hook before anyone
runs it. And its path template has no stateful filter, so it cannot produce the
`NN-name` counter: keep creating lanes with `git worktree add`.

## Mechanism over prose

When a rule here gets broken, the fix is a mechanism. Prefer, in order: a hook
that blocks it, CI that fails on it, a config setting that forbids it, then
prose. The concurrency rule above was prose for months and broke the first time
it mattered. It is now `~/.claude/hooks/git-safety-guard.sh`, which denies the
command.

For a repo meant to last: CI runs the repo's own documented checks on every push
and PR, and branch protection on trunk requires that CI to pass and blocks
force-push. Local pre-commit hooks are bypassed with `--no-verify`, so they
complement server-side protection rather than replace it.
