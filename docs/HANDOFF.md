# Handoff

What this repo is: Yiming's engineering workflow packaged as a Claude Code
plugin. Seven skills, five guard hooks. See `README.md` for what each does and
`docs/DECISIONS.md` for the dated measurements behind them.

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

**The no-attribution hook blocks writing about itself in a Bash command.** That
is the enforcement working. Use the file-edit tools for that text.

## Deliberately not done

- **Indented (4-space) code blocks are not stripped.** Quoting a diff that way
  can block a turn. Assistant output almost always uses fences.
- **The repo is private.** Both install commands resolve only for an account
  with read access. Going public needs a scrub pass first: the skills reference
  "your CLAUDE.md" and the hooks encode one person's rules.
- ~~**No CI.**~~ Superseded 2026-09-04: the four self-tests and
  `tools/check-repo.py` now run on every pull request and on push to `main`.
  The reason to move them was that a hook protects one laptop while a status
  check protects the repo. Deliberately one job, running the exact command
  above, because CI that runs something else is a second undocumented policy.
- **The status check enforces nothing yet.** Branch protection and rulesets both
  return 403 on a personal private repo with no paid plan, so a red check does
  not block a merge. Making the repo public is what turns the check into a gate.
- **Skipped: pre-commit and a PR template.** pre-commit is bypassable and this
  repo's own `harden` skill says never to treat it as the enforcement
  mechanism. A PR template would check nothing CI does not.
