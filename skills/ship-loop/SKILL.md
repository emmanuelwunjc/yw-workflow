---
name: ship-loop
description: Run work as a closing loop instead of a trailing-off one. Ticket, branch, implement test-first, dispatch an independent review, fix what blocks, file what does not, and repeat until a review round comes back clean. Use when asked to "run the loop", "keep going until it's right", "loop until the feedback is perfect", "babysit this to done", or when handed a backlog of tickets to work through. Also use to decide what happens to review findings.
origin: authored
tags: [workflow, review, tdd, subagents, loop, tickets]
version: 1.5.6
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

The Workflow diagram in this plugin's `README.md` shows where this loop sits
beside the other skills.

## 1. Ticket

Every unit of work starts as a written ticket, agent-ready, so it can feed a
test-first loop without a conversation. It has six parts, each a heading in
this plugin's issue template, `.github/ISSUE_TEMPLATE/ticket.md` in the
yw-workflow repo:

- **ELI5.** Always first. Two or three plain sentences a five-year-old could
  follow: what this is and why it matters. No file names and no jargon, e.g.
  "The robot forgets what it did yesterday. So it does the same work twice.
  This makes it remember."
- **Problem.** What is wrong, with a real example, and the function or
  behavior that changes.
- **Reproduction.** The literal commands and the observed wrong output.
- **Acceptance criteria.** Checkable boxes, each objectively true or false, so
  a criterion reads like "exit code 0 on N rows" rather than "improve X".
- **Verification.** The commands, literally, to paste.
- **Mutation check.** Whether one is expected, i.e. reverting the fix must
  fail something.

In the Problem part, name the function or behavior it changes, e.g.
"`_log` takes the singular object name from a map". Give a file path there
only as a hint, e.g. "(in `scripts/live_write.py` when this was filed)". The
Reproduction and Verification commands keep their literal paths. A file can
move or be cut up before the work starts. In twenty, ticket 521 named the
behavior, but its Reproduction said only "Read `scripts/live_write.py`". PR
630 then cut that file into three and moved `_log` out of it, so the worker
lost time to find the code.

In any repo, write the ticket with these six parts, each as a `## ` heading.
The plugin's own check, `tools/check-repo.py` in the yw-workflow repo, fails
when these bullets and the template headings name different parts.

When the repo has a goal tracker (`tools/tracker_sync.py`), give each ticket
its `slice:` label when you file it: `gh issue create ... --label
slice:<part>`. Pick `<part>` from the keys of the map file the sync reads:
the file its `--config` names, e.g. `.github/tracker-mvp.yml`, else
`.github/tracker-layers.yml` (`grep -h '^  "slice:' <map file>`). When no key
fits, file the ticket with no `slice:` label and name it in your report.
Each sync lists the open issues with none (`goal-tracker` step 9).

A ticket from `mattpocock-skills:to-tickets` is a draft. Its template has
acceptance criteria only, and it leaves out paths and code on purpose. Before
work starts, add the ELI5 on top, the problem, the reproduction, the
verification commands and the mutation check. Tell `to-tickets` to leave off its `ready-for-agent`
label and its `**Status:** ready-for-agent` line until the six parts are in.

A ticket without an acceptance criterion is a wish. Write the demand down when
it is given, then build it. Doing it in the other order is how a set of demands
gets built and never recorded, and then quietly cancelled by a later one.

## 2. Branch

Short-lived branch off trunk, `type/short-description`. Never commit to
`main`/`master`, even solo, even for one line.

When the branch starts, read the open housekeeping tickets (step 7), even if this
ticket is older than they are. A repo with no GitHub tracker reads its own
tracker, or skips this if it has none:

    gh issue list --label housekeeping --state open

If one lists this ticket, or this work fits its pattern, that housekeeping
ticket goes first (step 7, "Moving it to the front"). The branch that runs the
housekeeping ticket itself skips this check.

If another agent or session might be working the repo, **load `/yw-workflow:git-worktrees`**
and take a worktree. Check first with `git status --short` and
`git branch --show-current`: uncommitted changes, or a branch you did not
create, mean someone else is in there. This applies to you, not only to agents
you dispatch. File ownership does not help, because `checkout` and `pull` move
the whole tree.

## 3. Implement, test first

**Name the role.** When you hand this step to a subagent, start it with
`subagent_type: "yw-workflow:builder"`. A helper started without a type shows
as `general-purpose`, and the owner cannot tell a builder from a reviewer.
Fixes after a review go to `yw-workflow:fixer`. Every fixer brief says: check
the whole contract each time, in one assert. The fixer prompt gives the
example. Docs, READMEs and handoff notes go to `yw-workflow:documenter`. If
the install predates these types, the Agent tool errors on them: start a
`general-purpose` helper and put the role first in its description (e.g.
"Build: ticket 41").

**End the brief with the commit line.** Every builder, fixer or documenter brief ends
with "commit your work on your own branch before you return (on a detached
HEAD, `git switch -c wip/<folder>` first), as a WIP commit if it is
unfinished, and report the branch and SHA". `/yw-workflow:git-worktrees` says why.

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

**The seams under test come from the ticket.** They are the seams that the
ticket's Verification commands and acceptance boxes exercise. Name them in the
builder brief, and they count as confirmed for `tdd`. A ticket whose
Verification names no runnable seam goes back to step 1.

Write the failing probe before the fix, or you will ship something that never
runs. Then the smallest change that passes, at the root cause: grep every caller
of the function you touch and fix the shared function once.

A new check that takes its input as an argument ships with its broken-input
cases: bad inputs, each with the problem text it must contain, run by the
suite, and by CI. `fresh-eye` gives the shape and says where a survivor goes.

Two failure modes to watch, both of which produce a commit message that claims a
fix that did not happen:

- **A scripted edit whose anchor matched nothing is a silent no-op.** Assert the
  anchor before every scripted replace.
- **A check that greps for a string proves the code exists, not that it works.**
  Measure behavior.

### mattpocock's `implement` and `implement-spec`

`mattpocock-skills:implement` and `mattpocock-skills:implement-spec` may do
this step only. Their own `code-review` run is a self-check. So step 4 still
dispatches `fresh-eye`.

`implement-spec` runs in the coordinating session, because a builder has no
Agent tool. Start each implementer subagent as `yw-workflow:builder` ("Name
the role"). End each brief with the commit line. At most four implementers run
at once (`/yw-workflow:git-worktrees`).

Refuse the branch it merges every ticket into, its merger subagent, its draft
PR and its step 7. Each ticket ships through this loop on its own.

Each implementer branch starts from trunk. A ticket blocked by another starts
after its blocker merges. Each branch runs steps 4 to 6 and merges like any
other ticket. Several reviewed branches may share one PR with one commit each,
as `~/CLAUDE.md` section 3 says.

## 4. Review (not by you)

Dispatch `fresh-eye`. An agent reviewing its own work is a self-check. Green CI
is not a review either: it proves the tests pass, not that the change matches
what its ticket asked for.

Run the review on the FIX for the previous review too. That is where the next
defect usually is: each fix to a check tends to open a different hole in it.

Name the tier in the brief (`fresh-eye`, "Name the tier"). The reviewer runs
only the tests near the change. At tier 1, after a fix it mutates only the fix
and code that calls what the fix changed.

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

If a finding fits the pattern of an open housekeeping ticket (step 7), the
pattern came back before its general fix. That housekeeping ticket goes first
(step 7, "Moving it to the front").

Then post the verdict where the change lives, including what you did not fix.

## 6. Loop

Go back to step 4 with the new state. If a round changes code, the next round
is mandatory: you have just changed the code, and the change is unreviewed.
At tier 1, a round after a fix mutates only what the fix changed and code
that calls it.

While a review round runs, the coordinator keeps the other `parallel` tasks
running, each in its own worktree. `parallel` is a mark on a `## Next` item
(see skill `handoff`). A review wait is the most common idle time.

Stop on a clean round. A round is clean when it returns `PASS`. A `REVIEW`
counts as clean only when the owner's answer needs no code change. If the
answer changes code, that change gets another round. Nothing changes after a
`PASS`: the reviewed commit merges, and its nits become tickets or are
rejected in writing (step 5).

Three rounds whose blocking count does not fall means change direction. "Does
not fall" means the third of three consecutive rounds has a blocking count no
lower than the first of them. So 3, 1, 3 fires and 3, 2, 1 does not. The count
restarts after a change of direction.

When it fires, say in one line what changed and why, and carry on. Ask the
owner only if the new direction departs from what a grilling settled. This
differs from the rule under "Running it unattended": that one is one finding
surviving a fix, so the diagnosis is wrong. This one is the total holding
steady, so the approach is wrong.

A loop stops at four rounds. A change of direction does not restart this
count. If round 4 still has blocking findings, do not start round 5. Ship the
part that passed and put the rest, with its open findings, into a new ticket.
The ticket names the round-4 sha, or the branch if you keep it, so the removed
work can still be found after a squash merge deletes the branch. E.g. a branch
with a hook fix and a README section merges the part whose findings are fixed.
The split makes a new commit, so it gets one review of the split's diff
(`git diff <round-4-sha>..<split-sha>`), outside the count. That review checks
only that the split removed the unfinished part and broke nothing left. A
`PASS` from it is the clean round that ends the loop. If it does not return
`PASS`, or the change cannot be split, ask the owner (`/yw-workflow:need-me`).

Record every round in the PR body on one line: its verdict, its blocking count,
and the reviewer's token count (the Agent tool's `subagent_tokens` for that
review). Take the count from the usage block of the task notification that
says the review finished, and post the round only after it arrives. Never
estimate it, and never ask the reviewer for it. An Orca worker reports no
token count, so its round carries the verdict and the blocking count alone
(skill `pm`). The coordinating session writes the line after round 1 and
updates it after each round. The line starts exactly `Rounds:`, with no
bullet, bold, backticks, placeholders or annotations. Rounds are separated by
` · `, and a `REVIEW` carries its blocking count like a `BLOCK`. A blocking
finding makes the verdict `BLOCK`, so a `REVIEW` from one reviewer always
carries 0:

    Rounds: BLOCK 3 (95k) · REVIEW 0 (90k) · PASS (88k)

The review of a split after round 4 is the last entry, with the word `split`
before its verdict:

    Rounds: BLOCK 3 (95k) · BLOCK 2 (80k) · BLOCK 2 (70k) · BLOCK 1 (60k) · split PASS (40k)

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

Every PR body opens with `## ELI5`: two or three plain sentences a
five-year-old could follow, saying what the change is and why it matters. The
rest follows the PR template, `.github/pull_request_template.md` in the
yw-workflow repo: what changed (before and after), why, the ticket it closes,
testing, risk and how to back it out.

Each branch writes what the next session needs in a `## Handoff notes` section
of its PR body, and never edits `docs/HANDOFF.md`. The session that merges the
PRs runs the handoff pass before it stops: one `docs/handoff-*` branch that
copies those notes into the log. `/yw-workflow:handoff` has the steps.

If `mattpocock-skills:pr` shapes the PR body, keep its sections and add
`## ELI5` above them, and `## Handoff notes` and the `Rounds:` line, which its
template lacks.

## 7. Housekeeping after a long loop

A ticket that needed three or more fix rounds before its clean round found a
pattern, and the pattern is rarely in one ticket only. A fix round is a round
that returned `BLOCK`, or a `REVIEW` whose answer changed the work. Count every
fix round of the ticket. A change of direction (step 6) does not restart this
count. Before the branch merges:

1. Name the pattern in one general line. E.g. "a write-up states a claim wider
   than the run that measured it", not "line 104 of the 0.3a write-up".
2. Search the tracker for open tickets that can meet it. Search by the kind of
   work, e.g. every ticket that writes up a measurement.
3. File one ticket with the label `housekeeping`. It holds the pattern, the
   general fix, the similar tickets, and the PR that found it. Make the general
   fix a mechanism where one can exist, in the order of `~/CLAUDE.md` section
   3: a hook that blocks it, CI that fails on it, a config setting that forbids
   it. Below those, a rule in a ticket template or reviewer prompt, then prose.

Create the label once for each repo. `--force` makes a second run harmless and
still reports a real error:

    gh label create housekeeping --force --description "General fix for a pattern a long review loop found"

### Moving it to the front

The housekeeping ticket waits in the queue as ordinary work. It moves to the
front at two points: when a branch starts on work it lists or that fits its
pattern (step 2), and when a review finding fits its pattern (step 5). Do not
wait for a batch, because each recurrence costs a full review loop.

1. Freeze the branch: commit its work. Never put the general fix into that
   branch.
2. Run the housekeeping ticket through this loop, in a new worktree
   (`git-worktrees`) on a branch from trunk. Put `Closes #N` in its PR body, so the
   ticket closes on merge and the check at branch start stops finding it. Merge
   it.
3. Rebase the branch on trunk and continue. The rebase changes the work, so the
   next review round is mandatory (step 6).

Two branches can start the same housekeeping ticket at the same time. This step
has no guard against that, because a rare duplicate costs less than the guard.

If the general fix needs an owner call, queue the call for the owner and
continue other branches.

### A finding from `retro`

A `mattpocock-skills:retro` finding that a mechanism can fix goes to a
housekeeping ticket. A finding that is a habit goes to `LESSONS.md`, beside
`~/CLAUDE.md`. Add to `CODING_STANDARDS.md` only in a repo that already has
one.

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
clean, as step 6 defines it, or a review of a split after round 4 that returned
`PASS` (step 6). A `Rounds:` line in the PR body. A housekeeping ticket, if the
loop took three or more fix rounds (step 7).

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
- The backlog serves one goal with a target date and more than one part:
  `/yw-workflow:goal-tracker` sets up a pinned issue whose progress bars
  update with no hand edits.
- Anyone else may be in the repo: `/yw-workflow:git-worktrees` for step 2. It is the
  deep version of the rule stated there.
- Step 4 is `/yw-workflow:fresh-eye`, always, and again on the fix. A round that
  found something is the middle of the loop.
- A decision is genuinely the owner's (a step 3 call, or a new direction or
  diagnosis that departs from a grilling): `/yw-workflow:need-me`, which is the
  format for that escalation.
- The repo has no CI or branch protection for step 6 to merge into: `/yw-workflow:harden`.
- The change needs explaining to someone who will not read the diff:
  `/yw-workflow:eli5` for a page they keep, `/yw-workflow:eli5-text` in passing.
