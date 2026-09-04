---
name: bootstrap-repo-hygiene
description: Set up CI, pre-commit hooks, a PR template, and GitHub branch protection for a repo, matching the "pro dev / SDE agentic workflow" bar from CLAUDE.md's Git Workflow section. Use when the user asks to "set up CI", "add branch protection", "bootstrap this repo", "add git hygiene", "harden this repo's git workflow", or when starting real work in a repo that has none of this yet.
origin: authored
tags: [git, ci, github-actions, pre-commit, branch-protection, bootstrap]
version: 1.0.0
---

# Bootstrap Repo Hygiene

Stamps a repo up to the workflow bar `~/CLAUDE.md`'s "CI and branch
protection, not just local discipline" section describes. Built from doing
this by hand for `synthweave` (2026-07-31, PR #25) — the steps below encode
what actually went wrong that time so it doesn't get rediscovered.

**What's already global and does NOT need repeating per repo:**
- `~/.claude/hooks/git-safety-guard.sh`, wired as a `PreToolUse`/`Bash` hook
  in `~/.claude/settings.json`. Blocks direct commits to main/master,
  `--no-verify`/`--no-gpg-sign`, force-push to main/master, flags destructive
  commands without a prior `git status`. Applies everywhere already.
- The git-workflow rules in `~/CLAUDE.md` itself.

**What's inherently per-repo** (CI/pre-commit/branch-protection can only
live inside each repo — there's no global equivalent):

## Step 1: Detect the stack

Look for the dependency manifest to decide what CI should install/run:
- `pyproject.toml` → Python. Check `[project.optional-dependencies].dev`
  (or equivalent) for what's actually listed — don't assume test/lint tools
  are there just because a command in `CLAUDE.md` references them.
- `package.json` → Node. Use the `scripts` block for the real commands
  (`test`, `lint`, `build`) instead of guessing.
- Other stacks: find the repo's own documented commands first (its
  `CLAUDE.md`, README, or Makefile) and mirror those exactly in CI — CI
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
               `$([ -d examples ] && echo examples/)` — see Step 4>
```

Adapt the install/run lines to the detected stack (npm/pnpm/yarn install +
scripts for Node, etc.). Put it at `.github/workflows/ci.yml`.

## Step 3: Write pre-commit config

Local, fast feedback — but never treat this as the enforcement mechanism by
itself; it's bypassable with `--no-verify` (which the global hook also
blocks you specifically from using, but a human or another tool isn't
bound by that hook).

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0   # verify this is a real tag before using it — see Step 4
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

For the repo's own linter, prefer a `repo: local` hook that shells out to
the exact command already documented for the repo, rather than guessing at
a third-party pre-commit mirror repo — several expected mirrors (e.g. a
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

## Step 4: Verify before trusting either file — every one of these bit me once

1. **Confirm every tool CI/pre-commit invokes is actually installed by the
   install step.** A command being documented in the repo's `CLAUDE.md` does
   not mean it's in `pyproject.toml`'s `dev` extras (or `package.json`
   `devDependencies`). Check the manifest directly; add the tool if it's
   missing rather than assuming.
2. **Confirm every directory a command references actually exists in the
   branch CI runs against** (usually `main`, which may lag behind whatever
   feature branch you were just working in). A directory that exists on a
   feature branch but not yet on `main` will hard-fail CI with "No such file
   or directory" — make the reference conditional or drop it until merged.
3. **Confirm any pinned tool version (a pre-commit `rev:`, an action
   version) actually exists** — `curl -s https://api.github.com/repos/<org>/<repo>/tags`
   or `.../releases/latest`, don't guess a version number from memory.
4. **Run it for real before enabling branch protection.** Push a branch,
   open a PR (or push directly if the repo allows it pre-protection), and
   watch the actual CI run (`gh run watch <id> --exit-status`) rather than
   trusting the YAML looks right. A version-skew failure (CI's fresh
   `pip install` grabbing a newer major version of a core dependency than
   what's pinned/installed locally, e.g. pandas 2.x locally vs pandas 3.x in
   CI) is a realistic first-run failure, not a hypothetical — when it
   happens, that's a genuine finding worth logging to the repo's own issue
   tracker, not something to silently patch inside an unrelated infra PR.
   Narrow the CI matrix to what's known-good and log the incompatibility as
   a follow-up instead.
5. Only after CI is actually green on a real run, add the PR template
   (`.github/pull_request_template.md`, a short checklist of what CI already
   checks — don't reference tooling that isn't tracked/public if the repo
   deliberately keeps some directories private, e.g. via `.gitignore`).

## Step 5: Branch protection

`gh api` is picky about types — booleans passed via `-f` get sent as the
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
whatever feature branch happens to be checked out — it's a distinct,
single-purpose concern per `CLAUDE.md`'s PR-size guidance, and it needs to
land on `main` before branch protection can reference a check that's ever
actually run there.
