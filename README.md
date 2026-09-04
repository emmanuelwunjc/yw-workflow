# yw-workflow

Yiming's engineering workflow as a Claude Code plugin: the skills, and the
hooks that make the rules mechanical instead of hoping the model remembers
them.

## Install

**Pick one.** Installing both leaves two copies on disk under different names
(the plugin namespaces its skills as `/yw-workflow:grill`, the skills CLI does
not), so you get duplicates that drift apart.

**As a skill package** (what most skill repos use, and the shorter path):

```bash
npx skills add emmanuelwunjc/yw-workflow -g --skill '*' -y
```

It clones over your existing git credentials, so a private repo works with no
extra setup. `npx skills list` shows what landed, `npx skills update` refreshes.

Two things this path does differently. It installs the **skills only**, so none
of the five guard hooks come with it. And it defaults to **project-level**,
writing into whatever directory you are standing in, which is why `-g` is above.
`--all` is shorthand for `--skill '*' --agent '*' -y`, and that `--agent '*'`
installs to every coding agent it detects rather than to Claude Code alone.

**As a Claude Code plugin** (the path that also wires the hooks):

```bash
claude plugin marketplace add emmanuelwunjc/yw-workflow
claude plugin install yw-workflow@yw-workflow
```

Restart Claude Code. The five guard hooks come with it, and it installs at user
level. This is the one to use on your own machine.

**The repo is private**, so both resolve only for an account with read access
and a loaded key. Anyone else clones first and points at the directory:

```bash
git clone git@github.com:emmanuelwunjc/yw-workflow.git
claude plugin marketplace add ./yw-workflow
claude plugin install yw-workflow@yw-workflow
```

Both paths read the **default branch**, so a change is only installable once it
reaches `main`.

The skills reference "your CLAUDE.md" in a few places. They read fine without
one, and they read better with the rules in it.

## Skills

Plugin skills are namespaced, so the real invocation carries the plugin name.

| Command | What it does |
|---|---|
| `/yw-workflow:grill` | Interrogates a plan one decision at a time, in checkbox format, until an implementer could build it without asking anything. |
| `/yw-workflow:wayfinder` | Charts work too big for one session as a map of decision tickets on GitHub Issues, then resolves them one at a time. |
| `/yw-workflow:git-lanes` | Runs concurrent agents in isolated git worktrees so they cannot collide. Load before any parallel work. |
| `/yw-workflow:ship-loop` | Ticket, branch, implement test-first, review, fix, repeat until a review round comes back clean. |
| `/yw-workflow:fresh-eye` | Dispatches an independent adversarial reviewer in an isolated worktree, to try to break a change rather than agree with it. |
| `/yw-workflow:need-me` | Shows only what is actually waiting on you, in plain language, with options for each. |
| `/yw-workflow:harden` | Stamps CI, pre-commit hooks, a PR template, and branch protection onto a repo that has none. |

They form one chain, and each skill's "Hands off to" section names the next
link, so loading any one of them reaches the rest:

```
grill -> wayfinder -> git-lanes -> ship-loop -> fresh-eye
              |                         |            |
              +--------> need-me <------+------------+

harden runs once per repo, before any of it merges.
```

`grill` sizes the work. `wayfinder` charts it when it is too big for one
session. `git-lanes` isolates it. `ship-loop` builds it. `fresh-eye` tries to
break it. `need-me` escalates what only you can settle.

## Hooks

Each hook exists because a rule got broken and prose was not enough.

| Hook | Event | Blocks |
|---|---|---|
| `git-safety-guard.sh` | PreToolUse, gated to `git *` | Commits straight to `main`, and working-tree operations that would collide with a concurrent agent. |
| `require-code-review.py` | PreToolUse(Bash) | `gh pr merge` on a PR that changes 25+ lines and carries no review. Override: `SKIP_REVIEW_GATE=1`, visible in the command. |
| `no-ai-attribution.py` | PreToolUse(Bash) | AI-generation footers and session URLs in anything people read. Git commit trailers stay. |
| `claude-md-guard.py` | UserPromptSubmit + Stop | Em-dashes, negation-then-correction (six forms, tuned so a plain negative like "Not yet." never trips; known misses are listed in its self-test), and prose questions where the checkbox format is required. |
| `handoff-freshness.py` | Stop | Work accumulating with a `docs/HANDOFF.md` that has not been touched. |

**Wire these in one place only.** They were previously wired by absolute path in
`~/.claude/settings.json`. Installing the plugin without removing those entries
fires every hook twice, which matters: `claude-md-guard.py` allows two blocks per
session, so a single violation burns the whole budget and the second one of the
session goes through unblocked. Those entries were removed when this plugin was
installed; the old file is at `~/.claude/settings.json.bak-pre-plugin`.

`git-safety-guard.sh` matches the literal string `git `. A wrapper (`wt`,
lazygit, a Makefile target) runs git as its own subprocess and every rule stops
applying. Adding such a tool means adding its command names to the hook in the
same commit. See `docs/DECISIONS.md`.

## Self-tests

```bash
./hooks/git-safety-guard-selftest.sh        # 37 cases
./hooks/require-code-review-selftest.py     # 22 cases
./hooks/claude-md-guard-selftest.py         # 73 cases + a mutation check
./hooks/no-ai-attribution-selftest.py
```

## Layout

- `skills/` one directory per skill, each a single `SKILL.md`.
- `hooks/` the guard scripts, their self-tests, and `hooks.json` wiring them by
  `${CLAUDE_PLUGIN_ROOT}`.
- `docs/HANDOFF.md` why decisions went the way they did, and the traps that cost time.
- `docs/DECISIONS.md` the dated measurements behind the skills (a venv copy
  benchmark, a `worktrunk` evaluation). They live here rather than in a skill
  because findings age and procedures do not.

## Editing

This repo is the source of truth. Edit here, commit, then
`claude plugin update yw-workflow`. The personal copies that used to live in
`~/.claude/skills` were moved to `~/.claude/backups/skills-pre-plugin`, because
a second copy shadows the plugin and then drifts from it.
