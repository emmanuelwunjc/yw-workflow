#!/usr/bin/env python3
"""Self-test for require-code-review.py's verdict matching.

The gate has now missed a real review four times, each time because its
vocabulary drifted from whatever the review flow actually writes. Every miss
cost a SKIP_REVIEW_GATE=1, and a gate you routinely disable is not a gate.
This pins what counts as a verdict and, just as importantly, what does not.

Run: python3 ~/.claude/hooks/require-code-review-selftest.py
"""

import importlib.util
import pathlib
import sys

HOOK = pathlib.Path(__file__).with_name("require-code-review.py")

# (comment body, should it satisfy the gate, what this pins)
CASES = [
    # The fresh-eye skill tells reviewers to open with exactly one word.
    ("PASS\n\n## Executive TL;DR\nAll good.", True, "fresh-eye PASS"),
    ("BLOCK\n\n## Executive TL;DR\nTwo defects.", True, "fresh-eye BLOCK"),
    ("**PASS**\n\nreviewed at abc123", True, "PASS in bold"),
    ("> BLOCK", True, "BLOCK in a quote"),
    ("## PASS", True, "PASS as a heading"),
    ("Full report below.\n\nPASS\n", True, "verdict on a later line"),
    # The vocabularies that were already known.
    ("Verdict: approve", True, "Verdict: with a space after the colon"),
    ("Verdict:approve", True, "Verdict: with no space"),
    ("APPROVE_WITH_NITS", True, "bare uppercase marker"),
    ("READY TO MERGE", True, "LOOP.md vocabulary"),
    ("Approve with nits.", True, "opener without the word verdict"),
    ("LGTM", True, "lgtm"),
    # What must NOT satisfy it. These are the whole point: PASS and BLOCK are
    # ordinary words in prose about CI, so they only count stated up front.
    ("CI has to PASS before we merge this.", False, "PASS mid-sentence"),
    ("This would BLOCK the post job.", False, "BLOCK mid-sentence"),
    ("REVIEW\n\nA human needs to decide.", False, "REVIEW is a human's call"),
    ("Review the diff carefully.", False, "Review as an imperative"),
    ("I approve of this direction.", False, "prose about approving"),
    ("blocked on #123", False, "blocked in prose"),
    ("passport control", False, "pass as a word prefix"),
    ("blockchain notes", False, "block as a word prefix"),
    ("Nice work, shipping it.", False, "plain praise"),
    ("", False, "empty body"),
]


def main() -> int:
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    failures = []
    for body, want, label in CASES:
        got = gate.has_verdict(body)
        if got != want:
            failures.append(f"  {label}: wanted {want}, got {got} for {body!r}")

    if failures:
        print(f"FAIL: {len(failures)} of {len(CASES)} cases", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"ok: {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
