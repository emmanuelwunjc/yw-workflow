# Handoff

What this repo is: Yiming's engineering workflow packaged as a Claude Code
plugin. See `README.md` for what each skill and hook does, and
`docs/DECISIONS.md` for the dated measurements behind them. The counts live in
the README and are checked against the skills on every run, so they are not
repeated here.

State you can derive, so it is not written here:

```bash
git log --oneline main..HEAD          # what is unmerged
(for t in ./hooks/*-selftest.*; do "$t" || exit 1; done)  # do the guards work
claude plugin validate .              # whether it installs
npx skills add . -l                   # what the skills path would serve
```

## Why this exists at all

The skills and hooks lived loose in `~/.claude` on one laptop. They existed
only on that machine, had no history, and could not be handed to anyone. A
plugin repo fixes all three.

## Decisions, newest first

**2026-09-04 · eli5 and eli5-text are two skills, not one with a flag.**
The output shapes barely overlap: `eli5` is per-panel around an SVG, and the
text version wants a one-sentence opener, 3 to 6 labelled steps, and a closing
line. A flag would have meant one skill carrying two structures and a branch,
and the model choosing the branch from the same ambiguous request either way.
Two skills put that choice in the router, where a description can carry a
tie-break, rather than in the body.
Neither joins the ship chain, because they explain a thing rather than ship one.
They are still reachable from it: `grill` and `need-me` link to `eli5-text` when
a decision is blocked on understanding, and `ship-loop` and `harden` link to
`eli5` when a change needs explaining to someone who will not read the diff.
The `grill` edge is here because a reviewer found the handoff claiming it before
it existed, which is the failure this file is meant to prevent rather than
commit.
A reviewer caught that the first version left them an island, which quietly made
the README's "loading any of them reaches the rest" false. The Hands-off graph
is now strongly connected and `tools/check-repo.py` would be the place to assert
that if it breaks again.

**2026-09-04 · Both eli5 descriptions trigger on "eli5", and that is handled in
prose rather than by disabling model invocation.**
`eli5-text` matches "eli5 this", a superset of `eli5`'s "eli5", so the more
specific phrase would have won by default and silently changed what a bare
"eli5 X" produces. Each description now names when to prefer the other, and
`eli5-text` says in its DESCRIPTION that it takes ambiguous cases, since text
costs a reader nothing to skim and a page nobody opens costs more. The first
version put that sentence in the body, where the router never sees it: a body
loads only after the skill has already been chosen. Rejected:
`disable-model-invocation: true` on `eli5-text`, which is what `wayfinder` uses
for a name collision. Held in reserve if the prose tie-break turns out to fail
in practice.

**2026-09-04 · A required status check binds nobody until enforce_admins is on.**
Branch protection was enabled with `enforce_admins: false`, the GitHub default.
A deliberate probe commit pushed straight to `main` and was accepted, with the
remote printing "Bypassed rule violations". So the gate bound everyone except
the repo owner, who is the only person who commits here. It was decoration, and
it took a push to find out, because the API reports protection as configured
either way. Any repo hardened by `harden` needs the same probe: push something
to the protected branch and confirm it is rejected. Configured is not enforced.

**Probe with your real git identity, never a throwaway.** The first probe used
`t <t@t.com>` so it would look disposable. Protection accepted it, GitHub
resolved that address to a real user who happens to have it registered, and a
stranger appeared in the contributor list of a public repo, credited with a
commit they never wrote. A probe you expect to be rejected can be accepted;
that is the entire reason for running it.

**2026-09-04 · Rewriting history is not enough on GitHub; pull refs survive.**
A worked example in `need-me` named a real individual and asserted no public
record of them existed. `git filter-repo` cleaned every commit and a force-push
updated `main`, and the name was still fetchable from `refs/pull/1/head`,
which a force-push does not touch and which anyone can fetch on a public repo.
Two of the commit messages describing the fix also signposted where to look.
Resolved by renaming the old repo (it keeps those refs, and stays private) and
pushing the clean history to a fresh one. Verified from a scratch clone: zero
pull refs, zero hits. The old repo is `yw-workflow-archive-preScrub`, private,
and can be deleted once `gh auth refresh -h github.com -s delete_repo` is run.
The lesson: on GitHub, scrubbing anything from history means abandoning the
remote, not rewriting it. Learned twice on the same day, the second time for a
misattributed commit, because rewriting `main` cleared the branch and left the
pull refs feeding the contributor list. Cheap while a repo is hours old with no
stars or forks. Expensive later, which is the reason to get identity and
content right before the first push rather than after.

**2026-09-04 · Credit Matt Pocock explicitly, and reproduce his notice.**
`grill` and `wayfinder` are derivative works of skills in
github.com/mattpocock/skills (MIT). `wayfinder` follows his design section for
section: the map as an index, the four ticket types, claim-by-assign, the fog
of war and its state-it-now test, the out-of-scope section that never
graduates, both invocation modes. A reviewer read the two files line by line
and called it a rewrite of a whole design, which is the honest description.
The frontmatter key started as `inspired-by:` and was changed to
`adapted-from:`, because the key is what a tool reads and it was saying
something weaker than the prose beneath it. A link plus the token "(MIT)" is
not the notice MIT asks for, so `NOTICE` reproduces his copyright and
permission paragraphs verbatim. That matters more if this repo ever goes
public, and costs nothing now.
Checked and found clean: no other skill here derives from his work.
`git-lanes` against his `git-guardrails` (his blocks commands, this isolates
worktrees), `fresh-eye` against his `code-review` (his is standards-vs-spec,
this is adversarial), `harden` against his `setup-pre-commit` (his is Husky,
this is CI and branch protection), `need-me` against his `handoff` (his
compacts a conversation, this queues blocked decisions).

**2026-09-04 · Names questioned and kept: git-lanes, ship-loop, harden.**
Rejected `multi-task` (multitasking is sequential and needs no worktree, and it
overlaps ship-loop's territory), `loop-it` (a built-in `/loop` already exists
and ship-loop calls it, and Matt has a `loop-me` meaning a third thing), and
`set-infra` (infra reads as deployment, which harden never touches). The real
complaint was that the names are jargon. That is answered by the one-line
opener each skill now carries, rather than by renaming. `harden` itself was a
rename, from `bootstrap-repo-hygiene`, on the different ground that the old
name was 35 characters at the prompt.

**2026-09-04 · The negation guard stays partial, deliberately.**
`~/CLAUDE.md` said the no-negation rule was "Enforced by claude-md-guard.py".
It was not: the hook checked em-dashes and question format only. Building the
missing check took four attempts. Versions one and two blocked roughly half of
ordinary engineering prose, measured twice at 49% on fresh sentences. The
version that shipped requires the *substitution* to be present, so a plain
negative ("Not yet.", "the build is not green") never trips.

Its accuracy was measured two ways and the two disagree, so both are recorded.
Across the `SKILL.md` and `README.md` files under
`~/.claude/plugins/marketplaces`, `~/.claude/skills` and `~/code/*/` the trip
rate is well under 1%, and nearly every trip is a genuine violation in
someone's prose. Re-measure with that corpus named, because the rate moves a
lot with which files you include. Against sentences
a reviewer wrote deliberately to probe it, roughly half the trips are wrong.
Those are different populations, and a conversational turn sits between them.
The honest summary: it catches some real instances, it wrongly blocks
occasionally, and both directions are enumerated in
`hooks/claude-md-guard-selftest.py` as `KNOWN_MISSES` and
`KNOWN_FALSE_POSITIVES`, so nobody later assumes it is complete.
Rejected: widening it to catch most cases, because a wrong block costs a
rewrite and the interruption is worse than the miss. Rejected: deleting it,
because it caught four real violations in this repo's own text that six
reviewers read past.

**2026-09-04 · Each rule gets its own block budget.**
One shared counter meant a wrong negation block spent the em-dash rule's slots,
so a heuristic could switch off a literal character match for the rest of a
session. That coupling is what made an imprecise guard worse than none, and it mattered
more than the false-positive rate on its own. Separate budgets remove it, and
they are why the partial guard is safe to keep. The ceiling that buys is worth
knowing: three budgets of two means up to six blocked turns per session where
one shared budget capped it at two.

**2026-09-04 · Dated measurements live in `docs/DECISIONS.md`, never in a skill.**
`git-lanes` had grown a venv benchmark and a `worktrunk` evaluation inside it.
Findings age and procedures do not, so a finding sitting in a skill quietly
ages the whole file.

**2026-09-04 · `bootstrap-repo-hygiene` renamed to `harden`.**
Plugin skills are namespaced, and `/yw-workflow:bootstrap-repo-hygiene` is 35
characters at the prompt.

**2026-09-04 · Both install paths documented, neither made the default.**
`npx skills add` is what most skill repos use and is shorter. The plugin
marketplace path is the only one that carries the hooks. Installing both leaves
duplicates under different names, because plugin skills are namespaced and
skills-CLI ones are not.

## Traps that cost real time

**A plugin version that does not change is not installable.** Editing the repo
does nothing until `.claude-plugin/plugin.json` bumps, because
`claude plugin update` keys off the version. This bit hard once: the personal
skill copies had already been moved to backups while the cache still held the
pre-fix snapshot, so two skills existed nowhere and the git guard ran ungated
on every command.

**Both install paths read the default branch.** Work on a feature branch is
invisible to `npx skills add` and to the marketplace, however green it is.

**A test fitted to the fix proves nothing.** Twice, cases were added to prove a
detector was fixed, and every case exercised the branch that had just been
deleted, leaving the surviving branch untested. The reviewer caught it both
times by writing fresh sentences instead. Any new guard here needs its
must-stay-quiet list written by someone who did not write the guard.

**Code-stripping failed four separate ways, one per review round.** An
unterminated fence swallowed the document. A stray backtick paired with the
next one anywhere later. A `~~~` line closed a ` ``` ` block. A blockquoted
fence was never recognised at all, and the fix for that one closed ordinary
fences early, turning a fail-open bug into a fail-closed one. A guard that
fails open with no signal looks exactly like a guard that found nothing, and a
guard that fails closed blocks a turn over source that cannot be rewritten.
`FENCE_CASES` in the self-test keeps one case per direction.

**A regex cannot see grammar, and every attempt to make it look like it can
has cost a review round.** Six rounds went into one detector. Each fix revealed
a class the previous patterns could not distinguish: bare negatives, lexical
verbs, imperatives, subordinate clauses, independent clauses after "but". Adding
a seventh pattern is almost always the wrong move; recording the gap is the
right one.

**A backup is only as good as its date.** `~/.claude/skills/eli5` was deleted
when the skill moved into the plugin, on the strength of a backup at
`~/.claude/backups/skills-pre-plugin/eli5` that was thirteen days old. The
frontmatter matched, so nothing was lost, but that was luck. Re-take a backup at
the moment of deletion rather than trusting one that already exists.

**`marketplace.json`'s description must keep its skill list between a colon and
`, plus`.** `tools/check-repo.py` parses that list to check the blurb names every
skill and no skill that does not exist. A word heuristic was tried first and was
green on an invented name, because nothing distinguishes a skill name from an
English one. The parse is stricter and the trade is deliberate: a reworded blurb
fails loudly with a message naming the shape to restore, which is the right
direction for a manifest. Reword freely, keep the punctuation.

**`check-repo.py` is at its ceiling, not at the start of a pattern.** It is roughly
twice the size of the README it guards. Every check traces to a defect that
actually shipped, and a reviewer judged that worth the friction, with the
`## Skills` and `## Hooks` headings now load-bearing. Adding more of this shape
needs a defect to point at, not a gap to fill.

**The no-attribution hook blocks writing about itself in a Bash command.** That
is the enforcement working. Use the file-edit tools for that text.

## Deliberately not done

- **Indented (4-space) code blocks are not stripped.** Quoting a diff that way
  can block a turn. Assistant output almost always uses fences.
- ~~**The repo is private.**~~ Superseded 2026-09-04: scrubbed and published.
  What the scrub covered: two internal names nobody outside could resolve, six
  citations of named sections in a personal CLAUDE.md that a public installer
  does not have, and a worked example in `need-me` that named a real
  individual and asserted no public record of them existed. That last one was
  the only thing here genuinely unpublishable, and no reviewer had been asked
  about it until the round that made publishing imminent.
  What it did NOT cover, on the record: `EdSim` and a project codename remain
  in git history at the first commit, removed only later. Publishing the repo
  publishes the history, and only a rewrite would reach them. Judged low risk,
  since they are project names rather than secrets.
- ~~**No CI.**~~ Superseded 2026-09-04: the four self-tests and
  `tools/check-repo.py` now run on every pull request and on push to `main`.
  The reason to move them was that a hook protects one laptop while a status
  check protects the repo. Deliberately one job, running the exact command
  above, because CI that runs something else is a second undocumented policy.
- ~~**The status check enforces nothing yet.**~~ Superseded 2026-09-04: the repo
  is public, protection is on with `enforce_admins: true`, and force-pushes and
  deletions are blocked. A red check blocks the merge for the owner too,
  verified by pushing to `main` and being refused.
- **Skipped: pre-commit and a PR template.** pre-commit is bypassable and this
  repo's own `harden` skill says never to treat it as the enforcement
  mechanism. A PR template would check nothing CI does not.

## 2026-09-08: the guards run as a CI action

Why now: a review of Tencent's `teamai-cli` (a tool for distributing skills,
rules, and hooks across a team) turned up three ways local delivery of these
guards silently does nothing. Its resource handlers cover skills, rules, docs,
agents, env, hooks, and MCP, with no handler for executables, so a `hooks.yaml`
entry pointing at `claude-md-guard.py` lands in a teammate's `settings.json`
and fails with file-not-found. A PreToolUse hook that exits 127 is a
non-blocking error, so the tool call proceeds and the config still looks right.
The other two: `teamai install` is what carries a plugin, and `teamai pull`
only prints a hint about it, so package sync is a prompt someone can ignore;
and `TEAMAI_HOOKS_DISABLED=1` resolves team hooks to an empty set, which makes
the next reconcile delete the guards from `settings.json` rather than merely
skip installing them.

**Decisions.**

- **CI mode is a subcommand on each existing guard, never a second script.**
  `claude-md-guard.py scan FILE...`, `no-ai-attribution.py scan FILE...`,
  `require-code-review.py check-pr N`. The detection logic is shared, so the
  server-side rule cannot drift from the one the hook enforces. A separate CI
  linter would have been two policies with one name.
- **CI fails closed, hooks fail open, and both are tested.** A crashing guard
  exits 0 in hook mode, because it must never wedge a live session. In scan
  mode it re-raises. `require-code-review` treats an empty `gh` lookup as
  "unknown": the hook lets that through so a network blip cannot block a local
  merge, and `check-pr` fails on it. `hooks/scan-modes-selftest.py` asserts
  both directions, and every claimed guarantee was mutation-tested: deleting the
  re-raise, making `scan` always return 0, counting an unreadable path as clean,
  returning 0 for an `unknown` verdict, and discarding the review verdict
  entirely each turn the suite red.
- **`check-pr` runs the review gate only, never the all-checks-green gate.** In
  CI this check is one of those checks, so gate 1 would always find itself in
  progress and fail every run.
- **Attribution scanning covers the PR body and changed prose, never every
  changed file.** This repo's own `no-ai-attribution.py` and its self-test
  contain the banned strings by necessity. Scanning all files reports the rule's
  own implementation as a violation, which is how a gate teaches people to
  disable it.
- **Considered and rejected: line numbers in scan output.** `find_negation`
  matches text with emphasis markers stripped, so a hit does not map back to a
  raw file offset without re-deriving the position. The quote is greppable.
  Revisit if GitHub annotations are ever wanted.

**Trap.** `run:` in a composite action cannot start with a quoted scalar
(`run: "$X/script.py" check-pr "$PR"` is a YAML parse error, not a shell
error). Use a block scalar. Costs a round trip through a failed workflow to
diagnose if the YAML is not validated locally first.

**Still open.** The action is untested against a real PR run. Its first
exercise is the PR that adds it, which is the only honest way to test it.

**Review round 1 (2026-09-08), and what it caught.** Two blocking findings, both
in the same shape: a guarantee the prose asserted and nothing tested.

- **An unrecognised `rules` value made the whole gate a green no-op.** Each step
  is gated on `contains(inputs.rules, '<name>')`, a substring match on
  unvalidated input. `rules: all`, an empty string, or one typo skipped every
  step, and a job whose steps all skip concludes SUCCESS. Branch protection
  would show a green required check that ran nothing. Superseded by round 2
  below: the first fix was a validate step, and the input is now gone instead.
- **`check-pr` had no test, only `review_status` did.** The reviewer mutated
  `check-pr` to return 0 for the `unknown` verdict, and then to discard the
  verdict entirely, and the suite stayed green at 22 cases both times. Testing
  the helper and shipping the wrapper is the gap. Six cases now cover
  `check_pr` itself, and both mutations were re-run and now fail the suite.

  The lesson generalises past this PR: coverage of the pure function underneath
  is not coverage of the entry point the world actually calls.

**Considered and rejected: filtering the review verdict by author.** The gate is
satisfied by any PR comment matching the verdict pattern, including one the
author wrote. Filtering it would make the gate unsatisfiable for a solo
maintainer, and it is how this repo's own flow opens the gate. The README now
says so plainly rather than implying a second pair of eyes is enforced. Use
branch protection for that.

**Dropped: the `paths` input.** One caller, one value, no test. Config for a
value that never changes, and the same shape as the `rules` input that produced
the blocking finding above. The suffix list is literal now.

**Rejected trigger: `pull_request_target`.** The first version accepted it. It
hands a privileged token to a workflow whose checkout is usually the PR head,
and these steps execute `hooks/*.py` out of that checkout, so on a fork PR that
is the author's code running with write scope.

**Review round 2 (2026-09-08): the fix for round 1 was the defect.** This is why
the fix gets reviewed and not only the original change.

- **The validate step glob-expanded its own input.** It iterated `$RULES`
  unquoted, and `set -euo pipefail` does not disable pathname expansion. In a
  checkout containing a file named `claude-md`, an input of `[cn]*` passed
  validation while `contains(inputs.rules, 'claude-md')` saw the raw string and
  was false, so every step skipped and the job reported success. The round 1
  hole, reopened by the guard written to close it.
- **Nothing tested the validate step.** No selftest, no lint, not even a YAML
  parse in `tools/check-repo.py`. It was the only new branching logic in the
  change and it shipped with zero covering check, which is round 1's finding one
  level up.

**Decision: the `rules` input is deleted rather than fixed.** All three rules
always run. One caller, never exercised with a non-default value, and two
blocking findings and one confusing-error nit all lived in it. A consumer who
wants a single rule calls that guard's entry point in a step of their own, which
is what the README now says. This is the second input deleted from this action
for the same reason; the first was `paths`.

**Trap, and it cost a round.** A `str.replace` fix that does not match silently
does nothing. Round 1 "fixed" the README's `@v1.3.0` pin to `@main` by
substituting a string with the wrong indentation, so the pin survived and round
2 found it again, pointing at a tag that does not exist. Check that an edit
landed before reporting it as done.

**Considered and rejected: matching GitHub's case-insensitive `contains()` in
the shell.** Moot now that the input is gone.
