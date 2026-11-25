# Each guard is one script for both the hook and CI

Date: 2026-09-08

CI mode is a subcommand on each existing guard, e.g.
`hooks/claude-md-guard.py scan FILE...`, `hooks/no-ai-attribution.py scan FILE...`
and `hooks/require-code-review.py check-pr N`. The detection logic is shared,
so the rule CI enforces cannot drift from the rule the hook enforces. A
separate CI linter would be two policies with one name.

## Considered Options

- A second script for CI: rejected for the drift above.
- Run the guards action on `pull_request_target`: rejected. It gives a
  privileged token to a workflow that runs `hooks/*.py` from the PR head.
  So a fork PR runs its author's code with write scope. The reason is also in
  `.github/actions/guards/action.yml`.

## Consequences

The two modes fail in opposite directions, and `hooks/scan-modes-selftest.py`
tests both. A crash in hook mode exits 0, so a guard never wedges a live
session. A crash in `scan` mode fails the job. `check-pr` runs the review
gate only: in CI it is itself one of the checks, so an all-checks-passed
gate would always find itself in progress.
