---
name: fresh-eye
description: Dispatch an independent adversarial reviewer that did not write the code, in an isolated git worktree, to try to break a change rather than agree with it. Use before merging anything non-trivial, when asked for "a fresh eye", "a second opinion", "review this properly", "try to break this", or when you have just finished work and are about to call it done. Also use on the FIX for a previous review, because that is where the next defect usually is.
origin: authored
tags: [review, quality, adversarial, worktree, mutation-testing]
version: 1.5.0
---

# Fresh eye

**In one line:** Sends someone who did not write the code to try to break it.

Say that line back when you start, so whoever invoked this knows
what they got.

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

**Name the role.** Start the reviewer with `subagent_type: "yw-workflow:reviewer"`,
so it shows as a reviewer and not as `general-purpose`. That type has no
Write or Edit tool. It keeps Bash to run tests, so the isolated worktree below is
what protects the code. If the install predates the type, the Agent tool errors
on it: start a `general-purpose` helper and put the role first in its
description (e.g. "Review: PR 12").

**Isolate.** Give the reviewer `isolation: "worktree"`. Never point two agents at
one working directory: file ownership stops two agents editing the same file and
does nothing about `checkout`/`pull`, which move the whole tree.

**Name the base correctly.** Say which branch the work is based on. Stacked
branches are common and a reviewer diffing against `main` reviews the wrong
change. Give the exact command:

    git fetch origin && git diff origin/<base>...origin/<branch>

**Tell it to break things, not to summarize.** The prompt should say: you did not
write this, do not take the author's word for anything, find what is wrong.

**Give it the project's known disease.** Every codebase has a recurring failure
mode. Name it and say "assume it is present until you prove otherwise". Examples
that have paid off: checks that grep for a string instead of measuring behavior;
scripted edits whose anchor silently matched nothing; features that shipped
without ever rendering.

**Name the tier.** The coordinator names one tier in the brief. It sets
whether the reviewer mutates and when a finding blocks. A brief with no tier
means tier 1.

- **Tier 1:** any check whose silent failure lets wrong output through, on CI
  or local. E.g. a sources check, a fact-check gate, or a local guard such as
  `hooks/require-code-review.py`. When that guard fails silently, an
  unreviewed merge goes through. Full mutation tests, three invented
  mutations, and every survivor blocks. The brief also asks the read and
  stub questions in step 3 of the prompt below.
- **Tier 2:** a tool whose failure shows in its output, e.g. a figure tool or
  the hook that renders the PDF after a merge. Run the tests near the change,
  read the code, and try real-world cases. No mutation testing. A finding
  blocks only when wrong output can ship with no sign. A failure a person
  sees at once (e.g. a crash, a stale PDF) is a nit with a ticket.

**Run only the tests near the change.** The reviewer never runs the full suite
or the full render, because CI does that. One exception: the change is to the
render itself and no CI run exists at that commit.

**After a fix, mutate only what the fix changed and code that calls what it
changed (tier 1).** Other code a past round already mutated stays covered.
Name the fix's diff in the brief, e.g.
`git diff <reviewed-sha>..origin/<branch>`.

**Judge only what this branch changed.** Round 1 reviews the branch's diff
against its base. A later round reviews the fix's diff and what the fix
touches. A defect in text or code that this branch did not change is a nit
with a ticket, never blocking. One exception: the branch makes the old text
wrong, e.g. it renames a flag and an old README line still names the old
flag. Then the old line is part of the change and can block.

**A wording finding blocks only when a reader acts wrongly.** It blocks when
a reader who follows the sentence does the wrong thing, e.g. "run X" where X
fails, or "merge needs no review" where it does. A sentence that is only
stronger than its source, or has no source line, is a nit.

**Ask the premise once.** Round 1 asks whether the premise is sound and
whether the change should exist at all, about the whole change. A later round
checks house style on the fix's diff only. The premise does not change
between fix rounds.

**Demand mutation at tier 1.** At tier 1 this is the highest-value
instruction in the prompt. List the specific mutations that MUST fail, and ask
for any that survive, loudly:

    Mutate the source and prove each new check actually fails:
      <mutation 1> -> <check that must fire>
      <mutation 2> -> <check that must fire>
    Revert each after testing. Report any mutation that was NOT caught.

At tier 1, also ask it to invent three more mutations you did not think of,
aimed at the weakest checks. Those are the ones that find things.

**Record the broken inputs, so no round retypes them.** Two kinds of mutation
go into a review. A *broken input* is bad data fed to a check, e.g. a tag with
a typo. A *check mutation* is an edit to the check's own code, e.g. a deleted
branch or a looser regex.

When a check takes its input as an argument (a string, a row, a dict), the
author records each broken input as a test case beside it. A case holds the
input and the problem text it must contain. Add one valid input that must give
no problem. Give each branch its own problem text, so a case shows which branch
fired. These are ordinary tests, written with the check. The tests near the
check run them each round, and CI runs them all.

At tier 1, check mutations stay hand work each round, because the check's
code changes between rounds. The reviewer backs up the check's file, edits
the file in place with a Bash-run script, and runs the cases. Then it restores
the backup. The tests load the real file, so an edit to a copy tests nothing.
For each branch the reviewer breaks, at least one case must fail.

Each survivor has one route, and the route depends on the tier. At tier 1, a
surviving broken input or check mutation becomes the case that kills it, and
it blocks. A case is cheap to run, but it changes code, so it costs one
more review round (`ship-loop` step 6). At tier 2, a
finding follows the tier 2 rule above, and a nit's ticket holds the case. At
tier 1, a code breakage that a script's own self-check missed becomes a
`mutation-gate` entry. Cases go when their check goes. The measurement behind
this rule is in `docs/DECISIONS.md` (2026-11-04).

**Ask what a bound excludes.** If the change narrows a promise ("works above
1024 wide"), ask directly: is that bound justified by the physics of the problem,
or was it chosen to put the failing cases outside the promise? Goalpost-moving is
easy to do accidentally and invisible in a diff.

**Ask what the inputs never reach.** A check that finds nothing may be correct
and never exercised. Ask which regions of the input space no test renders.

**Diff every claim against its source.** When the change writes a sentence that
makes a factual claim to a reader (site copy, a report, a README claim), the
author wrote its source line first: the exact quote (or the command that
measures a number or a behavior), where it lives, its date.
The reviewer compares sentence to quote, and marks each finding by the
wording rule above. Before a PR exists, the source lines are in
the diff (a comment or a sources file) or in the author's report. Paste the
report's lines into the review prompt. The reviewer runs the author's commands
and judges whether each command measures what its sentence claims. Where a
command does not measure its sentence, or a line is missing, the reviewer
writes its own. E.g. a `grep -c case` that also counts comment lines does not
measure "52 cases".

**Forbid fixing.** "Do not fix anything. Do not commit." A reviewer that fixes
things stops reviewing.

**When the change builds or fixes something, pair it with Matt Pocock's skills.**
Breaking a change finds defects. It does not check the change against the
repo's written standards or against what its ticket asked for, and it cannot
tell a check that was written to fail first from one written after the code.

- The author builds with `mattpocock-skills:tdd`, one failing test before each
  slice of code. A bug fix starts with `mattpocock-skills:diagnosing-bugs`, which
  refuses to theorize until one command already fails on this bug.
- The reviewer checks that with something it can run. Revert the non-test part
  of the diff and show the new test fails. For a bug fix, show the reproduction
  command fails on the base and passes on the branch. A test that passes with the
  code reverted is a finding.
- On round 1 of a change that touches code, you also start a second reviewer
  for `mattpocock-skills:code-review`, at the same time as the first. A
  docs-only change never gets it, and a fix round uses the first reviewer
  only. The spec and the standards do not change between fix rounds. The `yw-workflow:reviewer` type has no Skill or Agent
  tool, and code-review needs both: it loads as a skill and runs its two axes
  as parallel sub-agents. So start it with `subagent_type: "general-purpose"`
  and `isolation: "worktree"`, and put the role first in its description (e.g.
  "Code review: PR 12"). That type has Write and Edit, so its prompt tells it
  to read only and fix nothing.
- Its prompt carries the fixed point, the spec text, and the tracker and
  standards lines. The fixed point is the branch's commit: it checks out that
  commit detached and runs code-review against the base, since code-review
  diffs against HEAD. The spec text is the ticket or PR body, pasted in, or
  "no spec" if there is none.
- Tell code-review where the tracker and the standards are. A reviewer worktree
  is a fresh checkout, so it can lack `docs/agents/issue-tracker.md`. When that
  file is missing, code-review tells the user to run
  `/setup-matt-pocock-skills`. So tell it the tracker is given in the prompt.
  The tracker line is filled in for the repo, e.g. GitHub Issues
  (`gh issue view <n>`). Name the repo's `CLAUDE.md` as a standards file, plus
  `CODING_STANDARDS.md` or `CONTRIBUTING.md` when the repo has them. If the
  Standards axis found no standards file, report that once, as a nit. Do not
  report that axis as clean.
- The second reviewer starts its report with its own decision line:
  `BLOCK n` when either axis found a blocking finding, where n is the number
  of blocking findings, else `PASS`. Blocking means a
  Standards "hard violation" of a documented standard, or a Spec requirement
  that is "missing or partial" or whose "implementation looks wrong". A
  "judgement call" and "scope creep" are nits. Its Standards and Spec verdicts
  go under Agent-facing specifics in the round's comment, beside the mutation
  results.
- If mattpocock-skills is not installed, say so in the round's comment and
  start only the first reviewer.

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
bury the verdict in prose the reader has to extract themselves. A `REVIEW`
that could have been asked before the build cost a round. `ship-loop` step 3
asks those calls first.

When a round has two reviewers (round 1 of a code change), one decision line covers both. A `BLOCK` from
either one makes the round a `BLOCK`. Else a `REVIEW` from either one makes it
a `REVIEW`. Else the round is a `PASS`.

A round is clean when it returns `PASS`. A `REVIEW` counts as clean only when
the owner's answer needs no code change.

Each round goes on the PR body's `Rounds:` line, in the format `ship-loop`
step 6 gives.

The TL;DR sits at a different altitude from the specifics section. It
describes the user-facing scenario the finding would have caused, leaving the
mechanism to the section below. If a TL;DR sentence names a variable,
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

    Round: <1, or n after a fix>. Review only: <round 1: the diff above;
    later: git diff <reviewed-sha>..origin/<branch> and what it touches>.
    A defect in text or code this branch did not change is a nit with a
    ticket, unless this branch makes it wrong.

    Tier: <1 or 2>. <That tier's rule, pasted from "Name the tier".>
    Tier 1, mutate only: <the full diff, or after a fix, the fix's diff and
    code that calls what it changed>.

    1. Run <the repo's own check command>. It must exit 0.
       Then run the tests near the change: <the test files>. Never run the full
       suite or the full render. CI runs those. One exception: the change is
       to the render, and no CI run exists at that commit. NOTE: a check reports
       failures on stderr and signals with its exit code; do not grep stdout.
    2. Tier 1: run the recorded broken-input cases. Then back up the check's
       file, mutate it in place, run the cases, and restore the backup. A
       case must fail for each branch you break:
       <list>
       Report any that survived, loudly. Name each survivor's route. A
       surviving broken input or check mutation becomes a new case. A
       script breakage its own self-check missed becomes a `mutation-gate`
       entry.
       Tier 2: do no mutation testing. Read the code and try real-world
       cases, e.g. <cases>. Mark each finding by the tier 2 rule above.
    3. Tier 1 only: invent three more mutations aimed at the weakest checks.
       Then answer two questions. What does this check read that CI may not
       have (a commit on a deleted branch, a shallow clone, a remote file)?
       What does it do when that read fails? A failed read must fail the
       check with its own message, never count as empty or absent.
       Which side effects of the real tool does the test stub leave out
       (files it erases or makes, run time, signals)? Would the code fail if
       they happened?
    4. Is the promised bound justified by the problem, or chosen to exclude
       failures?
    5. What part of the input space does nothing exercise?
    6. Anything orphaned, dead, scope creep, or a comment claiming something the
       code does not do?
    7. Both tiers, because it is cheap and checks the fix itself. If this
       change builds or fixes code: revert the non-test part of the
       diff and show the new test fails (for a fix, show the reproduction fails
       on the base and passes on the branch).
    8. For every sentence that makes a factual claim to a reader, find its
       source line (exact quote or the command that measures it, where it
       lives, date). The author's source lines: <pasted in, or "none">.
       Run each command and compare its output with the line. Judge whether
       the command measures what the sentence claims (e.g. a count that also
       counts comment lines does not). Where it does not, or where a line is
       missing, write your own command. Diff the sentence against
       the quote. BLOCKING only when a reader who follows the sentence
       does the wrong thing. Only stronger than the quote, or no source
       line: nit.
    9. Does the changed text match house style (the repo's CLAUDE.md,
       README, or style guide)? Round 1 only: is the premise sound? Should
       this exist at all?

    Report each finding with file:line, BLOCKING or nit, the concrete failure
    scenario (inputs -> wrong output), and how you verified it. Say plainly
    whether this is mergeable. Do not fix anything. Do not commit.

The second reviewer, on round 1 of a change that builds or fixes code:

    You run mattpocock-skills:code-review on a change you did not write.

    Fixed point: <branch> at <commit>, based on <base branch>.
      git fetch origin && git switch --detach <commit>
    Run code-review against origin/<base branch>.

    Spec: <the ticket or PR body, pasted in, or "no spec">.

    The tracker is <the tracker line, filled in for the repo, e.g. GitHub
    Issues (`gh issue view <n>`)>. The tracker is given here, so do not stop
    for `/setup-matt-pocock-skills`. The standards files are the repo's
    `CLAUDE.md`, plus `CODING_STANDARDS.md` or `CONTRIBUTING.md` when the
    repo has them. If the Standards axis found no standards file, report
    that once, as a nit. Do not report that axis as clean.

    Start with one decision line: BLOCK n if either axis found a blocking
    finding, where n is the number of blocking findings, else PASS.
    Blocking means a Standards "hard violation" of a
    documented standard, or a Spec requirement that is "missing or partial"
    or whose "implementation looks wrong". A "judgement call" and "scope
    creep" are nits. Then report the Standards and Spec verdicts. Read
    only. Do not fix anything. Do not commit.

## Hands off to

- Always run in its own worktree: `/yw-workflow:git-lanes` covers that, and a reviewer never
  works in the author's tree.
- Findings come back: `/yw-workflow:ship-loop` step 5 triages them, and the fix gets its own
  review round. The fix is where the next defect usually is.
- A finding is a product or design call rather than a defect: `/yw-workflow:need-me`, because
  the reviewer cannot settle it and neither can the author.
