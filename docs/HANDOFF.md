# Handoff

## Start here

You are a fresh session. This file and the repo's open tickets are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Run the repo's free work check, the command its `CLAUDE.md` names. It
   prints the tickets that may start now, first one first. The repo names
   no free work check: read `## Next` in this file for the tasks, and go
   to step 4.
3. Take tickets. The owner named one: take it. If the check does not print
   it, tell the owner why, and stop. Else take the first two to four the
   check prints. It prints none: tell the owner, and stop. Take each
   ticket with a branch linked to it, in its own worktree (`git-worktrees`):
   `gh issue develop <N> --name <type>/<N>-<short> --base <trunk> --checkout --worktree .worktrees/<NN>-<short>`
   The linked branch marks the ticket taken. If gh refuses, change
   nothing, stop, and tell the owner. Then run `gh issue develop --list <N>`.
   It lists a branch other than yours: another session took the ticket at
   the same time. Delete your branch on GitHub and your worktree, and take
   the next ticket.
4. Read `## Now` in this file. Run the recount commands before trusting
   any number. Start more tickets as earlier ones merge. Ask the owner
   nothing that this file or the tickets answer.

A ticket's state lives on GitHub, never in this file. A "blocked by" link
holds it back. The label `needs-owner` or `wayfinder:grilling` makes it
wait. A linked branch marks it taken. When you stop with a ticket not
finished, push its branch and comment on the ticket where the work stopped.
Delete the branch only when it holds no work: that frees the ticket.
Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.

## Now

This repo is Yiming's engineering workflow, packaged as a Claude Code
plugin. `README.md` says what each skill and hook does, and `docs/HOOKS.md`
holds the full hook rules. The counts live in the README, and
`tools/check-repo.py` checks them against the skills on every run.

The gate is these commands. CI (`.github/workflows/ci.yml`) runs the first
two, word for word:

```bash
(for t in ./hooks/*-selftest.*; do "$t" || exit 1; done)  # do the guards work
./tools/check-repo.py                 # do the repo checks pass
git log --oneline main..HEAD          # what is unmerged
claude plugin validate .              # whether it installs
npx skills add . -l                   # what the skills path would serve
```

- **Lane issues are retired** (2026-11-24, #228). A ticket's state lives on
  GitHub, as the Start here block says. Some `lane` issues are still open
  until their steps move to tickets: `gh issue list --label lane --state open`.
- **This repo names no free work check.** It has no root `CLAUDE.md` yet.
  So step 2 of the block sends a session to `## Next` below. #238 (move the
  Orca free-work, sweep and cleanup scripts into this repo) brings one.
- **The handoff layout is short now** (map #193). This file holds only the
  block, `## Now`, `## Next` and `## Read next`. A decision that passes the
  three ADR tests goes to `docs/adr/`. `docs/DECISIONS.md` is frozen.
- **Every PR raises the plugin version.** Each merge makes the next open
  branch rebase and take the next version. Before you bump, read the version
  on trunk: `git show origin/main:.claude-plugin/plugin.json`.

## Next

1. `parallel`: finish the lane retirement. For each open `lane` issue,
   copy each `## Next` step that is still open to its ticket as a comment,
   or open a ticket for it. Make each "after #X" a "blocked by" link. Then
   close the lane issue with a pointer to where its steps went. List them:
   `gh issue list --label lane --state open`.
2. `parallel`: the rest of handoff layer 3 (#196): #202 (give each of the
   9 old traps a check, a ticket or a `LESSONS.md` line) and #200 (the Handoff
   docs part of `~/CLAUDE.md`).
3. `after the owner reads this file`: #204 (move twenty,
   sals-day-in-life-dryrun and reimburse to this layout).
4. `parallel`: any other open ticket with no linked branch, no open
   blocker, and no `needs-owner` or `wayfinder:grilling` label:
   `gh issue list --state open --json number,title,labels`.

Waits on the owner:

- **Read this file, the pilot of the short layout, and say go or change
  for #204.**
- #159 (a CI step that runs recorded mutations) adds to a workflow. Ask
  before you add it.

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


## Read next

- `docs/adr/`: one file per decision, and why it went that way.
- `docs/DECISIONS.md`: older decisions and measurements, frozen on
  2026-11-24.
- `gh pr list --state merged --limit 50`: what merged. Each PR body's
  `## Handoff notes` says why.
- `git log -p -- docs/HANDOFF.md`: every earlier version of this file.
