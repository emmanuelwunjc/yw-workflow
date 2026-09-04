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
A reviewer caught that the first version left them an island, which quietly made
the README's "loading any of them reaches the rest" false. The Hands-off graph
is now strongly connected and `tools/check-repo.py` would be the place to assert
that if it breaks again.

**2026-09-04 · Both eli5 descriptions trigger on "eli5", and that is handled in
prose rather than by disabling model invocation.**
`eli5-text` matches "eli5 this", a superset of `eli5`'s "eli5", so the more
specific phrase would have won by default and silently changed what a bare
"eli5 X" produces. Each description now names when to prefer the other, and
`eli5-text` says explicitly that it takes ambiguous cases, since text costs a
reader nothing to skim and a page nobody opens costs more. Rejected:
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
- **The status check enforces nothing yet.** Branch protection and rulesets both
  return 403 on a personal private repo with no paid plan, so a red check does
  not block a merge. Going public unlocks the branch-protection API on a free plan, which is what
  makes enabling the gate possible. Enabling it is still a separate step.
- **Skipped: pre-commit and a PR template.** pre-commit is bypassable and this
  repo's own `harden` skill says never to treat it as the enforcement
  mechanism. A PR template would check nothing CI does not.
