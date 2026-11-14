# Decisions

Measured findings behind the skills. These carry a date because they age:
re-measure before trusting one that is old. The skills stay procedure, so a
moving tool version does not rot them.

A decision is superseded, never deleted. Mark it with the date and what
replaced it.

## 2026-09-21: owner's calls before the build, sources before sentences, a Rounds line

Supports `ship-loop` and `fresh-eye`. The owner read one day of review-loop
data from edsim_funder_impact. Extra review rounds had four causes:

1. Guards that could not fail.
2. A fix that made a new defect, for example in copy checked against sources
   (edsim_funder_impact #92).
3. A call only the owner could make, arriving after the build
   (edsim_funder_impact #89, #71, #92, #100).
4. Guards for work not built yet (edsim_funder_impact #98).

The day's counts came from the coordinating session's notes and cannot be
recounted from GitHub, so they are left out here.

The owner chose three changes. Ask the owner's calls before building UI or
copy. Write each claim's source line before its sentence. Record every round
on a `Rounds:` line in the PR body. Keeping the reviewer's breaks as a script
was considered and not chosen.

A cheaper design came first and was dropped the same day: fix-only review
rounds, an optional smaller model, and a forced final full round. The final
round would add a full round to every PR with two or more fix rounds. And the
rule's own wording took several review rounds to get right. The loop now stops
on a clean round.

Measurement starts now. Each round's verdict, blocking count and tokens go on
the `Rounds:` line, and `ship-loop` step 6 has the command that averages them.

## 2026-08-27: rebuild venvs per lane, never copy one

Supports `git-lanes`. A copied venv is slower AND broken.

Measured 2026-08-27 on a 72 MB, 3,134-file venv (pandas, numpy, requests,
pytest), macOS arm64:

```
reflink copy of .venv       0.35s   12 files broken
uv venv && uv pip install   0.08s    0 files broken
```

Rebuilding is four times faster AND correct, because `uv` hardlinks packages out
of `~/.cache/uv`, which every worktree on the machine shares. Copying wins only
on a cold cache, which happens once per machine.

The copy is also wrong in a way that hides. `bin/python` is a symlink out of the
tree, so `sys.prefix` relocates and `import pandas` works, which makes the copy
look fine. But `bin/activate` and every console script (`bin/pytest`,
`bin/f2py`, `bin/pygmentize`) hardcode the SOURCE worktree's absolute path on
line 2. So lane B runs lane A's interpreter for as long as lane A exists, and
`bin/pytest` dies with `No such file or directory` the moment lane A is removed.
That is cross-lane contamination, the one thing worktrees exist to prevent,
arriving through the cache optimisation meant to speed them up.

Build the venv fresh in each lane. Put it in a creation hook if your tooling has
one, never in a copy step.

## 2026-08-27: a git wrapper bypasses the safety hook, and worktrunk evaluated

Supports `git-lanes` and `harden` (renamed `hardcore` on 2026-11-13). Take `wt switch` and `wt remove`. Refuse
`wt merge`, and block it in the hook before anyone runs it.

This plugin's `hooks/git-safety-guard.sh` matches on the literal string `git `. Any
tool that wraps git (worktrunk's `wt`, lazygit, a Makefile target, a script)
runs its git operations as its own subprocesses and never presents a `git`
command to the Bash tool, so every rule in that hook silently stops applying:
no "do not move a tree while a mutation harness runs", no "no commit on main".

Adopting such a tool means adding matching rules for ITS command names to that
hook, in the same commit. A tool that is only a convenience layer over commands
the hook already guards is a hole in it.

Evaluated 2026-08-27: worktrunk (`wt`, github.com/max-sixty/worktrunk) is a thin
Rust wrapper that reads worktrees straight from git, so lanes created by hand
with `git worktree add` appear in `wt list` with no migration. Two things it
does better than raw git: `wt switch` onto a branch another worktree holds
NAVIGATES there instead of failing or detaching, which removes the checkout
footgun this whole skill exists for, and `wt remove` detects a squash-merged
branch that `git branch --merged` does not list. Two things to refuse: `wt
merge` fast-forwards LOCAL trunk with commits that never passed a required
status check, and no config disables it, so block it in the hook before anyone
runs it. And its path template has no stateful filter, so it cannot produce the
`NN-name` counter: keep creating lanes with `git worktree add`.

## A path resolver for gitignored data, not yet built (2026-09-08)

`git-lanes` tells a lane to read and write gitignored input data from the main
checkout, and prose is the weakest form that rule can take: it asks every script
author to remember, and the failure it prevents is silent in both directions.

The mechanism form is a resolver every script routes through, which refuses to
resolve a gitignored path that exists in both the lane and the main checkout,
and names both files when it refuses. That turns the ambiguous case from a run
that quietly succeeds against the wrong file into a run that will not start.

Nobody has built it. Recorded here rather than in the skill because a skill is
procedure a reader can follow, and a design nobody has implemented is not.

## 2026-09-17: the review gate asks the repo the merge targets, and blocks when it cannot tell

Supports `hooks/require-code-review.py`.

Reproduced 2026-09-17. A session started in repo A ran
`cd <a second repo> && gh pr merge 24 --squash --delete-branch`. The hook ran
`gh pr view 24` in its own working directory, so it read repo A's PR 24: old,
merged, 36 code lines, no review. It blocked. The second repo's PR 24 carried a
posted "Verdict: PASS". The only way through was `SKIP_REVIEW_GATE=1`.

The mirror case needs no bad luck, only a shared PR number: repo A's PR is
reviewed or trivial, and the hook passes the merge of an unreviewed PR in the
second repo. Both directions are pinned in
`hooks/require-code-review-selftest.py`, which runs the hook against a fake `gh`
that answers per repo and logs which repo each call resolved to.

Decided: the hook copies the merge's context and lets `gh` resolve it. It reads
the directory the shell is in when `gh` runs (`cd`, `pushd`, subshells, starting
from the hook event's `cwd`), `GH_REPO=` and `GH_HOST=` assignments,
`-R`/`--repo` on either side of `pr merge`, and the PR argument as typed, which
may be a URL. It passes all of them to every `gh` call.
`gh` applies its own precedence: URL, then `-R`, then `GH_REPO`, then the
directory's remote. Rejected: resolving `owner/repo` inside the hook, which
would be a second copy of that precedence to keep in step with `gh`.

Decided: a target the hook cannot read blocks, with a message that says what
was unreadable and asks for `gh pr merge <number> -R owner/repo`. Examples:
`cd "$DIR"`, `cd -`, `popd`, unbalanced quotes, `xargs` in front of `gh`, and a
repo or host that is not a literal (`$REPO`, backticks). The hook already passes
when a lookup comes back empty, because a network blip must not wedge a local
merge. That reasoning stops short of this case. A blip is transient and nothing
the caller types fixes it. An unreadable target is permanent for that command
and one flag fixes it. Falling back to the session repo is the defect itself.

Decided, then reversed: a `cd` to a literal path that does not exist is
unchanged rather than unknown. The `cd` fails, so `;` leaves the shell where it
was and `&&` drops the merge entirely. Both answers are the old directory. The
first version called it unknown and blocked, which cost a false block on a
heredoc writing `cd other && gh pr merge 25` into a file, a command 1.6.0
allows. The ceiling: a directory this same command creates first (`git clone x
&& cd x && gh pr merge 24`) is judged in the old directory, which is 1.6.0's
answer rather than a new hole.

## The two rounds that changed the approach

Review round 1, same day: BLOCK, three false passes. Each was a merge the hook
could see and then passed with no `gh` call.

- A regression. The first version replaced the text match with a word walk, and
  the walk read a quoted string as a command only when `bash`, `sh`, `zsh` or
  `eval` was the first word. `timeout 60 bash -c 'gh pr merge 24'`, `env bash -c
  ...`, `sudo -u me sh -c ...` and a backticked merge went through unchecked.
  1.6.0 caught all four with its plain text match.
- A variable where a literal is needed: `gh pr merge $n` in a `for` loop,
  `-R $REPO`, `GH_REPO=$R`. The lookup failed, a failed lookup reads as a
  network blip, and hook mode allows a blip.
- `gh -R owner/repo pr merge 25`. `gh` takes `-R` before the subcommand, and
  both halves wanted `pr` right after `gh`.

Review round 2, on the rewrite that answered round 1: BLOCK, four findings. The
rewrite had regressed detection further.

- Merges 1.6.0 caught now passed: a merge in a command substitution inside a
  quoted argument (`echo "out: $(gh pr merge 24)"`), `echo '<a merge>' | sh`,
  and arguments git itself runs such as `git rebase --exec`.
- Read-only commands 1.6.0 allowed now blocked: 23 of 48 realistic non-merge
  commands, against 11 for 1.6.0. Among them `grep -rn "gh pr merge" hooks/`,
  `rg`, `sed`, `awk`, `jq` and `gh pr merge --help`.

Decided after round 2, and this is the rule the code is built around. Blocking
findings went 3, then 4, and every exception added to the walk opened the next
hole. A word walk that has to decide what is and is not a merge is a shell
parser. Detection was never the defect, so detection goes back to 1.6.0's text
pattern and the walk answers one question about merges the pattern already
found: which repo to ask about.

What that buys: every shape 1.6.0 blocks is blocked again, and every read-only
shape 1.6.0 allows is allowed again. Measured on the same 48 commands, run twice
(once from a session whose repo has PR 24 unreviewed and PR 25 reviewed, once
reversed): 1.6.0 blocks 9 and 11, this hook blocks 8 and 10, and it blocks
nothing 1.6.0 allows.

What that costs: the shapes 1.6.0 cannot see stay unseen. A numberless `gh pr
merge`, a variable as the number, `xargs` with the number on stdin, and quoted
words that spell `gh pr merge`. The earlier version caught the first and the
second by walking; they are given up here and filed as #17 with a reproduction
and the false-block numbers a fix has to beat. A numberless merge after `git
switch` is given up with them, since a numberless merge is never detected.

Three additions to 1.6.0's pattern survived, each measured on those 48 commands
for new false blocks, all costing nothing (22 of 48 match either way):
`-R`/`--repo` between `gh` and `pr`; flags between `merge` and the number, with
a value flag's value skipped; and a PR URL in place of the number, with a
backslash-newline read as the space the shell makes of it. A fourth was measured
and refused: matching quote-stripped text closes `"gh" pr merge 24` and newly
blocks `rg "gh pr merge" --max-count 5`, which strips to `rg gh pr merge
--max-count 5` and reads `5` as the PR.

Decided in the same rounds and kept:

- `SKIP_REVIEW_GATE=1` counts only as a real assignment: a prefix on the merge,
  an `env` argument, an earlier `export`, or the hook's own environment. It
  covers the merge it fronts and no other. Before, the text anywhere was enough,
  so a `--body "SKIP_REVIEW_GATE=1"` or a trailing comment switched the gate
  off. An honored override prints one line to stderr, because an override nobody
  sees is an override nobody reconsiders.
- `watch -n5 gh pr merge 24` is judged as a merge, because it is one.
- Every block message offers `export SKIP_REVIEW_GATE=1;` in front of the whole
  command. A prefix on `gh pr merge` cannot help a command that only mentions a
  merge, and those are the commands this hook most often blocks by mistake.

Deliberately not handled, because a text pattern cannot see them: `gh api -X PUT
repos/o/r/pulls/N/merge`; a shell function, shell alias, `gh alias` or gh
extension that wraps the merge; a script file or a subprocess argv list that
runs it; `gh -Rowner/repo pr merge 25`, where the attached spelling stops the
flag skip at the `/` (the walk reads it fine and never gets the chance); and
`env -C <dir> gh pr merge 25`, which moves the directory with no `cd`, so the
merge is found, the redirect is not, and the session's repo is asked without a
word. That last one is this decision's own defect in a shape the hook cannot
see, and 1.6.0 answers it the same way. All of them are #17.

## Review round 3, the same day: BLOCK, two findings

Both were gaps between what the code does and what it says.

The first: `export SKIP_REVIEW_GATE=1;` did not work on the path that blocks a
merge the walk could not tie to a command. The hook printed "review gate
skipped", blocked anyway, and named the workaround that had just been used. A
workaround a message recommends is part of the message, and nothing tested it.
Four commands hit it and every other blocked case already honored the export.

Decided while fixing it: for a merge the hook found and could not read down to a
command, only `export SKIP_REVIEW_GATE=1;` counts, and not a bare
`SKIP_REVIEW_GATE=1` prefix. That covers two paths, the targets for merges the
walk could not tie AND the whole command when its words cannot be walked at all.
The second is easy to miss. `SKIP_REVIEW_GATE=1 gh pr merge 24 --body "it's
fine` has an unbalanced quote, so the words cannot be read. It went through
before, announcing a skipped gate. It blocks now and says nothing about an
override, because on that path the hook cannot tell what the assignment was
attached to.

Stated narrowly, because review round 4 pushed back on the general version of
this reason. A bare prefix binds to one command, and that argument carries
`SKIP_REVIEW_GATE=1 gh pr merge 24 && gh --no-such-flag v pr merge 24`, where
the prefix really does bind to the first command and not the second. It does NOT
carry `SKIP_REVIEW_GATE=1 gh pr merge -X 24 25` or `... 2$n`, which are one
command whose own merge is the untied one, and where the shell really would set
the variable for it. Those block anyway. Two things make that acceptable rather
than merely convenient: blocking is the safe direction on a merge nobody could
read, and no block message ever offers the bare prefix, so nobody is told to
type a form that will not work. The rule is "the spelling the messages give is
the spelling these paths take", and not "a bare prefix never binds".

Decided in the same round: the dedupe key keeps `skip` and `unreadable`. Both
look redundant, because a key of PR, repo, directory and environment already
describes the lookup, and dropping either one passed every case when the dedupe
landed. Each guards a false pass and each now has a case. Drop `skip` and
`SKIP_REVIEW_GATE=1 gh pr merge 24 && gh pr merge 24` collapses the real merge
into the skipped one, so an unreviewed merge runs with the gate never asked.
Drop `unreadable` and `gh pr merge 25 && echo --squash | xargs gh pr merge 25`
collapses the unreadable target into the readable one, which is allowed. The
collapse keeps the first target, and in both shapes the first is the permissive
one.

The second: `docs/HANDOFF.md` still described the design round 2 threw away.
Marked superseded there with what replaced it, per this repo's own handoff rule
that a decision is superseded and never deleted.

Also fixed: one lookup per distinct target. Each target costs up to four `gh`
calls and detection counts every mention, so a doc naming one PR 300 times cost
36.6 seconds. It is 0.25 now. The cost that remains is one lookup per DISTINCT
PR, which is inherent: 1.6.0 checks only the first merge in a command, and this
hook checks each. 300 distinct PRs in one command take 20 seconds, and an
ordinary single merge takes 0.1.

Known false blocks, kept, because the alternative is a shell parser: a command
that only mentions a merge with a number is judged as a merge. A commit message,
a heredoc written to a file, an `echo`. 1.6.0 does the same. The workaround is
in every block message, and `grep 'gh pr [m]erge'` breaks the text instead.

Measured the same day in `hooks/git-safety-guard.sh`, not fixed here (#15): its
`target_dir` reads an unquoted `cd /path` and misses a quoted path, a `~` path
and `pushd`. Run from a feature branch, `cd /repo/on/main && git commit` is
denied, and the same command with the path in quotes or written with `~` is
allowed. It falls back to `$PWD` without saying so, which is the guess this
decision refuses.

## 2026-09-21: warn the model when its context passes the smart zone

Superseded 2026-09-30 by "wind down and hand off when context passes the
smart zone" below. What still holds: the numbers, how the size is
measured, the two events, main thread only. What was replaced: the
warning-only behavior and the rejection of Stop.

Supports `handoff`. Adds `hooks/context-warning.py`.

The owner decided the numbers: the first warning at 120k tokens, then one more
at every 100k past it (220k, 320k). 120k comes from mattpocock's `ask-matt`
skill, which calls it the smart zone, "the window (~120k tokens on
state-of-the-art models) within which the model still reasons sharply", and
says to `/handoff` and continue in a fresh thread when a session nears it. Both
numbers are settings in `.handrail.toml` (`[context_warning] first`, `step`).
The switch is `[rules] context_warning`, so a repo config cannot switch it off.
The thresholds sit outside that ratchet, as they do for every guard: a repo can
set `first` high enough that the warning never fires.

The warning tells the model to wait for the agents it is waiting on before the
handoff pass. A coordinator that hands off with lanes still running loses their
reports.

Event: PostToolBatch and UserPromptSubmit, both through
`hookSpecificOutput.additionalContext`. Quoted from
https://code.claude.com/docs/en/hooks as read on 2026-09-21:

- PostToolBatch "fires exactly once with the full batch", and its
  `additionalContext` is a "Context string injected once before the next model
  call".
- PostToolUse was the first choice and lost: it "fires once per tool, which
  means it fires concurrently when Claude makes parallel tool calls". The
  reviewer measured the race: 3 of 20 parallel trials warned twice.
- For UserPromptSubmit, "Plain stdout and the `additionalContext` value are
  each injected as a system reminder that starts with the hook's name; Claude
  reads both."
- Stop was rejected. It does accept `additionalContext`, but "The conversation
  continues so Claude can act on it". A size warning is no reason to make a
  finished turn keep going. Issue #22 asks about Stop's stderr, and this hook
  does not use it.

Size: the sum of `input_tokens`, `cache_read_input_tokens` and
`cache_creation_input_tokens` on the last main-thread assistant message in the
transcript. The docs say the transcript "may lag the in-memory conversation",
so the number can be one message old. At a 100k granularity that does not
matter. Lines whose fields sum to 0 are skipped. Claude Code writes those,
with model `<synthetic>`, for API errors, usage-limit notices and "No
response requested.", and the reviewer found them in 14 of 286 of the owner's
transcripts. Read as a size, one looked like a `/compact` and the same step
warned twice.

Main thread only. Hooks "also run inside subagents", and there the input
"carries the `agent_id` and `agent_type`". The docs say `transcript_path` is
"the main session's transcript" (on SubagentStop), so a subagent would read the
parent's size, receive the warning meant for the parent, and use up its step.
The hook skips any call with `agent_id`.

Cost: 31 ms median per call over 20 runs on a 10.1 MB transcript (maximum 280
ms, the first run). Only the last 2 MB of the transcript is read, so an
880k-token session costs the same as a small one.

## 2026-09-30: wind down and hand off when context passes the smart zone

Supports `handoff`. Supersedes the warning-only design of 2026-09-21. Renames
the hook from `hooks/context-warning.py` to `hooks/context-handoff.py`, with rule `[rules] context_handoff`,
section `[context_handoff]` and state in `~/.claude/state/context-handoff/`.

The owner's words: "build a global hook where at that percentage, u allow the
agents to finish, if the subagents go for too long, save its outcome and kill
it, either way writes handoff for the next session". The 2026-09-21 hook
printed one sentence and left the rest to the model. A coordinator past 120k
could read it, keep dispatching, and end the session with no handoff.

What it does now, in three parts:

1. Wind-down notice, on PostToolBatch or UserPromptSubmit, at `first` tokens
   and again at each `step` past it. Start no new work. Spawn no new subagents.
   Running subagents may finish, for at most `grace_minutes` (default 15). Set
   one background timer for the deadline. Then write the handoff and tell the
   user to start a fresh session. The time of the notice is recorded.
2. Deadline notice, on the first of those events at or after that time plus
   `grace_minutes`, when no handoff has been written since. For each subagent
   still running: save what it has (its last report, its branch and worktree
   path, any files) into the handoff, stop it with TaskStop, write the handoff
   now. Said once per notice.
3. Stop check. After a notice, with no handoff written since, one Stop is
   blocked with the same instruction.

The unit is tokens. The owner said "percentage" loosely. The source gives a
count, "(~120k tokens on state-of-the-art models)", and says nothing about a
share of the window. 120k is 60% of a 200k window and 12% of a 1M one, so a
percentage would move the line with the model while the source's claim stays
at the same count.

The hook instructs and the model acts. It stops no subagent and blocks no
tool. A hook sees one event's input and cannot know which subagent holds work
worth saving. The model can, and TaskStop is its tool.

The timer is the model's: a Bash `sleep` with `run_in_background`. A finished
background command re-invokes the model. That sentence is in the Bash tool's
own description and was seen to happen while this was built. The tools
reference page does not state it, so it is an observed behavior with no
documented guarantee. Without the timer an idle main thread triggers no hook
and the deadline would pass unseen.

Stop blocks once per notice. Quoted from https://code.claude.com/docs/en/hooks
as read on 2026-09-30:

- The shape is `{"decision": "block", "reason": "..."}`. `decision`: "`"block"`
  prevents Claude from stopping. Omit to allow Claude to stop". `reason`:
  "Required when `decision` is `"block"`. Tells Claude why it should continue".
- "The `stop_hook_active` field is `true` when Claude Code is already
  continuing as a result of a stop hook. Check this value or process the
  transcript to avoid blocking on a condition that will never resolve." The
  hook never blocks when it is true.
- The hook also keeps its own record of the block, so a later turn in the same
  session is not blocked again. A lane's handoff goes in its PR body, which
  this check cannot see, so on a lane the condition never resolves by itself.
  One block asks the question. A second would only repeat it.
- The input's `background_tasks` and `session_crons` arrays "let hooks
  distinguish "session is done" from "session is paused waiting for background
  work to wake it back up"". Inside the grace, a Stop with a non-empty
  `background_tasks` is let through and the block is kept for later. A main
  thread waiting on its subagents has to go idle, and that is what the notice
  asked for. "Both arrays are present when the task registry is reachable", so
  when the array is missing the hook blocks and the reason says to stop again
  if subagents are still inside their grace.
- After the deadline the block carries the deadline instruction, and that
  counts as the deadline notice.

This reverses the 2026-09-21 rejection of Stop. Then the hook had nothing to
require, so keeping a finished turn going bought nothing. Now it requires a
handoff, and a session that ends past the line without one is the failure the
owner asked to prevent.

"Handoff written" is one test, `hooks/handoff_touch.py`, used by this hook and
by `handoff-freshness.py`: a non-merge commit that changes `docs/HANDOFF.md`
since the given time, or an uncommitted change to it, a new untracked file
included (`--untracked-files=all`). `handoff-freshness.py` asks about the last
8 hours in HEAD's history only, as before. This hook asks about the time since
its notice with `all_refs=True` (`git log --all`), so a handoff committed from
another branch or worktree counts. An uncommitted edit carries no time, so one
made before the notice counts too. Both widenings came from review round 2: a
handoff pass committed from another worktree was invisible, and a new `docs/`
showed as `?? docs/`. Round 3 kept `--all` out of `handoff-freshness.py`,
where a handoff pass on an unmerged branch would silence the warning on trunk.

Known limits. The detector cannot see two cases, and in both the deadline
notice and the one Stop block always arrive, even after the handoff exists:

- A lane whose notes are in its PR body. The text says so and asks the model
  to say the notes are there and stop again.
- A plain folder that is no git repo. There is no history to ask. The text
  says the folder is not a git repo and asks the model to say where the
  handoff is and stop again. It names no branch and no PR body, and tells the
  model to ask the user where the handoff lives if that is not clear.

One block per notice bounds the cost. The risk is a model that learns to
answer "done, stop again" by habit.

A missing or broken `hooks/handoff_touch.py` leaves no detector. Then this
hook still gives the wind-down notice, which needs none, and gives no deadline
notice and no Stop block, because both would claim no handoff was written and
the hook cannot tell. The safe side is silence: a false block trains the model
to ignore the true ones. `handoff-freshness.py` exits 0 and checks nothing.
Both import it inside a guard, as they do `handrail_config`, so neither prints
a traceback.

Relied on, observed, and not in the hooks docs:

- The transcript line format. The page gives `transcript_path` only as "Path
  to conversation JSON". The hook reads JSON lines with `type`, `isSidechain`
  and `message.usage` (`input_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens`). Observed in this machine's transcripts under
  `~/.claude/projects/`, read on 2026-09-21 and again on 2026-09-30 with
  Claude Code 2.1.220. A format change makes the hook silent, never wrong
  loudly, because a line it cannot read is skipped.
- PostToolBatch inside a subagent carrying `agent_id`. The page says that for
  "tool events such as `PreToolUse` and `PostToolUse`". Observed on 2026-09-30
  with Claude Code 2.1.220: a headless `claude -p` run with a PostToolBatch
  hook that logged its input, where a subagent ran one Bash command. The log
  held one main-thread event with no `agent_id` and one with `agent_id` and
  `agent_type` "general-purpose".

Rejected:

- A percentage of the window. See the unit above.
- The hook stopping subagents itself, or blocking the Agent tool after the
  notice. Out of scope by the owner's brief: the hook instructs.
- Blocking every Stop until a handoff exists. On a lane that never resolves,
  and the docs' cap would end it anyway: "after stop hooks have continued the
  turn eight times in a row, Claude Code overrides the next block and ends the
  turn".
- Reading the PR body with `gh` to see a lane's notes. It needs the network,
  and `handoff-freshness.py` already refused that for the same reason.
- Stop's `hookSpecificOutput.additionalContext` in place of the block. It
  continues the conversation the same way, and the docs say "no hook error
  notification is shown". The owner should see that a session tried to end
  past the line with no handoff.
- A hook-owned timer through `asyncRewake`, which per the docs "wakes Claude
  immediately even when the session is idle" on exit code 2. Not tried. It
  would put a 15-minute sleeping process behind every notice, and "Claude Code
  still enforces `timeout` on a hook you run with `asyncRewake`", so it needs
  a timeout longer than the grace. Worth a ticket if the model's own timer
  proves unreliable.

Check: `./hooks/context-handoff-selftest.py`.

## 2026-11-04: record broken inputs as test cases

Supports `fresh-eye`, `ship-loop` and `mutation-gate`. The case is EdSim PR
#520, which tags each constant that a Virginia answer would change.

- Its second review round used 101k tokens, and its third used 69k. Recount:
  the `Rounds:` line of the PR body
  (`gh pr view 520 --repo georgetown-mdi/EdSim --json body`).
- Between those rounds, commit 9f29452 added a table of 13 broken inputs and
  one valid input to `tests/dcetep/requirements/test_va_waits_on.py`. Recount:
  `git show 9f29452:tests/dcetep/requirements/test_va_waits_on.py`, then count
  the `_CASES` entries.
- After the third round, commit 41cd8de added three more broken inputs that the
  round found. Recount: `git show 41cd8de`.

Two rounds do not prove the cases caused the drop in tokens. The owner asked
for the rule in conversation on 2026-11-04. That request has no public record.

Considered and rejected: put every mutation into the `mutation-gate` data file.
The gate breaks a script's code and needs its runner. A bad input to a check
that takes an argument is cheaper as an ordinary test beside the check.

## 2026-11-10: one GitHub issue per open lane holds its next task

Supports `handoff`. The case is EdSim on 2026-11-10. Two lanes were open: a
wage fix, run by a live session, and drafts of redesign tickets. A new session
read the Start here block of `docs/HANDOFF.md`, which sent it to the last
section. That section named the wage fix, so the new session took a lane
that was already taken. The drafts' next step was only in the Handoff notes
of a merged PR, and no handoff pass had folded it in. One file gave every
session the same first task.

The owner decided the fix. Each open lane has one issue with label `lane`,
and its body holds the lane's `## Next`. A session claims a lane with the
body line `Held by: <session name>, since <YYYY-MM-DDTHH:MMZ>` and lets it
go with `Held by: nobody`. Issue edits cost no CI minutes unless a
workflow runs `on: issues`, and every machine and cloud routine can read
them. `docs/HANDOFF.md` stays
the shared log of decisions, traps and judgment.

The handoff pass reviewer now checks four things: each next step in merged
Handoff notes has a `lane` issue, no two lane issues name the same first
task, each closed lane issue cites a PR whose notes say
`Lane: #<N>. finished`, and a lane whose `updatedAt` and `Held by:` time
are both over 7 days old goes to the owner.

A claim holds for 24 hours, or while ListAgents shows its session live.
The 24 hours keep a claim held for its first day even when ListAgents does
not list its session. Corrected 2026-11-10 (review round 7): this line
also said ListAgents sees one machine and one harness only. No source
confirmed it, so the claim is dropped.

The holder is one `Held by:` line in the issue body. To claim, a session
reads the body, writes its line if the lane is free, waits 30 seconds, and
reads again. The line names it: it holds the lane. Otherwise it changes
nothing and picks again. A loser must not write `Held by: nobody`, because
that would free the winner's lane. Superseded 2026-11-10 by the entry "the
lane claim moves into a script": `scripts/lane_claim.py claim` does the
read, the write, the wait and the second read in one process.

Every write to a lane body reads the body just before it and keeps the
`Held by:` line as read, unless the write is a claim, a refresh or a
release. An edit replaces the whole body, so a `## Next` update built from
an old read erased a claim made since (review round 4). The limit that is
left: two writes inside the same few seconds still lose one, because
GitHub offers no compare-and-set on an issue body. The 30-second wait and
the read before the first push catch most of these, and a holder that
finds its line gone stops and tells the owner. Superseded 2026-11-10 by
the entry "the lane claim cut to four rules": the exceptions for a claim,
a refresh and a release, and the read before the first push, are gone.
Every write after a claim follows the one stop rule, and since the entry
"the lane claim moves into a script", every write runs through
`scripts/lane_claim.py`.

The holder line is the first line of the issue body. With a trailing CR
stripped, it must match
`^Held by: (nobody|.+, since \d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)$`. Any other
first line is malformed and counts as free: no line, an empty body,
`Held by: nobody, since ...`, seconds in the time, or a time in the future.
This superseded "the first `Held by:` line above `## Next`, outside a code
fence" on 2026-11-10 (review round 5). That parser broke on nested fences
and on a fenced `## Next`, and nobody could check it by eye. Anyone can read
a first line.

A body with no `Held by:` line, or a malformed one, counts as free.
The choice keeps a lane opened by hand, without the line, from being
locked forever. The risk: a holder whose line was deleted or mangled looks
free, and another session can take its lane. The read before the first
push is where the first holder finds out. Superseded 2026-11-10: there is
no first-push read now. The holder finds out when `lane_claim.py write` or
`release` refuses.

Free lanes sort by issue number, oldest first, and held lanes follow by
their time. Before that, every free lane tied in the sort, so a routine
with no owner always took the newest lane (review round 4).

Superseded 2026-11-10 on this change, before the body line was chosen:
- First rule: claim and release comments, where the first claim since the
  last release won. Review round 2 found it locked a lane forever behind an
  expired claim, and it named a different holder than the list did.
- Second rule: the latest claim or release comment held the lane. Review
  round 3 found two faults. The comment read stops at 100 comments, so a
  long lane loses its holder. And a late claim from a session that listed
  before the holder's claim took a working session's lane. Three review
  rounds passed without the blocking count falling (2, 3, 3), so the owner
  chose the body line. One line has one value, so every reader sees the
  same holder.

Later on 2026-11-10, three more changes superseded parts of this entry:
the first-line parser (review round 5, above), the four rules (next entry)
and the claim script (the entry after it).

The handoff pass closes a lane issue only when a merged PR's notes have the
exact line `Lane: #<N>. finished`, with nothing after it. Notes with no lane
line or no next step go to the owner, because a guess there would close an
open lane.

What `handoff-freshness.py` checks, offline, in the section from the
`## Start here` line to the next `## ` heading: a line that starts with
`gh issue list --label lane` (a backtick in front is allowed, and the label
must end there), at line 40 of the file or earlier. It also warns when a
numbered step in that section starts with "Read the LAST section". It does
not check what the command prints or whether the label exists.

Considered and rejected: a `gh` call in the hook to compare the issues with
the notes. A Stop hook must work offline, so the reviewer of each handoff
pass checks the issues against the notes.

Check: `./hooks/handoff-freshness-selftest.py`.

## 2026-11-10: the lane claim cut to four rules

Supports `handoff`. Six review rounds on the lane claim found 2, 3, 3, 2,
1, then 3 blocking findings. The count rose again, and each new branch of
the protocol was a new gap: a separate first-push check, a separate "names
another session" case, a release only "if it still names you", and a
parser that scanned past `## Next`. So the claim is cut to four rules,
inside the owner's decision of one `Held by:` first line per lane issue:

1. Line one of the body, with a trailing CR stripped, decides. It is free
   when it matches `^Held by: nobody$`. It is a holder line when it matches
   `^Held by: (?<name>.+), since (?<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)$`,
   with a name other than `nobody` and a time not in the future. Anything
   else is malformed and free. A holder line holds for 24 hours, or while
   ListAgents shows its session live.
2. To claim, replace line one if it starts with `Held by:`, else insert a
   new line one. Wait 30 seconds and read again.
3. One stop rule for every later write: "Before every write to a lane
   body, read it again, and if line one is not your own holder line,
   change nothing, stop, and tell the owner. Otherwise write, keeping line
   one as read, with a new time when you update `## Next`, or as
   `Held by: nobody` when you stop."
4. Session names are unique per run.

This supersedes the rules of review rounds 4 to 6 in the entry above: read
just before every write with its own exceptions, the first-push check, and
the release condition. The skill rules, the Start here block, the STALE
warning in `handoff-freshness.py` and the wind-down notice in
`context-handoff.py` carry the stop rule word for word, and the self-tests
fail if any one loses it. The handoff pass writes a lane body only as its
holder, so it follows the same rule.

Superseded 2026-11-10 by the next entry, for rules 2 and 3: the claim and
every later write run in `scripts/lane_claim.py`, and the stop rule now
reads "Write a lane body only with `scripts/lane_claim.py write` or `release`, and if it refuses, change nothing, stop, and tell the owner." Rules 1 and 4 stand.

Check: `./hooks/handoff-freshness-selftest.py` and
`./hooks/context-handoff-selftest.py`.

## 2026-11-10: the lane claim moves into a script

Supports `handoff`. Review round 7 found two blocking faults in the claim
as prose. First: the claim read the body in one tool call and wrote it in
a later one, and nothing bounded the gap. A session that read a free lane
at minute 0 and wrote at minute 45 overwrote a claim made at minute 8, and
both sessions then held the lane. Second: the claim said "wait 30
seconds", and Claude Code refuses a standalone `sleep 30` in a Bash call,
so an agent could not follow it. Rounds 5 to 7 found 1, 3, then 2
blocking faults. Each round of prose moved the gap, so the owner moved the
protocol into code.

`skills/handoff/lane_claim.py` is one stdlib Python script that calls
`gh`. A repo copies it to `scripts/lane_claim.py`, as `mutation-gate` does
with its runner, and this repo links that path to the canonical file.

- `claim <issue> <name>` reads the body. A holder line for another name
  under 24 hours old: it refuses and names the holder. Over 24 hours old:
  it refuses unless `--holder-not-live` is passed, which the agent does
  only after ListAgents shows the holder is not live. Else it writes this
  name with the current UTC minute as line one, waits 30 seconds
  (`LANE_CLAIM_WAIT_SECONDS` sets it for the self-test), reads again, and
  exits 0 only if line one is this name's holder line.
- `write <issue> <name> <file>` and `release <issue> <name>` change
  nothing and print the stop rule when line one is not this name's holder
  line. `write` replaces the body after line one with the file and puts a
  new time on line one. `release` sets line one to `Held by: nobody`.

Rule 1 of the entry above, the holder line and its malformed-is-free
cases, is unchanged. The stop rule is one sentence, word for word in the
skill rules, the Start here block, the STALE warning, the wind-down notice
and the script:

Write a lane body only with `scripts/lane_claim.py write` or `release`,
and if it refuses, change nothing, stop, and tell the owner.

Two claims inside the same second can both write, because GitHub offers
no compare-and-set on an issue body. The read after the wait catches that,
since only one line can be line one.

Corrected 2026-11-10 (review round 8): this entry first said the
same-second case was all that remained. Round 8 measured another: an edit
slower than the wait. A 3-second edit and a 2-second wait gave two
holders, because one session's edit landed after the other's second read.
Every `gh` call now times out at two thirds of the wait, and a timeout
exits 2 like any `gh` failure, so a claim whose edit is that slow ends
without reporting a hold. What remains: an edit the client gave up on can
still land on GitHub after the timeout. That case is left for a ticket.
Superseded 2026-11-10 (review round 9): the span that matters runs from the
read being served to the edit landing, so two calls each under two thirds
of the wait could together pass it. The reviewer got two holders with a
3-second wait, a 1.6-second read and a 1.6-second edit. Now the read and
the edit share one budget of half the wait, from the start of the read to
the end of the edit. Each `gh` call gets what is left as its timeout, and
a run past the budget exits 2 without writing. Another session's read and
edit then both fit inside one wait. The self-test checks the budget is at
most half the default wait, and that a read and an edit that each fit the
budget, but not together, write nothing. What remains is #50: an edit that
`gh` gave up on can still land on GitHub after the timeout. It is accepted
and ticketed.

Round 8 also found that the Start here block sent every non-zero exit back
to step 4. With no `scripts/lane_claim.py`, or with `gh` failing, a session
then walked every lane. Step 5 now reads exit 1 as "pick again" and any
other exit as "stop and tell the owner". `handoff-freshness.py` warns,
offline, when the block runs `scripts/lane_claim.py` and the repo has no
such file, and prints the copy command.

Round 9 found that the script still exited 1 on errors it did not expect,
e.g. no `gh` on PATH, so step 5 read them as refusals. The script now exits
1 only on a refusal, and one handler turns any other error into exit 2.
The self-test covers no `gh` on PATH, a `gh`
that exits non-zero or times out, and `gh` output that is not JSON or has
no `body`: each exits 2. The STALE warning carries the exit rule word for
word. The missing-script warning now checks the repo top and prints the
copy command with the repo-top path, and a copy that git does not track
warns too.

Check: `./hooks/lane-claim-selftest.py`, `./hooks/handoff-freshness-selftest.py`
and `./hooks/context-handoff-selftest.py`.
