---
name: mutation-gate
description: Prove a repo's self-checks can fail, by applying recorded two-line breakages to each script and requiring its own check to catch them. Use when a review finds an assertion that could not fail, when a ticket names a rule as one that must be provable by mutation, when adopting the gate in a new repo ("add the mutation gate", "mutation test the scripts"), or when deciding whether a proposed gate entry has earned its place.
origin: authored
tags: [testing, mutation, ci, self-check, review]
version: 1.0.0
---

# Mutation gate

**In one line:** Proves each self-check can fail, by breaking the code it covers and requiring it to notice.

Say that line back when you start, so whoever invoked this knows what they got.

## Why it exists

Adversarial review rounds on one repo kept returning the same finding: the
production code was right and the assertion written to prove it could not fail.
Each round relocated the hole to whatever the newest commit had added, and
reviewing harder did not close it. This closes it mechanically. Measured on
2026-09-16: 281 recorded breakages (`--list | wc -l` on that repo before #186),
and the gate is what caught them.

## The rule for adding an entry

An entry is added only when:

- a ticket names the rule as one that must be provable by mutation, or
- a review found an assertion that could not fail.

The entry's `source` cites that ticket or PR. No entry for a rule nobody has
seen break: a guard needs an incident behind it, and a list that grows one
entry per guard by habit costs review attention on every diff. An entry with
no `source` fails `--list` by name, so the rule is enforced by the runner
rather than by a sentence.

Retire, never delete. When a script's one-shot job is done (its `--apply` ran
and its plan is archived), move its entries to `retired` with the date. The run
skips them; `--list --retired` still prints them, so the record of what the
review rounds found survives.

## Adopt it in a repo

The runner exists once, here, at `skills/mutation-gate/mutation_gate.py`. A
repo supplies only the data file.

1. Every script under `scripts/` exposes a `_demo()` that runs offline, with no
   key and no network, and prints `demo ok` as its last line. `python3
   scripts/x.py --demo` calls it. That is the self-check the gate breaks.
2. Copy the runner verbatim to `scripts/mutation_gate.py`. `diff` against this
   plugin's copy is the drift check; edit here, then re-copy.
3. Write `scripts/mutations.json`:

   ```json
   {
     "mutations": [
       {"script": "x.py", "label": "domain taken from the first @, not the last",
        "find": "email.rsplit(\"@\", 1)[-1]", "replace": "email.split(\"@\")[1]",
        "source": "#111"}
     ],
     "retired": []
   }
   ```

   `script` is a bare filename beside the JSON file, so moving a script is one
   edit. `find` must occur exactly once, in production code, outside that
   script's own `_demo`. A match inside the fixture breaks the check rather
   than the code and records a kill nothing earned; the runner refuses it.
4. Add the CI step, after the step that runs every `_demo`:

   ```yaml
   - name: Mutation gate
     run: python scripts/mutation_gate.py
   ```

Commands, from the repo root:

    python3 scripts/mutation_gate.py                   # every active entry
    python3 scripts/mutation_gate.py --list            # names and sources
    python3 scripts/mutation_gate.py --list --retired  # what was retired, and when
    python3 scripts/mutation_gate.py --demo            # the runner's own self-check
    python3 scripts/mutation_gate.py other/mutations.json

Offline. Each run, baseline or mutant, copies the scripts directory to its own
temporary directory, so a killed run leaves nothing mutated behind. Mutants
run in parallel; a hang counts as killed, bounded by `DEMO_TIMEOUT_SECONDS`.

## Reading a failure

- `SURVIVED x.py: <label>`: the assertion covering that defect does not exist
  or cannot fail. Add the case that catches it, in the same PR.
- `no longer matches any code`: the code the entry targeted was renamed or
  deleted. Retarget it, or retire it and say why in the commit.
- `occurs N times`: the `find` string is ambiguous and would mutate the first
  match. Anchor it on enough surrounding lines to be unique.
- `--demo fails BEFORE any mutation`: the baseline is broken. Fix that first;
  a gate whose baseline fails proves nothing.

## Hands off to

- `/yw-workflow:fresh-eye` is where entries come from: a reviewer who finds an
  assertion that cannot fail names it, and the fix adds the entry with the PR
  as its `source`.
- `/yw-workflow:harden` wires the CI step so the gate holds where the work
  runs, rather than only on one laptop.
- `/yw-workflow:ship-loop` runs the gate as part of "run what CI runs" before
  a PR opens.
