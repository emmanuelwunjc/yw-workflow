# Decisions

Measured findings behind the skills. These carry a date because they age:
re-measure before trusting one that is old. The skills stay procedure, so a
moving tool version does not rot them.

A decision is superseded, never deleted. Mark it with the date and what
replaced it.

## 2026-08-27: rebuild venvs per lane, never copy one

Supports `git-lanes`. A copied venv is slower AND broken.

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

## 2026-08-27: a git wrapper bypasses the safety hook, and worktrunk evaluated

Supports `git-lanes` and `harden`. Take `wt switch` and `wt remove`. Refuse
`wt merge`, and block it in the hook before anyone runs it.

This plugin's `hooks/git-safety-guard.sh` matches on the literal string `git `. Any
tool that wraps git (worktrunk's `wt`, lazygit, a Makefile target, a script)
runs its git operations as its own subprocesses and never presents a `git`
command to the Bash tool, so every rule in that hook silently stops applying:
no "do not move a tree while a mutation harness runs", no "no commit on main".

Adopting such a tool means adding matching rules for ITS command names to that
hook, in the same commit. A tool that is only a convenience layer over commands
the hook already guards is a hole in it.

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
