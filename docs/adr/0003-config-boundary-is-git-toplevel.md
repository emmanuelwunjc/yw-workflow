# The config search stops at the git toplevel

Date: 2026-09-08

`hooks/handrail_config.py` walks up from the current directory for a
`.handrail.toml` and stops at `git rev-parse --show-toplevel`. Outside a
repository it trusts only the current directory. A toplevel that is not an
ancestor of the current directory (set by `GIT_DIR` and `GIT_WORK_TREE`) is
refused. The bound stops a config in a shared or world-writable parent, e.g.
`/tmp`, from governing every checkout below it.

## Considered Options

- A hand-rolled walk that looks for a `.git` marker: rejected after it was
  wrong four ways in four review rounds. A `touch /tmp/.git` restored the
  attack, a `.git` at `$HOME` captured `~/code`, and requiring a `.git`
  directory broke linked worktrees, which use a `.git` file.
- Ask git, but only when a pattern matches: chosen. The guard matches its
  patterns first, so the subprocess runs on a command that carries a footer
  and not on every Bash call. Measured 2026-09-08: 24.7 ms for an ordinary
  command and 37.2 ms on a match, against 35.8 ms for every command when the
  lookup ran first.

## Consequences

A directory with a corrupt `.git` file gets the defaults, and does not take
its parent's policy. A submodule is its own boundary, so a superproject's
config does not reach into it.
