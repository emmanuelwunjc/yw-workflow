# Hooks, CI gate and config

The detail behind the short tables in `README.md`.

### Hooks

Each exists because a rule broke and prose was not enough. They come with the
plugin path only.

| | | |
|---|---|---|
| **git-safety-guard.sh** | PreToolUse, `git *` | Blocks commits straight to `main` and tree moves that collide with another agent. |
| **require-code-review.py** | PreToolUse | Blocks `gh pr merge <number>` on a 25+ line PR with no review, looked up in the repo the command targets (`cd`, `-R`, a PR URL, `GH_REPO`) rather than the folder the session started in. A merge it finds and cannot tie to a literal PR and repo is blocked with a request for `-R owner/repo`. It reads the merge from the command text, so a command that only mentions one with a number is judged as a merge, and a merge with no number is invisible to it (#17). Override: `export SKIP_REVIEW_GATE=1;` in front of the command, announced on stderr when honored. |
| **no-ai-attribution.py** | PreToolUse | Keeps AI-generation footers out of anything people read. Commit trailers stay. |
| **zsh-trap-guard.py** | PreToolUse | The Bash tool runs commands under zsh. Blocks an unbraced `$name:` before a letter zsh reads as a modifier (`$s:refs` applies `:r`, so write `${s}:refs`), and `for v in $VAR`, which zsh does not split into words. Ignores single-quoted text and quoted heredocs. Switch: `[rules] zsh_traps`. |
| **claude-md-guard.py** | UserPromptSubmit, Stop | Blocks em-dashes, negation-then-correction, and prose questions where checkboxes are required. |
| **handoff-freshness.py** | Stop | On a lane whose net diff from trunk changes real files, reminds it to write the PR body's `## Handoff notes` section, and warns any lane (a detached HEAD included) whose net diff changes `docs/HANDOFF.md`. On trunk (`main`, `master`, or what `origin/HEAD` names) or a `docs/handoff-*` branch, catches work piling up against an untouched `docs/HANDOFF.md`. Also catches a `docs/HANDOFF.md` that lacks the `## Start here` block, has a block that never lists the open `lane` issues, still opens with an "end of a session" preamble, has a block that runs `scripts/lane_claim.py` in a repo without that file, or has a handoff-named `.md` tracked outside `docs/` (the shape in skill `handoff`). Override: `SKIP_HANDOFF_CHECK=1`. |
| **context-handoff.py** | PostToolBatch, UserPromptSubmit, Stop | Winds a session down when its context passes about 120k tokens, the end of the "smart zone", and again at every 100k past that. The notice tells the model to start no new work, spawn no subagents, let running ones finish for at most 15 minutes, then write the handoff and tell the user to start a fresh session. After the 15 minutes, with no handoff written, a second notice says to save what each running subagent has, stop it, and write the handoff now. Blocks one Stop per notice while `docs/HANDOFF.md` is untouched since the notice, on any branch or worktree. Known limits: it cannot see a lane's notes in a PR body, or anything in a folder that is not a git repo, so there the deadline notice and the one block always arrive. The hook instructs and the model acts: it stops no subagent itself. Reads the size from the last assistant message's usage in the transcript. Main thread only. Settings: `[rules] context_handoff` and `[context_handoff] first`, `step`, `grace_minutes` in `.handrail.toml`. |

Wire them in one place only. Wiring the same hook here and in
`~/.claude/settings.json` fires it twice and halves its block budget.

`git-safety-guard.sh` matches the literal string `git `. A wrapper (`wt`,
lazygit, a Makefile target) runs git as a subprocess and every rule stops
applying, so adding one means adding its command names to the hook in the same
commit.


### CI gate

A hook protects one machine. Anyone who skips the install, sets
`TEAMAI_HOOKS_DISABLED=1`, or clones on a fresh laptop is unguarded, and nothing
says so. The same rules run server-side as a composite action, so a team gets
them as a required status check:

```yaml
# .github/workflows/guards.yml in any repo
on: pull_request
permissions:
  contents: read
  pull-requests: read
jobs:
  guards:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: emmanuelwunjc/yw-workflow/.github/actions/guards@main
```

Pin a release tag in place of `@main` so a change here cannot alter what a
consumer's required check enforces.

Then name `guards` as a required context in branch protection, or the check is
advisory and a red run merges anyway.

The action takes no inputs, so no rule can be switched off. A selector gated on
a substring match turns one typo into a job that skips every step and reports
success, which is what the first two versions of this action did. Each rule
still scopes itself to what it reads, so a PR touching only `.py` files scans no
prose and the review gate carries the run.

The action assumes a Linux runner. `xargs -a`, `xargs -d` and process
substitution are what the steps are built on. Its scratch files go in
`$RUNNER_TEMP`, which is job-scoped, so two jobs on one self-hosted runner do
not overwrite each other's file lists.

| Rule | What it reads | What fails the job |
|---|---|---|
| `claude-md` | changed `.md` and `.txt` files | an em-dash or a negation-then-correction in prose, with code fences exempt |
| `no-ai-attribution` | the PR body and changed prose files | a generation footer or a session URL, and in the PR body a `Claude-Session:` line too. That trailer still passes inside changed files |
| `review-gate` | the PR's files, reviews, and comments | a 25+ line code diff with no approval and no verdict comment, including a verdict the author posted themselves |

Three differences from the hook path, each deliberate:

- **It fails closed.** A guard that crashes, or an API lookup that comes back
  empty, fails the job. The hooks do the opposite, because a broken guard must
  never wedge a live session. A required check that passes when it could not run
  is a rubber stamp.
- **`review-gate` skips the all-checks-green gate the hook runs first.** In CI
  this check is one of those checks, so asking whether every check is green
  would always find this one in progress.
- **Attribution scanning stops at prose.** A guard, a test, or a script that
  quotes the banned footer on purpose is source. This repo's own hooks are that
  case, and scanning every changed file reports the rule's documentation as a
  violation of itself.

There is no author filter on that verdict comment, which is how this repo's own
flow satisfies the gate: a review runs, its verdict is posted, the gate opens.
Requiring a second GitHub account would make it unsatisfiable for a solo
maintainer. Branch protection is where "somebody else must approve" belongs.

`SKIP_REVIEW_GATE=1` has no effect here. Bypassing a server-side gate is a
branch-protection decision, and it belongs with the people who own the branch.


### Config

**Read this first: only `claude-md-guard.py`, `no-ai-attribution.py`,
`context-handoff.py` and `zsh-trap-guard.py` consult the config today.** The
`[rules]` switches and `policy_doc` work for the first two,
`context-handoff.py` reads its switch and its `[context_handoff]` values, and
`zsh-trap-guard.py` reads only its switch.
The other value keys below are parsed and are not yet read by any guard, so
`trivial_lines` and `protected` change nothing until the unit that wires them
lands. `git-safety-guard.sh` still hardcodes `main` and `master`, and
`require-code-review.py` still hardcodes 25 lines. The CI half is not wired
either: the action runs the guards' `scan` entry points, which never read a
config.

Every rule is on by default except negation-then-correction, which is the one
heuristic with known false positives. To change that, write `.handrail.toml` in
a repo, or `~/.handrail.toml` for your machine.

```toml
policy_doc = "ENGINEERING.md"     # cited in block messages when the file exists

[rules]
negation = true                   # off by default
em_dash = false                   # only your user config may switch one off

[git_safety]
protected = ["main", "trunk"]

[require_review]
trivial_lines = 10

[context_handoff]
first = 120000                    # tokens; the first wind-down notice
step = 100000                     # tokens; the notice repeats per step past it
grace_minutes = 15                # how long running subagents may finish
```

A repo config may switch a rule **on**. Only your user config may switch one
**off**, so a repo you clone can make you stricter and never laxer. One
exception, and it is inherent: if your home directory is itself a git checkout,
as the dotfiles-in-a-bare-repo pattern does, then that repo's `.handrail.toml`
is your user config and can switch rules off.

The repo config is looked for between the current directory and the repository
root, and the root comes from `git rev-parse --show-toplevel`. A root that is
neither the current directory nor one of its parents is refused, because
`GIT_DIR` and `GIT_WORK_TREE` can point git at a tree the current directory has
nothing to do with. A
config above that boundary is ignored, so a `.handrail.toml` in a shared parent,
a world-writable one included, cannot govern a checkout below it. Outside a
repository only the current directory is trusted. Linked worktrees, submodules and bare
checkouts behave the way git says they do, subject to that ancestry rule.
Thresholds
sit outside that ratchet: a repo sets them freely, because a monorepo full of
generated files has a real reason to move the review threshold. So the guarantee
is that a repo cannot switch a guard off, rather than that a repo cannot weaken
your guards.

Block messages explain their rule on their own terms and append `See
<policy_doc>.` only when that file is configured and present. A citation
pointing at a file the reader does not have is worse than none.

Where tomllib is missing (Python before 3.11), `.handrail.json` is read instead.
With both files present a session reads the TOML and warns. The CI half of that
rule, which fails the job instead, is written and not yet wired.

Repo-controlled text is kept out of block messages, because a guard's stderr is
handed to the model as the reason it was blocked and anything in it reads as an
instruction. A `policy_doc` is refused unless it is a plain relative path of
letters, digits, dots, dashes, underscores and slashes, under 100 characters. A
path printed in a warning has every other character replaced with `?`. A
parser's error contributes its type and never its message, since a TOML key is
arbitrary text and quoting the file back is how the file gets to speak.

