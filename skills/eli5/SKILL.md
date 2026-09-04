---
name: eli5
description: Explain a topic like the reader knows nothing about it, as an HTML artifact with big pictures and few words. Use when the user asks to "eli5", "explain like I'm 5", or wants a dead-simple visual explainer instead of a text answer. Prefer this over eli5-text when the explanation will be re-read, shared, or kept.
origin: authored
tags: [explanation, artifact, svg, teaching]
version: 1.0.0
---

# eli5

**In one line:** Explains a topic to someone with zero background, as a page of
big pictures and few words.

Say that line back when you start, so whoever invoked this knows what they got.

Explain the topic for someone with zero background. No jargon. No prerequisites assumed.

## Output

Always an HTML artifact, not a text answer.

- Big pictures. Prefer one dominant visual per screen/section: a simple diagram, icon, or shape built in inline SVG. No stock photos, no external images.
- Few words. Short labels and single sentences, never paragraphs. If a sentence needs "and" or "because" more than once, cut it.
- One idea per section. Break the topic into 3-6 bite-size steps or panels, each with its own picture and its own one-line explanation.
- Plain, concrete language. Real-world comparisons over abstract terms (e.g. "like a mail carrier delivering letters" beats "a message-passing protocol").

## Process

1. Load skill `artifact-design` if it is available, per its own trigger rule, to calibrate visual weight for this content. It ships with Claude Code rather than with this plugin.
2. Identify the core idea in one sentence. That sentence anchors the whole page.
3. Break it into a small number of simple steps or parts.
4. For each step, draw one simple SVG picture and write one short line of text.
5. Publish with the `Artifact` tool, which this skill requires. Without it, use `/yw-workflow:eli5-text` instead of half-building a page. Pick a favicon emoji that matches the topic.

## Guardrails

- No walls of text. If a section needs more than ~15 words, the idea isn't broken down enough yet, split it further.
- No technical terms without an immediate plain-language stand-in.
- Keep it legible in both light and dark mode, following `artifact-design` where it is available.

## Hands off to

- The answer is wanted in the conversation rather than as a page to open, or no
  `Artifact` tool is available: `/yw-workflow:eli5-text` is the same discipline
  without the page.
- The explanation keeps growing because the topic is genuinely large: that is a
  signal to split it, and each part gets its own page.
