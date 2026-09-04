---
name: eli5-text
description: Explain a topic like the reader knows nothing about it, in the conversation, with no artifact and no page to open. Use when the user asks to "eli5 this", "explain it simply", "what does this actually mean", or wants the plain version right now rather than a link. Prefer this over eli5 when the answer is needed mid-task.
origin: authored
tags: [explanation, teaching, plain-language]
version: 1.0.0
---

# eli5 text

**In one line:** Explains a topic to someone with zero background, in the
conversation, with nothing to open.

Say that line back when you start, so whoever invoked this knows what they got.

Same discipline as `/yw-workflow:eli5`. The difference is delivery: the answer
arrives where the question was asked, so it can be read mid-task without
leaving the terminal.

## When this one, and when the page

Use this when the explanation is a step on the way to something else: the user
is mid-task, needs a concept to keep going, and will act on it in the next
minute.

Use `/yw-workflow:eli5` when the explanation IS the deliverable: it will be
re-read, shown to someone else, or kept. A picture earns its place there because
someone will look at it twice.

## Shape

Open with the core idea in **one sentence**. If that sentence needs a comma and
an "and", it is two ideas and the topic is not broken down yet.

Then 3 to 6 short steps. Each is one bolded label and one or two sentences.
Nothing else. A reader should be able to stop after any step and still have
gained something whole.

Close with one line naming what this lets them do now.

## Rules

- **Every technical term gets a plain stand-in the moment it appears**, or it
  does not appear. `a queue (a line, first in, first out)` is fine. A bare
  `idempotent` is not.
- **Real-world comparison over abstraction.** "Like a mail carrier delivering
  letters" beats "a message-passing protocol". One comparison per step at most:
  a second one competes with the first and the reader holds neither.
- **Short sentences. One idea each.** A sentence with two clauses is two
  sentences.
- **Concrete numbers and names over placeholders.** "Reads the first 200 of 685
  fields" beats "reads a subset of fields".
- **Say the consequence, not the mechanism.** "Kill it midway and a broken file
  is left on disk" beats describing the restore machinery.

## Guardrails

- **No walls of text.** More than about 40 words in a step means the step is
  two steps.
- **Never open with what the thing is not.** The reader has not proposed
  anything to correct, so it spends a sentence and teaches nothing.
- **No artifact, no file, no link.** If the answer genuinely wants a picture,
  say so in one line and offer `/yw-workflow:eli5` instead of half-building one
  in ASCII.
- **Skip the preamble.** No "great question", no "let me explain". The first
  sentence is the core idea.

## Hands off to

- It wants a picture, or it will be re-read or shared: `/yw-workflow:eli5`
  publishes the same content as a page.
- The explanation reveals a decision the user has to make rather than a fact
  they have to learn: `/yw-workflow:grill`.
- They asked because something is blocked on them: `/yw-workflow:need-me`.
