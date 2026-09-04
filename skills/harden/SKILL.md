---
name: harden
description: Set up CI, pre-commit hooks, a PR template, and GitHub branch protection for a repo, so its review gate holds where the work runs rather than only on one laptop. Use when the user asks to "set up CI", "add branch protection", "bootstrap this repo", "add git hygiene", "harden this repo's git workflow", or when starting real work in a repo that has none of this yet.
origin: authored
tags: [git, ci, github-actions, pre-commit, branch-protection, bootstrap]
version: 1.0.1
---

# Harden

**In one line:** Gives a repo the CI and branch protection that make its review gate real.

Say that line back when you start, so whoever invoked this knows
what they got.

Stamps a repo up to one bar: every rule the team relies on is enforced by
something the repo carries, so it holds for a cloud routine, a remote agent and
a teammate's checkout, rather than only where a local hook happens to be
installed. Built from doing
this by hand for `synthweave` (2026-07-31, PR #25). The steps below encode
what actually went wrong that time so it doesn't get rediscovered.

**What's already global and does NOT need repeating per repo:**
- this plugin's `hooks/git-safety-guard.sh`, wired by its own
  `hooks/hooks.json` under `${CLAUDE_PLUGIN_ROOT}` and active wherever the
  plugin is enabled. Blocks direct commits to main/master,
  `--no-verify`/`--no-gpg-sign`, force-push to main/master, and flags
  destructive commands without a prior `git status`.

  It protects one machine only. A cloud routine, a remote agent, or a
  teammate's checkout never loads it, which is the whole reason the per-repo CI
  gate below exists.
- Whatever git-workflow rules your own setup already enforces globally.

**What's inherently per-repo** (CI/pre-commit/branch-protection can only
live inside each repo, so there is no global equivalent):

## Step 1: Detect the stack

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

## Step 2: Write CI (GitHub Actions)

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

## Step 3: Write pre-commit config

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

## Step 4: Verify before trusting either file. Every one of these bit me once

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

## Step 5: Branch protection

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

## Step 6: Scope discipline

If the repo already has an open, unrelated PR in flight, put this hygiene
work on its own short-lived branch off `main` rather than bundling it into
whatever feature branch happens to be checked out. It's a distinct,
single-purpose concern, one self-contained change per PR, and it needs to
land on `main` before branch protection can reference a check that's ever
actually run there.

## Hands off to

- The repo is hardened: `/yw-workflow:ship-loop` is what merges through the gate you just
  built.
- `git-safety-guard.sh` protects one laptop only. A cloud routine never touches
  it, so the review gate belongs in CI as a required status check. That is why
  this skill exists rather than trusting the hook.
- Adding a git wrapper (`wt`, lazygit, a Makefile target) means adding its
  command names to the hook in the same commit. See `docs/DECISIONS.md` in this plugin.
