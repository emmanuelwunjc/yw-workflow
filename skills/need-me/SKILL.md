---
name: need-me
description: Show only what is actually waiting on the human, delivered as clickable questions they answer in seconds. Use when the user asks "what needs me", "am I blocking anything", "/need-me", "what's waiting on me", at any natural pause where they may walk away, and before a handoff so the next session does not inherit a hidden queue of unanswered questions.
origin: authored
tags: [attention, escalation, handoff, decisions]
version: 1.0.1
---

# Need me

**In one line:** Shows only what is waiting on you, answerable in one word.

That line is for a human reading the skill list. Never say it back: the output
format below allows exactly one line of prose, and this would be a second.


Write for someone whose calendar is booked in thirty-second units. They read
this standing up, between two other things, and they answer by clicking.

## The one rule

**If they have nothing to do about it, leave it out.** Not "no action
required". Out.

Something belongs here only when a decision, a permission, or a physical human
act is the ONLY thing between it and progress. If more work on your side would
resolve it, go and do that instead.

## Delivery: one TLDR line, then the questions

1. **One line of prose. Exactly one.**
   `**Need you: <four-word tldr> · <four-word tldr>**`
   This has to be enough on its own to decide whether to engage at all.
2. **Then `AskUserQuestion`, one question per blocked item.** The situation
   lives in the question text. The options are the answer.

No progress counts. No backlog. No parked list. No closing paragraph: the
questions ARE the close.

If there is nothing, write `Nothing needs you.` and stop. Do not open a
question box to say so.

## Rendering: must work in a terminal AND in the desktop app

The same call renders as a chip-and-list in the terminal and as cards on
desktop. The terminal is the tighter constraint, so write to it and desktop
follows.

- **`header`: 12 characters, hard limit.** It is a chip. `Vermont ID`,
  `Send email`, `Contact obj`. Not a sentence, not a number.
- **`label`: 5 words or about 30 characters.** It is one selectable row in a
  terminal list; longer wraps and the list stops being scannable. Mark the
  suggested one by ending its label `(recommended)` and putting it first.
  That tag costs 14 characters, so the label's own words get about 16: write
  `Open the profile (recommended)`, never `Open his LinkedIn profile now
  (recommended)`.
- **`description`: one or two short sentences.** Say the consequence of
  choosing it, not a restatement of the label. This is what makes a choice
  possible without reading anything else.
- **2 to 4 options.** Never one: a single option is an instruction, not a
  decision. "Other" is added automatically, so never write your own.
- **4 questions maximum**, which is the tool's limit and also the attention
  limit. More than four blocked things, take the four that unblock the most
  and say `showing 4 of 7` in the TLDR line.
- **Never use `preview`.** It forces a side-by-side layout that is cramped in
  a terminal, and it is single-select only.
- **No markdown in labels or headers.** Bold and backticks render literally in
  some surfaces.
- **`multiSelect` only when the choices genuinely combine.** A blocked
  decision is almost always one answer.

## The question text carries the situation

Put what is happening INTO the question, so the options can be short.

Good: "The spreadsheet names 'VT guy, J. Doe'. No public record of him
exists and LinkedIn blocks automated access. How do you want this settled?"

Bad: "What should we do about J. Doe?" (they have to reconstruct it)

Two sentences maximum. Plain language. No jargon, no bare issue numbers.

- "the check that reads 200 of 685 fields", not "#103"
- "writes to the live database, no undo", not "the apply path"
- Say the consequence: "two of the same person, nobody can tell which is real"

## What this is

- **A decision queue.** What the agents did stays in your bookkeeping.
- **Only what someone waits on.** Tickets nobody waits on stay in the tracker.
- **As short as the truth allows.** Three real blockers beat seven where four
  are filler.

## Facts are derived, never recalled

Read the live state before writing: open PRs and their checks, issue labels,
running agents, the last write to a live system. A number remembered from
earlier in the session is already stale, and a stale number is worse than none.

## Example

The prose, in full:

**Need you: identify a Vermont contact · send a drafted email**

Then two questions:

```
header:   "Vermont ID"
question: The spreadsheet names "VT guy, J. Doe". No public record of him
          exists, and LinkedIn blocks automated access. How do you want it settled?
options:
  "Open the profile (recommended)"
      You check it logged in. Thirty seconds, and it either confirms him or
      rules him out for good.
  "Leave him out"
      He stays in the spreadsheet, absent from the system, with a note saying why.
  "Ask whoever wrote it"
      Slower, and they may not remember a note from years ago.
```

```
header:   "Send email"
question: Six people in the sheet cannot be identified from any public source.
          A draft asking your colleague about all six sits unsent in your Gmail.
options:
  "Forward it (recommended)"
      It is addressed to you alone, so nothing has left the account yet.
  "Make it a task instead"
      The six questions go into the CRM, so answers land next to the records
      rather than in a mail thread.
  "Drop it"
      Those six stay marked unresolved. Nothing breaks.
```

## Hands off to

- Every answer is in: `/yw-workflow:ship-loop` resumes, or `/yw-workflow:wayfinder` records the decision
  on the map and closes the ticket.
- A decision here supersedes one already recorded: update `docs/HANDOFF.md` with
  the date and what replaced it.
- The answer opens more questions than it settles: `/yw-workflow:grill`.
- They are stuck because the choice needs background they do not have:
  `/yw-workflow:eli5-text`, then ask again.
