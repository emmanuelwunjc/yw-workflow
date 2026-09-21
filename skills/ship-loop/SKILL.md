---
name: ship-loop
description: Run work as a closing loop instead of a trailing-off one. Ticket, branch, implement test-first, dispatch an independent review, fix what blocks, file what does not, and repeat until a review round comes back clean. Use when asked to "run the loop", "keep going until it's right", "loop until the feedback is perfect", "babysit this to done", or when handed a backlog of tickets to work through. Also use to decide what happens to review findings.
origin: authored
tags: [workflow, review, tdd, subagents, loop, tickets]
version: 1.1.0
---

# Ship loop

**In one line:** Runs work as a loop that closes: ticket, branch, test first, review, fix, repeat.

Say that line back when you start, so whoever invoked this knows what they
got.


Most work trails off: implement, glance at it, declare done, leave the findings
in a comment that dies at merge. This is the version that closes.

    ticket -> branch -> implement (test first) -> independent review
           -> fix what blocks, ticket what does not -> review again
           -> stop when a round comes back clean

Step 6 says exactly when the loop stops.

## 1. Ticket

Every unit of work starts as a written ticket, agent-ready, so it can feed a
test-first loop without a conversation:

- **Reproduction.** The literal commands and the observed wrong output.
- **Acceptance criteria as checkable boxes.** Objectively true or false, so a
  criterion reads like "exit code 0 on N rows" rather than "improve X".
- **Verification commands**, literally, to paste.
- **Whether a mutation check is expected**, i.e. reverting the fix must fail
  something.

A ticket without an acceptance criterion is a wish. Write the demand down when
it is given, then build it. Doing it in the other order is how a set of demands
gets built and never recorded, and then quietly cancelled by a later one.

## 2. Branch

Short-lived branch off trunk, `type/short-description`. Never commit to
`main`/`master`, even solo, even for one line.

If another agent or session might be working the repo, **load `/yw-workflow:git-lanes`**
and take a worktree. Check first with `git status --short` and
`git branch --show-current`: uncommitted changes, or a branch you did not
create, mean someone else is in there. This applies to you, not only to agents
you dispatch. File ownership does not help, because `checkout` and `pull` move
the whole tree.

## 3. Implement, test first

**UI or on-screen copy: get the owner's calls before you build.** An owner's
call is one of three things: a claim the sources do not settle, a design or
layout choice, or a tradeoff. A reviewer would label it `REVIEW` (see
`fresh-eye`). A sentence with a source, no stronger than its quote, needs no
call, because the next rule covers it. Skip a call that has a conventional
default, one the brand or house style already settles, and one already made
(in the repo's plan, a grilling, or `docs/HANDOFF.md`). Show the rest to the
owner as something cheap: a screenshot of a rough build or a mockup, or the
sentences with their sources. Batch them through AskUserQuestion, up to four per
call, each with a recommended option (the `need-me` format). Build after the
answer. In an unattended run, build what the calls do not touch and queue the
calls for the owner. A call that arrives after the build costs a review round
(e.g. a logo, a layout band, who owes a report, a chart axis).

**Source first, then sentence.** Any sentence that makes a factual claim to a
reader (site copy, a report, a README claim) starts as its source line: the
exact quote (or, for a number or a behavior claim, the command that measures
it), where it lives, and its date. Write the sentence after it, and
never stronger than the quote. Keep the source line beside the sentence (a
comment, a sources file, or the PR body), so the review becomes a diff of
sentence against quote. A fix to copy can make a new defect, as in
edsim_funder_impact #92.

Write the failing probe before the fix, or you will ship something that never
runs. Then the smallest change that passes, at the root cause: grep every caller
of the function you touch and fix the shared function once.

Two failure modes to watch, both of which produce a commit message that claims a
fix that did not happen:

- **A scripted edit whose anchor matched nothing is a silent no-op.** Assert the
  anchor before every scripted replace.
- **A check that greps for a string proves the code exists, not that it works.**
  Measure behavior.

## 4. Review (not by you)

Dispatch `fresh-eye`. An agent reviewing its own work is a self-check. Green CI
is not a review either: it proves the tests pass, not that the change matches
what its ticket asked for.

Run the review on the FIX for the previous review too. That is where the next
defect usually is: each fix to a check tends to open a different hole in it.

## 5. Triage the findings, and record all of them

Every finding gets exactly one of three outcomes, and all three are written down:

| Outcome | Where it goes |
|---|---|
| Blocking | Fixed in this branch. The fix is the record. |
| Real but out of scope | A new ticket, agent-ready, before the branch merges. |
| Considered and rejected | Written down WITH the reason, in the record. |

The third is the one people skip. "Considered and rejected" and "never noticed"
look identical later, and only one of them is fine. If a reviewer asks for
something and you measured it and it cost too much, say so with the number.

A finding that asks for a guard on work that belongs to a later ticket goes
into that ticket's acceptance criteria. A guard protects only behavior that
exists today. Written ahead of the code, it has nothing to fail against, and it
still costs a round. This ticket's own failing probe still comes first.

Then post the verdict where the change lives, including what you did not fix.

## 6. Loop

Go back to step 4 with the new state. If a round changes code, the next round
is mandatory: you have just changed the code, and the change is unreviewed.

Stop on a clean round. A round is clean when it returns `PASS`. A `REVIEW`
counts as clean only when the owner's answer needs no code change. If the
answer changes code, that change gets another round. A clean round ends the
loop only when nothing changes after it. Nits fixed in code after a `PASS` get
one more round; otherwise they go to a ticket.

Three rounds whose blocking count does not fall means change direction. "Does
not fall" means the third of three consecutive rounds has a blocking count no
lower than the first of them. So 3, 1, 3 fires and 3, 2, 1 does not. The count
restarts after a change of direction.

When it fires, say in one line what changed and why, and carry on. Ask the
owner only if the new direction departs from what a grilling settled. This
differs from the rule under "Running it unattended": that one is one finding
surviving a fix, so the diagnosis is wrong. This one is the total holding
steady, so the approach is wrong.

Record every round in the PR body on one line: its verdict, its blocking count,
and the reviewer's token count (the Agent tool's `subagent_tokens` for that
review). The coordinating session writes the line after round 1 and updates it
after each round. The line starts exactly `Rounds:`, with no bullet, bold,
backticks, placeholders or annotations. Rounds are separated by ` · `, and a
`REVIEW` carries its blocking count like a `BLOCK`:

    Rounds: BLOCK 3 (95k) · REVIEW 0 (90k) · PASS (88k)

That makes the three-round rule checkable at a glance. The averages are one
command, which reads the first `Rounds:` line of each PR:

    gh pr list --state merged --limit 100 --json body \
      --jq '.[] | [.body | splits("\r?\n") | select(startswith("Rounds:"))][0] // empty' |
      awk '{ sub(/^Rounds:[ \t]*/, "") } $0 != "" {
             n++; r += gsub(/·/, "&") + 1
             while (match($0, /\([0-9.]+k\)/)) {
               tk += substr($0, RSTART + 1, RLENGTH - 3); tr++
               $0 = substr($0, RSTART + RLENGTH) } }
           END { if (n) printf "%d PRs, %.1f rounds each\n", n, r / n
                 if (tr) printf "%.0fk tokens per round, over %d rounds\n", tk / tr, tr }'

For a backlog, run steps 1 to 5 per ticket and batch the review across a related
group rather than one review per one-line fix.

Each lane writes what the next session needs in a `## Handoff notes` section
of its PR body, and never edits `docs/HANDOFF.md`. The session that merges the
PRs runs the handoff pass before it stops: one `docs/handoff-*` branch that
copies those notes into the log. `/yw-workflow:handoff` has the steps.

## Running it unattended

If asked to keep looping without check-ins:

- **Interval work** (waiting on CI, a deploy, a queue): use `/loop` with a delay
  matched to how fast that state actually changes. One check every eight minutes
  for an eight-minute CI run, not eight checks a minute apart.
- **Report once per turn**, a digest, not one message per agent finishing.
- **Rediagnose** if two consecutive rounds fail on the same finding. That means
  the diagnosis is wrong, and more loops will not fix a wrong diagnosis. Ask the
  owner only if the new diagnosis departs from what a grilling settled.
- **Never fabricate a pending result.** If a review is still running, say so.

## Definition of done

Goal met. Diff reviewed by someone who did not write it. Behavior verified by
running something, with the output. No orphaned code your change created. Every
finding fixed, ticketed, or rejected in writing. A review round that came back
clean, as step 6 defines it. A `Rounds:` line in the PR body.

## Suggested skills

- `fresh-eye` for step 4. It carries the reviewer prompt skeleton and the
  mutation-testing instructions.
- `mattpocock-skills:tdd` for step 3 when the change is behavioral.
- `mattpocock-skills:diagnosing-bugs` for step 3 when the change fixes a bug: it
  gets one command failing on the bug before any fix.
- `security-review` in addition to `fresh-eye` for anything touching auth, input
  handling, secrets, or outbound calls.
- `/loop` for unattended interval running.

## Hands off to

- The backlog is too big to grind ticket by ticket, or the tickets are decisions
  rather than work: `/yw-workflow:wayfinder` charts it first. This skill builds what is
  already decided.
- A ticket is not agent-ready, or the goal is ambiguous: `/yw-workflow:grill` before step 1.
- Anyone else may be in the repo: `/yw-workflow:git-lanes` for step 2. It is the
  deep version of the rule stated there.
- Step 4 is `/yw-workflow:fresh-eye`, always, and again on the fix. A round that
  found something is the middle of the loop.
- A decision is genuinely the owner's (a step 3 call, or a new direction or
  diagnosis that departs from a grilling): `/yw-workflow:need-me`, which is the
  format for that escalation.
- The repo has no CI or branch protection for step 6 to merge into: `/yw-workflow:harden`.
- The change needs explaining to someone who will not read the diff:
  `/yw-workflow:eli5` for a page they keep, `/yw-workflow:eli5-text` in passing.
