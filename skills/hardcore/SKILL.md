---
name: hardcore
description: Turn a prose rule into a mechanism (a hook that blocks, a CI check that fails, a config setting that forbids) with a self-test that proves it fires. Use when the user names a rule and says "/hardcore", asks "is this hardened or prosed", "make this a hook", "enforce this rule", "audit the rules in this repo", or when a rule broke after it was written down. Also sets up CI, pre-commit hooks, a PR template and branch protection: "set up CI", "add branch protection", "bootstrap this repo", "add git hygiene", "harden this repo's git workflow", or when starting real work in a repo that has none of this yet.
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
reading the output. Issue #94 (prose rules fail silently), collected on
2026-11-13, lists thirteen cases. This skill moves a rule from text into
something that runs.

Three ways in:

- **One rule.** The owner says "rule xxx, /hardcore". Run *One rule* below.
  This is the usual case.
- **Audit.** The owner asks to audit a repo's rules. Run *Audit* below.
- **Repo setup.** The repo has no CI or branch protection. Run *Repo setup*
  below. *One rule* also sends you there when a CI check needs a CI to live in.

## One rule

1. **Quote the rule and its source.** Copy the rule word for word with its
   file and line, e.g. `~/CLAUDE.md` section 7, or a memory file, or a lane
   issue's `## Next`. Write at least one broken input for each way the rule
   can break, e.g. a reply that holds an em-dash. Use a real break when one is
   known. Step 7 uses these inputs.
2. **Find every event where the violation shows.** A script can only see what
   an event hands it. List each event that carries the violation, e.g. a rule
   about all prose needs Stop for replies and PreToolUse on Write for files:
   - a tool call, before it runs (PreToolUse: the Bash command text, the Write
     content),
   - the end of a turn (Stop: the reply text and the transcript),
   - a tool call, after it ran (PostToolUse: e.g. a `gh pr merge` that
     finished),
   - a pushed branch (CI: the diff, the built files, the PR body),
   - a setting the tool already has (branch protection, `.gitignore`,
     `permissions.deny`),
   - a script the repo makes agents call (e.g. `scripts/lane_claim.py`): the
     script refuses.

   Event names and what each event carries change between Claude Code
   versions. Before you pick an event, read
   https://code.claude.com/docs/en/hooks.md and quote the line that says the
   event carries your input. For a subagent's work, the docs name the event
   that carries its report.
3. **Classify it.** The rule is *mechanical* when a script on that event can
   decide pass or fail with no reading of intent, e.g. "no em-dash in the
   reply" or "no merge without a review comment". It is *judgment* when only a
   reader can decide, e.g. "the method section keeps its coverage". A judgment
   rule ends here: say it cannot be enforced, say which word in it needs a
   reader, and change nothing. A rule with a mechanical part and a judgment
   part: enforce the mechanical part and name the part left as prose. A check
   on the mechanical part may also stop some correct work, e.g. blocking every
   `gh pr create --draft` for "never park work in a draft PR". Take it only
   when its override is cheap, and name the correct work it stops in the
   report.
4. **List what may already cover it, and let the owner decide.** Deciding
   cover alone is unreliable: a hook can be wired but switched off by a config
   key, and a self-test can test a function the hook never calls. So list
   candidates, and do not judge them. A candidate is a hook wired for an event
   from step 2 whose name, docstring or self-tests mention the rule's
   violation, a `permissions.deny` entry that names the exact tool, or a CI
   check whose file or script mentions the violation. Hooks are wired in the
   plugin's `hooks/hooks.json`, the `hooks` block of
   `~/.claude/settings.json`, the repo's `.claude/settings.json` and
   `.claude/settings.local.json`, and other enabled plugins. For each
   candidate, give:
   - the file, the event, the `matcher` and the `if`,
   - each thing that can switch it off, with its state where it runs (this
     machine for a hook, the CI job for a CI check): a config key (e.g.
     `"negation": False` in `hooks/handrail_config.py`, not set in
     `~/.handrail.toml`), an off-switch file (e.g. `~/.claude/.ste-off`), a
     block limit for each session (e.g. `MAX_BLOCKS_PER_SESSION = 2`),
   - each self-test case that mentions the violation, in any self-test that
     runs this mechanism, whether that case expects a block or an allow, and
     whether it runs the command the wiring calls or only calls a function
     inside the hook.

   No candidate: go on. Candidates: ask the owner, with one question for each
   event from step 2 that has candidates, all in one AskUserQuestion. Each
   question's options are "covered, stop", "build a new one", and "extend
   `<file>`" for at most two candidates in git, the closest first. Each answer
   applies to its own event only. An event with no candidate gets no question
   and goes on. The evidence for every candidate goes in the question text.
   The owner is usually present, since the owner named the rule. In an
   *Audit*, put the candidates in the table and ask nothing.

   This skill never edits a mechanism outside git (`~/.claude/hooks/`,
   `~/.claude/settings.json`), because no review can reach it, so such a
   candidate gets no "extend" option. "Build a new one" puts the new hook
   where step 5 says, and the report names the outside file beside it.
5. **Put it where the rule's scope is.**
   - Apply each step 4 answer to its own event. "Covered, stop" for an event:
     add nothing for that event. "Extend `<file>`": extend that hook or CI
     check, in the repo that holds it, and add nothing else for that event. An
     extended hook that must read a new event gets a new entry in the wiring
     file for that event. The bullets below apply only to events with no
     answer, or with "build a new one".
   - A rule from `~/CLAUDE.md` holds in every repo. For an event where the
     owner chose "build a new one", its hook goes in this plugin:
     `hooks/<name>.py`, wired in `hooks/hooks.json`. For an event with no step
     4 question, extend the plugin hook whose subject is closest, e.g.
     `hooks/claude-md-guard.py` for a rule about reply prose, or add a new one
     when no hook has that subject.
   - A rule for one repo (its `CLAUDE.md`, its memory, a lane issue) goes in
     that repo: a hook in `.claude/hooks/` wired in `.claude/settings.json`.
   - Add a CI check when the violation leaves a trace in the repo (a file, a
     diff, a PR body), because a cloud routine or a teammate never loads this
     laptop's hooks. A check counts only when it fires before the cost the
     rule protects, e.g. CI on a draft PR runs after the CI minutes are spent,
     so a draft-PR rule gets a hook. A rule about replies or tool calls leaves
     no trace, so it gets a hook only. No CI yet: run *Repo setup* first.
   - A rule from `~/CLAUDE.md` that leaves a trace gets both homes: the plugin
     hook, and a CI check in each repo where the owner names the trace as a
     problem. Ask the owner which repos when the rule does not say. Code the
     plugin ships for repos to copy (e.g. `skills/handoff/lane_claim.py`) is
     changed in the plugin, then copied.
   - A rule a subagent must follow needs a hook. A subagent never reads the
     parent's memory, and hooks from settings files and plugins run inside
     subagents too ("When a subagent calls a tool, tool events such as
     `PreToolUse` and `PostToolUse` fire the same configured hooks as in the
     main conversation", https://code.claude.com/docs/en/hooks.md).

   Say the choice in one line before you build.
6. **Take the cheapest mechanism that blocks**, in this order: a hook that
   blocks, CI that fails, a config setting that forbids. A new hook blocks by
   exiting 2 with the reason on stderr. An extended hook keeps the way it
   blocks already, e.g. the JSON decision of `hooks/claude-md-guard.py`. A
   warning that only prints is the last choice, used only where a block would
   stop correct work, and the report says so. A rule that says to do a step
   after an event, e.g. "render the PDF again after each merge", gets a
   mechanism that does the step: a PostToolUse hook or a CI job on push to
   `main`. Doing the step beats blocking the next one.
7. **Build it test first.** Write the self-test before the hook, beside it as
   `<name>-selftest.py`, in a folder whose self-tests the repo's CI runs
   (here, `.github/workflows/ci.yml` runs `hooks/*-selftest.*`), in the shape
   of `hooks/no-ai-attribution-selftest.py`. An extended hook gets new cases
   in its own self-test. The self-test holds each broken input from step 1
   with the result it must give, and one valid input that must pass. Each case
   feeds the hook's entry point, the command the wiring calls, with that
   event's JSON and a new `session_id`. The case's tool name must match the
   wiring's `matcher` and `if`, or the hook never runs in a session.
   `hooks/no-ai-attribution-selftest.py` runs its PreToolUse hook as a command
   with event JSON, and `hooks/handrail-config-selftest.py` runs its Stop hook
   with a transcript and a new `session_id`. For a CI check, a case puts a
   file that holds the violation into a copy of the repo, runs the check's
   command there, and expects a non-zero exit. A case that only calls a
   function inside the hook does not prove the wired hook blocks. Run the
   self-test and see each new case fail. A new case that passes before you
   change the hook: stop, and show the owner that case. Then write the hook.
   Give the hook an override that shows in the command, e.g. `SKIP_<NAME>=1`,
   and say it in the block message. A rule that says it has no override gets
   none. Add a `mutation-gate` entry when the repo has the gate.
8. **Point the prose at the mechanism, after it is live.** Keep the rule's
   text. Add one line after it, or extend the `Enforced by` line it has, e.g.
   `Enforced by <file> (<event>, blocks the call).` Write what it does: blocks
   the call, blocks the turn, fails CI, or does the step. Add the line only
   when the mechanism runs. For a repo hook or CI check, that is the merge.
   For a plugin hook, it is the merge, then `claude plugin marketplace update
   yw-workflow`, then `claude plugin update yw-workflow@yw-workflow`, then a
   restart of Claude Code. A line in `~/CLAUDE.md` that names a mechanism not
   yet installed sends every session to something that is not there. This line
   is the one edit the skill makes to a file outside git, and the report
   quotes it.
9. **Ship it** through `/yw-workflow:ship-loop`. Each repo the rule touches
   gets its own PR, the plugin first. The reviewer gets the broken inputs to
   try, and asks for three more.

Report back: the rule, each event, the file, the command that proves it fails
on a violation, any part left as prose, and any correct work the check stops.

## Audit

1. **Collect the rules.** Read the repo's `CLAUDE.md`, `~/CLAUDE.md`, the
   project memory folder, `docs/HANDOFF.md`, the open `lane` issues, and the
   repo's skill bodies. A rule is any sentence that tells an agent what it
   must or must not do.
2. **Run steps 1 to 6 of *One rule* on each rule**, without building. A rule
   with step 4 candidates gets a *Candidates* cell in the table, for the owner
   to judge. It gets no ticket until the owner has judged it. An `Enforced by`
   line is a claim, so it gets the same run.
3. **Write the table**, one row per rule:

   | Rule (quoted) | Source | Class | Event | Candidates | Mechanism and home
   | Proof command |
   |---|---|---|---|---|---|---|

   The proof command is the one that shows the mechanism fails on a
   violation, e.g. `python3 hooks/<name>-selftest.py`. A judgment row says
   why in the Mechanism cell and has no proof command.
4. **File one ticket per mechanism**, agent-ready. Rows that share one event
   and one hook go in one ticket. Each ticket holds the rule and source,
   the broken inputs, acceptance criteria as boxes, and the proof command.
   When the owner asked for the table only, print the `gh issue create`
   commands and file nothing.
5. **Build the tickets** through `/yw-workflow:ship-loop`, one *One
   rule* run each. Keep at most four built branches waiting for review.

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

- Each mechanism ships through `/yw-workflow:ship-loop`, one PR for each
  repo a ticket touches. The reviewer from `/yw-workflow:fresh-eye` tries
  the broken inputs.
- A new self-check in a repo with the gate: `/yw-workflow:mutation-gate` proves
  it can fail.
- The repo is set up: `/yw-workflow:ship-loop` is what merges through the gate
  you just built.
- `git-safety-guard.sh` protects one laptop only. A cloud routine never touches
  it, so the review gate belongs in CI as a required status check.
- Adding a git wrapper (`wt`, lazygit, a Makefile target) means adding its
  command names to the hook in the same commit. See `docs/DECISIONS.md` in this plugin.
- The team needs to know why the gate exists before they resent it:
  `/yw-workflow:eli5` makes the case in one page.
