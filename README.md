# yw-workflow

Yiming's engineering workflow as a Claude Code plugin: the skills, and the
hooks that make the rules mechanical instead of hoping the model remembers
them.

## Install

```bash
claude plugin marketplace add emmanuelwunjc/yw-workflow
claude plugin install yw-workflow@yw-workflow
```

Restart Claude Code. Every skill below is then available as a slash command
and the hooks are live. Nothing else to configure.

## Skills

| Command | What it does |
|---|---|
| `/grill` | Interrogates a plan one decision at a time, in checkbox format, until an implementer could build it without asking anything. |
| `/wayfinder` | Charts work too big for one session as a map of decision tickets on GitHub Issues, then resolves them one at a time. |
| `/fresh-eye` | Dispatches an independent adversarial reviewer in an isolated worktree, to try to break a change rather than agree with it. |
| `/ship-loop` | Ticket, branch, implement test-first, review, fix, repeat until a review round comes back clean. |
| `/git-lanes` | Runs concurrent agents in isolated git worktrees so they cannot collide. Load before any parallel work. |
| `/bootstrap-repo-hygiene` | Stamps CI, pre-commit hooks, a PR template, and branch protection onto a repo that has none. |

They chain. `/grill` sizes the work, `/wayfinder` charts it if it is big,
`/ship-loop` builds it, `/fresh-eye` tries to break it.

## Hooks

Each hook exists because a rule got broken and prose was not enough.

| Hook | Event | Blocks |
|---|---|---|
| `git-safety-guard.sh` | PreToolUse(Bash) | Commits straight to `main`, and working-tree operations that would collide with a concurrent agent. |
| `require-code-review.py` | PreToolUse(Bash) | `gh pr merge` on a PR that changes 25+ lines and carries no review. Override: `SKIP_REVIEW_GATE=1`, visible in the command. |
| `no-ai-attribution.py` | PreToolUse(Bash) | AI-generation footers and session URLs in anything people read. Git commit trailers stay. |
| `claude-md-guard.py` | UserPromptSubmit + Stop | Em-dashes, negation-then-correction, and prose questions where the checkbox format is required. |
| `handoff-freshness.py` | Stop | Silently accumulating work with a `docs/HANDOFF.md` that has not been touched. |

`git-safety-guard.sh` matches the literal string `git `. A wrapper (`wt`,
lazygit, a Makefile target) runs git as its own subprocess and every rule
stops applying. Adding such a tool means adding its command names to the hook
in the same commit.

## Self-tests

```bash
./hooks/git-safety-guard-selftest.sh
./hooks/require-code-review-selftest.py
./hooks/no-ai-attribution-selftest.py
```

`no-ai-attribution-selftest.py` is blocked by the hook it tests when you write
about it inside a Bash command. That is the enforcement working, and it is why
this README was written with the file-edit tool.

## Editing

This repo is the source of truth. Edit here, commit, then
`claude plugin update yw-workflow`. Do not copy files back into
`~/.claude/skills` or `~/.claude/hooks`: two copies drift.
