---
name: orca-bot
description: The general rules every Orca bot follows (which language goes where, how to hand work to workers, when an item is Needs you or Waiting, the boss-bot convention, how a bot home is laid out), plus a setup step that points a bot's home at them. Use when a bot loads it at the start of a session, when the owner says "set up the bot", "orca-bot setup <name>", or "add the bot rules", or right after `orca bot create`.
origin: authored
tags: [orca, bots, setup, language, workers]
version: 1.1.0
---

# Orca bot

**In one line:** Holds the rules every Orca bot follows, and a setup step that points a new bot's home at them.

Say that line back when you start, so whoever invoked this knows what they got.

The rules live here, in the plugin, so one `claude plugin update yw-workflow`
reaches every bot. A copy in each bot home drifts: on 2026-11-24 two bots
held hand copies of the same two memory files, and the copies differed. A
rule that is specific to one bot (its purpose, its project, its own skills)
stays in that bot's SOUL.md and MEMORY.md.

## Setup

Run it once per bot, after `orca bot create`:

```bash
python3 <this skill's folder>/setup.py <bot name>
```

It writes to `~/.orca/bots/<bot name>/` and nowhere else:

- It appends a short marked block to `SOUL.md` that tells the bot to load
  this skill. When `SOUL.md` already holds the marker, it appends nothing.
- It writes `memory/feedback-delegate-fixes.md` and
  `memory/feedback-tell-agent-not-owner.md`, each only when the bot has no file
  of that name. A file the bot already has stays as it is.
- It never writes `AGENTS.md`, `CLAUDE.md`, `bot.json` or `MEMORY.md`.

A second run changes nothing. It stops with one line, and writes nothing, when
`orca` is not on PATH, the bot home has no `SOUL.md`, or its `memory` is a
plain file. A memory file name that is a symlink, also a dangling one, counts
as present, so setup never writes through it. The texts it writes are
in `templates/`. Its self-test is `test_setup.py`, which CI runs through
`hooks/orca-bot-selftest.py`.

The two memory files are not listed in `MEMORY.md`, because only
`orca bot memory` changes that file. The `SOUL.md` block names them.

## The rules

### 1. Language: an allow-list

The owner's own language goes in one place only: the bot's reply to the owner
in the Orca Home Chat. Everything else is English: Slack, GitHub and Linear
threads (also ones the owner started), mail to agents and bots, worker specs,
item text, code, commits, PRs, issues, handoffs and every file.

Before you write, ask: "is this my Home Chat reply to the owner?" Yes: the
owner's language. Anything else: English.

The owner's language is a setting: the `disallowed` scripts of the hook. An
owner who writes English everywhere has nothing to do. For Slack, the plugin hook
`slack-language.py` blocks an `orca slack post` in a disallowed script. It is
off by default. Turn it on, and set the scripts, in `~/.handrail.toml`
(`[rules] slack_language = true`, `[slack_language] disallowed`). See
`docs/HOOKS.md` in this plugin for its known misses.

Source: owner decision 2026-11-24, after a bot replied in a Slack thread in
the wrong language on 2026-11-23.

### 2. Workers

- **Send every edit to a worker.** That includes a small edit in the bot's own
  `skills/` folder. The bot does reads, status and digests itself. Its context
  is for coordinating. Source: owner, 2026-11-23.
- **Close a worker's terminal after its `worker_done`.** A finished worker
  still uses compute. Never close one that still waits for an answer.
  Source: owner, 2026-11-24.
- **Tell the agent, not the owner.** A note, caveat or instruction that only
  an agent acts on goes to that agent (`orca orchestration send`) or on its
  item. The Home Chat reply holds the outcome, what changed, and what waits on
  the owner. Source: owner, 2026-11-24: "Don't tell me, tell the agent."
- **One digest per turn.** The owner gets one report of overall progress, and
  hears when an agent needs them. Never one message per worker that finishes.
  Source: owner, 2026-11-23.

### 3. Boss bot (an option)

Use this when an owner has more than one bot and names one of them the boss.

- A child bot names its boss in its purpose (`orca bot create --purpose`).
- The boss gives a child work with
  `orca orchestration send --to bot:<name> --type handoff|question|status`.
- The boss never edits a child's `SOUL.md` or `MEMORY.md` without the owner.
  A child that asks for setup gets an answer by mail, and the owner does the
  copying (or runs the setup step above).
- The owner stays above every bot. The owner's word wins over the boss's.

Orca has no org field, and every bot runs as the owner, so this is a
convention that nothing enforces. Source: owner decision 2026-11-24.

### 4. How a bot home is laid out

A bot's home is `~/.orca/bots/<name>/`. Read on 2026-11-24 from Orca 1.4.273.

| File | Who writes it |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `bot.json` | Orca. It replaces any edit to them. `CLAUDE.md` holds only `@AGENTS.md`. |
| `SOUL.md` | Starts with the `--purpose` line. Says who the bot is and how it works. Change it only when the owner asks. |
| `MEMORY.md` | The bot's memory: one dated line per fact. A line taken out by hand comes back. Remove one with `orca bot memory forget --fact "<its words>"`. |
| `memory/<topic>.md` | The details behind a `MEMORY.md` line. The bot writes them. |

`orca bot create --template` takes only Orca's built-in template ids, so a
custom template folder cannot do this setup at create time yet. That is why
setup is a separate step.

### 5. Item status: Needs you and Waiting

- **Needs you is for anything only the owner can do or decide.** That
  includes a physical act, e.g. running commands on the owner's machine or a
  step in a web console. Waiting is only for a wait outside the bot, its
  workers and the owner, e.g. a CI run or a reply from another team. A
  reminder adds a comment to the item and never changes its status. Source:
  owner, 2026-11-24: a daily reminder moved 5 owner-blocked items from Needs
  you to Waiting, and the owner had to ask where they were.
- **Mark a finished item done in the same turn.** A PR merged or a ticket
  closed makes its item done at once. Never set it to Waiting to stop the
  "nothing is running" line. Source: owner, 2026-11-24.
- **Ask the owner once.** In a live chat, ask in the chat. Put Needs you on an
  item only for a question raised while the owner is away. Source: owner,
  2026-11-24.
