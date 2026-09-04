---
name: grill
description: Interrogate a plan, decision, or idea one decision at a time until the shared understanding is real. Use when the user says "grill me", "stress-test this", "poke holes in it", "am I missing anything", or before committing to any plan whose cost is more than an hour. Also use when a request is ambiguous enough that two readings would produce different work.
origin: authored
tags: [planning, questions, decisions, askuserquestion]
version: 1.0.0
---

# Grill

A plan that survived no questions is a plan nobody checked. This skill asks
the questions.

## The format is fixed

Every question goes through the **AskUserQuestion tool**. Checkboxes, 2 to 4
concrete options, the recommended one first and labelled `(Recommended)`.
Never in prose.

This is your CLAUDE.md's habits section and it outranks any skill text, including
this one. A skill saying "ask one at a time" sets cadence, not format. That
displacement is exactly how this rule broke on 2026-07-08 and 2026-08-03:
skill text lands mid-turn at higher recency and wins on tone. It does not win
on format. This plugin's own `hooks/claude-md-guard.py` enforces it, and its Stop hook
refuses to end a turn that asked in prose.

If a question has only one live path, it is not a question. State the path
you are taking and continue.

## What to ask about

**Only decisions.** A fact you can find is a fact you go and find. Read the
file, run the command, check the schema, grep the callers. Asking the user
something the filesystem already knows spends their attention on your
laziness.

Ask about:

- **Scope boundaries.** What is deliberately out. The answer that saves the
  most time is usually "do not build that at all".
- **Forks with different downstream work.** Two readings of the request that
  lead to different code. Put both up.
- **Irreversibles.** Anything that deletes, publishes, migrates, or takes a
  name. Cheap to ask, expensive to undo.
- **Cost.** A third-party API, a paid tier, a runtime that bills. State the
  pricing in the option description, per your CLAUDE.md's habits section.
- **The thing you are about to assume.** If you catch yourself writing
  "assuming X", that assumption is the next question.

Do not ask about: conventional defaults, anything the repo already does
consistently, style the surrounding code has already settled.

## Cadence

One decision per call, in dependency order. Resolve what the next question
hangs on before asking it. Batch into a single call only when the questions
are genuinely independent and the user is answering a setup form rather than
thinking.

Walk the tree depth-first: take the branch the last answer opened before
going back for the siblings. Breadth-first grilling produces a wide shallow
map and no decisions.

## When to stop

Stop when an implementer could build it without asking anything. That is the
test. Not "the user seems satisfied", not "I have enough to start".

Then say back what was decided, in the user's own words where they gave them,
and do not start work until they confirm. A grilling that ends in you
building the wrong thing confidently is worse than no grilling.

## Hands off to

- The answers describe work too big for one session: `/yw-workflow:wayfinder` charts it.
- Sized for one session: `/yw-workflow:git-lanes` if anyone else may be in the repo, then
  `/yw-workflow:ship-loop`.
- A decision changed one already recorded: update `docs/HANDOFF.md` and mark the
  old one superseded with the date. A decision is superseded, never deleted.
- You could not get an answer: `/yw-workflow:need-me` puts the open question in front of the
  human in the format they can act on.
