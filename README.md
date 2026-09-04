# yw-workflow

Nine skills and five hooks that make an engineering workflow mechanical
instead of remembered.

## Install

Pick one. Both serve the same nine skills, and installing both leaves
duplicates that drift apart.

```bash
# skills only
npx skills add emmanuelwunjc/yw-workflow -g --skill '*' -y

# skills and the five hooks. Use this on your own machine.
claude plugin marketplace add emmanuelwunjc/yw-workflow
claude plugin install yw-workflow@yw-workflow
```

Then restart Claude Code.

Both read the **default branch**, so a change is installable only once it
reaches `main`. The `-g` above is load-bearing: the skills CLI defaults to
project level and would write into whatever directory you are standing in.

A few skills mention "your CLAUDE.md". They read fine without one, and better
with the rules in it.

## Skills

Each one carries a one-line summary at the top.

| | |
|---|---|
| **grill** | Asks you one decision at a time, in checkboxes, until nothing is left to guess. |
| **wayfinder** | Turns work too big for one session into a map of decisions on GitHub Issues. |
| **git-lanes** | Gives every concurrent agent its own worktree so they cannot corrupt each other. |
| **ship-loop** | Runs work as a loop that closes: ticket, branch, test first, review, fix, repeat. |
| **fresh-eye** | Sends someone who did not write the code to try to break it. |
| **need-me** | Shows only what is waiting on you, answerable in one word. |
| **harden** | Gives a repo the CI and branch protection that make its review gate real. |
| **eli5** | Explains a topic to someone with zero background, as a page of big pictures and few words. |
| **eli5-text** | Explains a topic to someone with zero background, in the conversation, with nothing to open. |

Invoke them namespaced: `/yw-workflow:grill`.

They chain, and each one's "Hands off to" section names the next, so loading
any of them reaches the rest.

```
grill -> wayfinder -> git-lanes -> ship-loop -> fresh-eye
              |                         |            |
              +--------> need-me <------+------------+
```

`harden` runs once per repo, before any of it merges.

`eli5` and `eli5-text` are off the diagram because they explain a thing rather
than ship one. They are still in the graph: `grill` and `need-me` reach
`eli5-text` when a decision is blocked on understanding, and `ship-loop` and
`harden` reach `eli5` when a change needs explaining to someone who will not
read the diff.

## Hooks

Each exists because a rule broke and prose was not enough. They come with the
plugin path only.

| | | |
|---|---|---|
| **git-safety-guard.sh** | PreToolUse, `git *` | Blocks commits straight to `main` and tree moves that collide with another agent. |
| **require-code-review.py** | PreToolUse | Blocks `gh pr merge` on a 25+ line PR with no review. Override: `SKIP_REVIEW_GATE=1`. |
| **no-ai-attribution.py** | PreToolUse | Keeps AI-generation footers out of anything people read. Commit trailers stay. |
| **claude-md-guard.py** | UserPromptSubmit, Stop | Blocks em-dashes, negation-then-correction, and prose questions where checkboxes are required. |
| **handoff-freshness.py** | Stop | Catches work piling up against an untouched `docs/HANDOFF.md`. |

Wire them in one place only. Wiring the same hook here and in
`~/.claude/settings.json` fires it twice and halves its block budget.

`git-safety-guard.sh` matches the literal string `git `. A wrapper (`wt`,
lazygit, a Makefile target) runs git as a subprocess and every rule stops
applying, so adding one means adding its command names to the hook in the same
commit.

## Checks

```bash
(for t in ./hooks/*-selftest.*; do "$t" || exit 1; done)
./tools/check-repo.py
```

Both run in CI on every pull request and on push to `main`, and `main` is
protected: a red check blocks the merge, for the repo owner too.
`claude-md-guard.py` is deliberately partial: it blocks a turn, so it fires only when it is sure, and
its known misses and known false positives are listed in its self-test.

## Credit

`grill` and `wayfinder` are adapted from
[Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT). `wayfinder`
in particular is his design: the map issue, decision tickets sized to one
session, the fog of war, one ticket per session. Each skill's own Credit
section says what changed and why, and `NOTICE` reproduces his copyright and
permission notice in full, which is what MIT actually requires.

## Layout

- `skills/` one directory per skill, one `SKILL.md` each.
- `hooks/` the guards, their self-tests, and `hooks.json`.
- `tools/check-repo.py` what the self-tests do not cover.
- `docs/HANDOFF.md` why decisions went the way they did, and the traps.
- `docs/DECISIONS.md` the dated measurements behind the skills.

Edit here, commit, then `claude plugin update yw-workflow`. A version bump is
required, because the update keys off it.
