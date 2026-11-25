# A repo copies the mutation runner verbatim

Date: 2026-09-16

The runner that proves a repo's self-checks can fail lives once, at
`skills/mutation-gate/mutation_gate.py`. A repo copies it verbatim to
`scripts/mutation_gate.py`, and `diff` against the plugin's copy is the drift
check. CI on a GitHub runner has no plugin installed, so a call into the
plugin path works on one laptop only, which is the failure skill `harden`
exists to stop.

## Considered Options

- Call the runner from the plugin path: fails in CI, as above.
- Fetch the runner from this repo in CI: rejected, because it adds a network
  dependency to a gate whose claim is that it runs offline.

## Consequences

A fix to the runner reaches a repo only when that repo copies it again. The
`diff` is how a repo sees that its copy is behind.
