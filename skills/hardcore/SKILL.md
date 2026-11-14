---
name: hardcore
description: Turn a prose rule into a mechanism (a hook that blocks, a CI check that fails, a config setting that forbids) with a self-test that proves it fires. Use when the user names a rule and says "/hardcore", asks "is this hardened or prosed", "make this a hook", "enforce this rule", "audit the rules in this repo", or when a rule broke after it was written down. Also sets up CI, pre-commit hooks, a PR template and branch protection: "set up CI", "add branch protection", "bootstrap this repo", "add git hygiene".
origin: authored
tags: [rules, hooks, ci, enforcement, branch-protection, bootstrap]
version: 2.0.0
---

# Hardcore

**In one line:** Turns a rule written as prose into a hook or CI check that blocks the violation.

Say that line back when you start, so whoever invoked this knows
what they got.

A prose rule holds while it sits in the reader's recent context. It fails
once the session moves on, a skill body loads later, or the work goes to a
subagent that never saw it. The failure is silent: the owner finds it by
reading the output. Issue #94 (prose rules fail silently) lists thirteen
cases from one week. This skill moves a rule from text into something that
runs.

Three ways in:

- **One rule.** The owner says "rule xxx, /hardcore". Run *One rule* below.
  This is the usual case.
- **Audit.** The owner asks to audit a repo's rules. Run *Audit* below.
- **Repo setup.** The repo has no CI or branch protection. Run *Repo setup*
  below. *One rule* also sends you there when a CI check needs a CI to live in.

## One rule

1. **Quote the rule and its source.** Copy the rule word for word with its
   file and line, e.g. `~/CLAUDE.md` section 7, or a memory file, or a lane
   issue's `## Next`. Name one real time it broke, if one is known.
2. **Find the event where the violation shows.** A script can only see what
   an event hands it. Pick the first one that carries the violation:
   - a tool call, before it runs (PreToolUse: the Bash command text, the
     Write content),
   - the end of a turn (Stop: the reply text and the transcript),
   - a tool call, after it ran (PostToolUse: e.g. a `gh pr merge` that
     finished),
   - a pushed branch (CI: the diff, the built files, the PR body),
   - a setting the tool already has (branch protection, `.gitignore`,
     `permissions.deny`).
3. **Classify it.** The rule is *mechanical* when a script on that event can
   decide pass or fail with no reading of intent, e.g. "no em-dash in the
   reply" or "no merge without a review comment". It is *judgment* when only
   a reader can decide, e.g. "the method section keeps its coverage". A
   judgment rule ends here: say it cannot be enforced, say which word in it
   needs a reader, and change nothing. A rule with a mechanical part and a
   judgment part: enforce the mechanical part and name the part left as
   prose.
4. **Put it where the rule's scope is.**
   - A rule from `~/CLAUDE.md` holds in every repo. Its hook goes in this
     plugin: `hooks/<name>.py`, wired in `hooks/hooks.json`.
   - A rule for one repo (its `CLAUDE.md`, its memory, a lane issue) goes in
     that repo: a hook in `.claude/hooks/` wired in `.claude/settings.json`.
   - Add a CI check when the violation leaves a trace in the repo (a file, a
     diff, a PR body), because a cloud routine or a teammate never loads this
     laptop's hooks. A rule about replies or tool calls leaves no trace, so it
     gets a hook only. No CI yet: run *Repo setup* first.
   - A rule from `~/CLAUDE.md` that leaves a trace gets both homes: the plugin
     hook, and a CI check in each repo that needs it. Code the plugin ships
     for repos to copy (e.g. `skills/handoff/lane_claim.py`) is changed in the
     plugin, then copied.
   - A rule a subagent must follow needs a hook. A subagent never reads the
     parent's memory, and hooks from settings files and plugins run inside
     subagents too ("When a subagent calls a tool, tool events such as
     `PreToolUse` and `PostToolUse` fire the same configured hooks as in the
     main conversation", https://code.claude.com/docs/en/hooks.md).

   Say the choice in one line before you build.
5. **Take the cheapest mechanism that blocks**, in this order: a hook that
   blocks, CI that fails, a config setting that forbids. A hook blocks: it
   exits 2 with the reason on stderr. A warning that only prints is the last
   choice, used only where a block would stop correct work, and the report
   says so. A rule that says to do a step after an event, e.g. "render the PDF
   again after each merge", gets a mechanism that does the step: a
   PostToolUse hook or a CI job on push to `main`. Doing the step beats
   blocking the next one.
6. **Build it test first.** Write the self-test before the hook, beside it as
   `<name>-selftest.py`, in the shape of `hooks/no-ai-attribution-selftest.py`.
   It holds each broken input from step 1 with the result it must give, and
   one valid input that must pass. Run it and see it fail. Then write the
   hook. Give the hook an override that shows in the command, e.g.
   `SKIP_<NAME>=1`, and say it in the block message. Add a `mutation-gate`
   entry when the repo has the gate.
7. **Point the prose at the mechanism.** Keep the rule's text, and add one
   line after it: `Enforced by <file> (<event>, blocks the turn).` The text
   keeps the reason a reader needs. The line tells them the rule no longer
   depends on memory.
8. **Ship it as one PR** through `/yw-workflow:ship-loop`. The reviewer gets
   the broken inputs to try, and asks for three more.

Report back: the rule, the event, the file, the command that proves it fails
on a violation, and any part left as prose.

## Audit

1. **Collect the rules.** Read the repo's `CLAUDE.md`, `~/CLAUDE.md`, the
   project memory folder, `docs/HANDOFF.md`, the open `lane` issues, and the
   repo's skill bodies. A rule is any sentence that tells an agent what it
   must or must not do.
2. **Drop the ones already enforced.** A rule with an `Enforced by` line, or
   one a hook already blocks, is done. Check the hook exists before you drop
   the rule.
3. **Run steps 2 to 5 of *One rule* on each one left**, without building.
4. **Write the table**, one row per rule:

   | Rule (quoted) | Source | Class | Event | Mechanism and home | Proof command |
   |---|---|---|---|---|---|

   The proof command is the one that shows the mechanism fails on a
   violation, e.g. `python3 hooks/<name>-selftest.py`. A judgment row says
   why in the Mechanism cell and has no proof command.
5. **File one ticket per mechanism**, agent-ready. Rows that share one event
   and one hook go in one ticket. Each ticket holds the rule and source,
   the broken inputs, acceptance criteria as boxes, and the proof command.
   When the owner asked for the table only, print the `gh issue create`
   commands and file nothing.
6. **Build the tickets** through `/yw-workflow:ship-loop`, one PR each, one
   *One rule* run each. Keep at most four built branches waiting for review.

## Repo setup: CI and branch protection

This part stamps a repo up to one bar: every rule the team relies on is enforced by
something the repo carries, so it holds for a cloud routine, a remote agent and
a teammate's checkout, rather than only where a local hook happens to be
installed. Built from doing
this by hand for `synthweave` (2026-07-31, PR #25). Its steps encode
what actually went wrong that time so it doesn't get rediscovered.

**What is already global and does NOT need repeating per repo:**
- this plugin's `hooks/git-safety-guard.sh`, wired by its own
  `hooks/hooks.json` under `${CLAUDE_PLUGIN_ROOT}` and active wherever the
  plugin is enabled. Blocks direct commits to main/master,
  `--no-verify`/`--no-gpg-sign`, force-push to main/master, and flags
  destructive commands without a prior `git status`.

  It protects one machine only. A cloud routine, a remote agent, or a
  teammate's checkout never loads it, which is the whole reason the per-repo CI
  gate below exists.
- Whatever git-workflow rules your own setup already enforces globally.

**What is inherently per-repo** (CI/pre-commit/branch-protection can only
live inside each repo, so there is no global equivalent):

### Step 1: Detect the stack

Look for the dependency manifest to decide what CI should install/run:
- `pyproject.toml` → Python. Check `[project.optional-dependencies].dev`
  (or equivalent) for what's actually listed. Don't assume test/lint tools
  are there just because a command in `CLAUDE.md` references them.
- `package.json` → Node. Use the `scripts` block for the real commands
  (`test`, `lint`, `build`) instead of guessing.
- Other stacks: find the repo's own documented commands first (its
  `CLAUDE.md`, README, or Makefile) and mirror those exactly in CI, because CI
  should run precisely what's already been decided as "the commands", not a
  fresh policy.

### Step 2: Write CI (GitHub Actions)

Mirror the real dev commands. For a Python project via `pyproject.toml` and
a `dev` extras group:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]   # start with ONE version, see Step 4
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: <the repo's real test command>
      - run: <the repo's real lint command, made conditional if it
               references a directory that might not exist yet, e.g.
               `$([ -d examples ] && echo examples/)` (see Step 4)>
```

Adapt the install/run lines to the detected stack (npm/pnpm/yarn install +
scripts for Node, etc.). Put it at `.github/workflows/ci.yml`.

### Step 3: Write pre-commit config

Local, fast feedback. Never treat this as the enforcement mechanism by
itself; it's bypassable with `--no-verify` (which the global hook also
blocks you specifically from using, but a human or another tool isn't
bound by that hook).

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0   # verify this is a real tag before using it (see Step 4)
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

For the repo's own linter, prefer a `repo: local` hook that shells out to
the exact command already documented for the repo, rather than guessing at
a third-party pre-commit mirror repo. Several expected mirrors (e.g. a
`PyCQA/pyflakes` pre-commit hook, `pre-commit/mirrors-pyflakes`) don't
actually exist. Example:

```yaml
  - repo: local
    hooks:
      - id: <linter-name>
        name: <linter-name>
        entry: <the repo's real lint command>
        language: system
        files: ^(src|tests)/
        types: [python]
```

Put it at `.pre-commit-config.yaml`.

### Step 4: Verify before trusting either file. Every one of these bit me once

1. **Confirm every tool CI/pre-commit invokes is actually installed by the
   install step.** A command being documented in the repo's `CLAUDE.md` does
   not mean it's in `pyproject.toml`'s `dev` extras (or `package.json`
   `devDependencies`). Check the manifest directly; add the tool if it's
   missing rather than assuming.
2. **Confirm every directory a command references actually exists in the
   branch CI runs against** (usually `main`, which may lag behind whatever
   feature branch you were just working in). A directory that exists on a
   feature branch but not yet on `main` will hard-fail CI with "No such file
   or directory". Make the reference conditional or drop it until merged.
3. **Confirm any pinned tool version (a pre-commit `rev:`, an action
   version) actually exists**. Run `curl -s https://api.github.com/repos/<org>/<repo>/tags`
   or `.../releases/latest`, don't guess a version number from memory.
4. **Run it for real before enabling branch protection.** Push a branch,
   open a PR (or push directly if the repo allows it pre-protection), and
   watch the actual CI run (`gh run watch <id> --exit-status`) rather than
   trusting the YAML looks right. A version-skew failure (CI's fresh
   `pip install` grabbing a newer major version of a core dependency than
   what's pinned/installed locally, e.g. pandas 2.x locally vs pandas 3.x in
   CI) is a realistic first-run failure, not a hypothetical. When it
   happens, that's a genuine finding worth logging to the repo's own issue
   tracker, not something to silently patch inside an unrelated infra PR.
   Narrow the CI matrix to what's known-good and log the incompatibility as
   a follow-up instead.
5. Only after CI is actually green on a real run, add the PR template
   (`.github/pull_request_template.md`, a short checklist of what CI already
   checks. Don't reference tooling that isn't tracked/public if the repo
   deliberately keeps some directories private, e.g. via `.gitignore`).
   Give it a `## Handoff notes` section too, the one `/yw-workflow:handoff`
   carries, so each lane's notes reach the handoff pass without the lane
   editing `docs/HANDOFF.md`.

### Step 5: Branch protection

`gh api` is picky about types. Booleans passed via `-f` get sent as the
string `"true"` and rejected. Use a JSON payload file with `--input`
instead of `-f`/`-F` flags:

```bash
cat > /tmp/branch-protection.json <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["<exact CI job name from the run you just watched>"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
gh api repos/<owner>/<repo>/branches/main/protection -X PUT \
  -H "Accept: application/vnd.github+json" --input /tmp/branch-protection.json
```

The `contexts` value must exactly match the job name GitHub shows in the
Checks tab (e.g. `test (3.11)` for a matrixed job named `test`), not the
workflow name.

### Step 6: Scope discipline

If the repo already has an open, unrelated PR in flight, put this hygiene
work on its own short-lived branch off `main` rather than bundling it into
whatever feature branch happens to be checked out. It's a distinct,
single-purpose concern, one self-contained change per PR, and it needs to
land on `main` before branch protection can reference a check that's ever
actually run there.

## Hands off to

- Each mechanism ships through `/yw-workflow:ship-loop`, one PR per rule, and
  the reviewer from `/yw-workflow:fresh-eye` tries the broken inputs.
- A new self-check in a repo with the gate: `/yw-workflow:mutation-gate` proves
  it can fail.
- The rule turned out to be a decision only the owner can make:
  `/yw-workflow:need-me`.
- The repo is set up: `/yw-workflow:ship-loop` is what merges through the gate
  you just built.
- `git-safety-guard.sh` protects one laptop only. A cloud routine never touches
  it, so the review gate belongs in CI as a required status check.
- Adding a git wrapper (`wt`, lazygit, a Makefile target) means adding its
  command names to the hook in the same commit. See `docs/DECISIONS.md` in this plugin.
- The team needs to know why the gate exists before they resent it:
  `/yw-workflow:eli5` makes the case in one page.
