# Decisions

Measured findings behind the skills. These carry a date because they age:
re-measure before trusting one that is old. The skills stay procedure, so a
moving tool version does not rot them.

A decision is superseded, never deleted. Mark it with the date and what
replaced it.

## 2026-09-21: owner's calls before the build, sources before sentences, fix-only middle rounds

Supports `ship-loop` and `fresh-eye`. The owner read one day of review-loop
data from one repo (edsim_funder_impact): 25 review rounds over 9 PRs on
09/21/2026 (7 merged: #74, #76, #89, #92, #94, #95, #98; #71 and #100 still
open, and #71 began on 09/18/2026). That is about 2.8 rounds per PR. In
that session's Agent tool reports, the review agents' `subagent_tokens` ranged
from 78,776 to 155,942 per review round. The one fix-only round run on the
smaller model (PR #100, round 3) used 110,568, inside the same range, so the
fix-only saving did not show on its first use. The extra rounds had four
causes:

1. Guards that could not fail.
2. A fix that made a new defect, most often in copy checked against sources.
   One PR's blocking counts ran 6, 1, 0, 1, 0.
3. A call only the owner could make, arriving after the build. Four PRs lost
   five rounds this way: a logo, a layout band twice, who owes a report, a
   chart axis.
4. Guards for work not built yet. One PR.

The owner chose three changes. Ask the owner's calls before building UI or
copy. Write each claim's source line before its sentence. Review the fix only
in the rounds after round 1, with every round's verdict and blocking count on a
`Rounds:` line in the PR body. Keeping the reviewer's breaks as a script was
considered and not chosen.

The owner then decided (09/21/2026) that the final full round runs only after
two or more fix rounds. One fix whose fix-only round comes back clean ends the
loop.

Correction, same day: the first version of this entry said 25 rounds over 9
merged PRs, and gave a rounded token figure with no source. Both came from the
coordinating session's summary, and that summary was wrong about the merges.
The counts above replace it.

Recount once PR bodies carry the line: the command in `ship-loop` step 6.

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

Supports `git-lanes` and `harden`. Take `wt switch` and `wt remove`. Refuse
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
