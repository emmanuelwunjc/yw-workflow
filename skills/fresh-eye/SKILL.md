---
name: fresh-eye
description: Dispatch an independent adversarial reviewer that did not write the code, in an isolated git worktree, to try to break a change rather than agree with it. Use before merging anything non-trivial, when asked for "a fresh eye", "a second opinion", "review this properly", "try to break this", or when you have just finished work and are about to call it done. Also use on the FIX for a previous review, because that is where the next defect usually is.
origin: authored
tags: [review, quality, adversarial, worktree, mutation-testing]
version: 1.1.0
---

# Fresh eye

An agent reviewing its own work is a self-check. It is not a review. This skill
dispatches someone else.

## When to use it

- Before merging any change that is not a typo.
- On the FIX for a previous review. Each fix to a check tends to open a different
  hole in it, and the second review routinely finds defects the first one's fix
  introduced. One clean round is not enough for new checking code.
- When a change alters a global property (a layout invariant, a timeout, an
  auth boundary). Requirements written under the old assumption rot silently.

Green CI is not a review. CI proves the tests pass. It does not prove the change
matches what its issue asked for, and it does not catch a bad design decision.

## How to run it

**Isolate.** Give the reviewer `isolation: "worktree"`. Never point two agents at
one working directory: file ownership stops two agents editing the same file and
does nothing about `checkout`/`pull`, which move the whole tree.

**Name the base correctly.** Say which branch the work is based on. Stacked
branches are common and a reviewer diffing against `main` reviews the wrong
change. Give the exact command:

    git fetch origin && git diff origin/<base>...origin/<branch>

**Tell it to break things, not to summarise.** The prompt should say: you did not
write this, do not take the author's word for anything, find what is wrong.

**Give it the project's known disease.** Every codebase has a recurring failure
mode. Name it and say "assume it is present until you prove otherwise". Examples
that have paid off: checks that grep for a string instead of measuring behaviour;
scripted edits whose anchor silently matched nothing; features that shipped
without ever rendering.

**Demand mutation, not reading.** This is the highest-value instruction in the
prompt. List the specific mutations that MUST fail, and ask for any that survive,
loudly:

    Mutate the source and prove each new check actually fails:
      <mutation 1> -> <check that must fire>
      <mutation 2> -> <check that must fire>
    Revert each after testing. Report any mutation that was NOT caught.

Then ask it to invent three more mutations you did not think of, aimed at the
weakest checks. Those are the ones that find things.

**Ask what a bound excludes.** If the change narrows a promise ("works above
1024 wide"), ask directly: is that bound justified by the physics of the problem,
or was it chosen to put the failing cases outside the promise? Goalpost-moving is
easy to do accidentally and invisible in a diff.

**Ask what the inputs never reach.** A check that finds nothing may be correct
and never exercised. Ask which regions of the input space no test renders.

**Forbid fixing.** "Do not fix anything. Do not commit." A reviewer that fixes
things stops reviewing.

## Reading the result

Believe measurements. Do not automatically believe conclusions: reviewers are
confidently wrong too. Two things to check before acting:

- Did it verify by running something, or by reading code and reasoning? Reasoned
  findings need reproducing before you change anything.
- Does its measurement method have an artifact? Ask how it measured. A reviewer
  measuring the wrong thing carefully still reports a defect that is not there.

When a finding lands, reproduce it yourself, then fix the ROOT cause. Grep every
caller of the function you are about to touch: one guard in the shared function
is a smaller diff than a guard in every caller, and patching only the path the
report names leaves every sibling caller broken.

## Closing the loop

**A review that finds something is not finished until that something is written
down.** Blocking findings get fixed in the branch, and the fix is the record.
Everything else becomes a ticket, written agent-ready: reproduction, acceptance
criteria as checkable boxes, literal verification commands. A nit that lives only
in a review comment dies when the branch merges.

If a finding is deliberately not acted on, say so with the reason. "Considered
and rejected" and "never noticed" look identical six months later, and only one
of them is acceptable.

Then post the verdict where the change lives, including what you did NOT fix and
why. See `ship-loop` for running this repeatedly until the feedback is clean.

**Every round's posted comment has a fixed shape**, whether it's the first round
or the fifth fix-and-re-review cycle:

    <ONE OR TWO WORD DECISION>

    ## Executive TL;DR
    <2-4 sentences, framed around the use / the case, not the implementation.
    Say what a person trying to do a real thing would have experienced, not
    which variable or line misbehaved. "A partner who logged a recent visit
    still got flagged as stale" beats "effective_contact returns the wrong
    value when lastContacted post-dates the newest event". A reader who never
    opens the diff should still know what almost went wrong and for whom.>

    ## Agent-facing specifics
    <the existing detailed format: file:line, BLOCKING or nit, the concrete
    failure scenario (inputs -> wrong output), how it was verified (ran vs.
    reasoned), and the mergeable/not verdict. This is for the next agent that
    picks up the fix, not for a person skimming.>

The decision line is the first thing on the page and is exactly one or two
words: `PASS`, `BLOCK`, or `REVIEW` (a call only a person can make, e.g. a
deliberate tradeoff the reviewer can't approve or reject on its own). Never
bury the verdict in prose the reader has to extract themselves.

The TL;DR is not a shorter version of the specifics section, it is a different
altitude: it describes the user-facing scenario the finding would have caused,
not the mechanism that caused it. If a TL;DR sentence names a variable,
function, or line number, it belongs in Agent-facing specifics instead.

## Prompt skeleton

    You are an independent adversarial reviewer. You did NOT write this change.
    Your job is to find what is wrong with it, not to agree with it.

    Base: <branch>, based on <base branch>, NOT main.
      git fetch origin && git diff origin/<base>...origin/<branch>

    Read first: <the requirements or spec files>.

    The change claims: <claims, one line each>.

    This project's recurring failure mode is <disease>. Assume it is present
    until you prove otherwise.

    1. Run <the gate command>. It must exit 0. NOTE: it reports failures on
       stderr and signals with its exit code; do not grep stdout.
    2. Mutate the source and prove each new check fails:
       <list>
       Revert each after. Report any that survived, loudly.
    3. Invent three more mutations aimed at the weakest checks.
    4. Is the promised bound justified by the problem, or chosen to exclude
       failures?
    5. What part of the input space does nothing exercise?
    6. Anything orphaned, dead, scope creep, or a comment claiming something the
       code does not do?

    Report each finding with file:line, BLOCKING or nit, the concrete failure
    scenario (inputs -> wrong output), and how you verified it. Say plainly
    whether this is mergeable. Do not fix anything. Do not commit.
