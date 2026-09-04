---
name: ship-loop
description: Run work as a closing loop instead of a trailing-off one. Ticket, branch, implement test-first, dispatch an independent review, fix what blocks, file what does not, and repeat until a review round comes back clean. Use when asked to "run the loop", "keep going until it's right", "loop until the feedback is perfect", "babysit this to done", or when handed a backlog of tickets to work through. Also use to decide what happens to review findings.
origin: authored
tags: [workflow, review, tdd, subagents, loop, tickets]
version: 1.0.0
---

# Ship loop

Most work trails off: implement, glance at it, declare done, leave the findings
in a comment that dies at merge. This is the version that closes.

    ticket -> branch -> implement (test first) -> independent review
           -> fix what blocks, ticket what does not -> review again
           -> stop when a round comes back clean

The loop ends on evidence, not on effort. One clean round after a round that
found nothing new, not "I am tired of this".

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

Write the failing probe before the fix, or you will ship something that never
runs. Then the smallest change that passes, at the root cause: grep every caller
of the function you touch and fix the shared function once.

Two failure modes to watch, both of which produce a commit message that claims a
fix that did not happen:

- **A scripted edit whose anchor matched nothing is a silent no-op.** Assert the
  anchor before every scripted replace.
- **A check that greps for a string proves the code exists, not that it works.**
  Measure behaviour.

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

Then post the verdict where the change lives, including what you did not fix.

## 6. Loop

Go back to step 4 with the new state. Stop when a review round produces nothing
new. If a round produces findings, the next round is mandatory: you have just
changed the code, and the change is unreviewed.

For a backlog, run steps 1 to 5 per ticket and batch the review across a related
group rather than one review per one-line fix.

## Running it unattended

If asked to keep looping without check-ins:

- **Interval work** (waiting on CI, a deploy, a queue): use `/loop` with a delay
  matched to how fast that state actually changes. One check every eight minutes
  for an eight-minute CI run, not eight checks a minute apart.
- **Report once per turn**, a digest, not one message per agent finishing.
- **Stop and ask** if two consecutive rounds fail on the same finding. That means
  the diagnosis is wrong, and more loops will not fix a wrong diagnosis.
- **Never fabricate a pending result.** If a review is still running, say so.

## Definition of done

Goal met. Diff reviewed by someone who did not write it. Behaviour verified by
running something, with the output. No orphaned code your change created. Every
finding fixed, ticketed, or rejected in writing. A review round that came back
clean.

## Suggested skills

- `fresh-eye` for step 4. It carries the reviewer prompt skeleton and the
  mutation-testing instructions.
- `mattpocock-skills:tdd` for step 3 when the change is behavioural.
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
- Two rounds fail on the same finding, or a decision is genuinely the human's:
  `/yw-workflow:need-me`, which is the format for that escalation.
- The repo has no CI or branch protection for step 6 to merge into: `/yw-workflow:harden`.
