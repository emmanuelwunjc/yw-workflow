#!/usr/bin/env python3
"""Block `gh pr merge` when nothing has code-reviewed the PR.

CLAUDE.md Section 2 step 3 requires the code-review skill on non-trivial
diffs before anything is called done. On 2026-08-04 that step was skipped on
22 of 26 PRs merged in one session. Nothing stopped it, because the rule was
prose. The four PRs that *were* reviewed each produced a real finding,
including a fix whose covering test did not exist while CI stayed green.

So this is the mechanism, per CLAUDE.md's own rule that a broken rule gets a
hook rather than a stronger sentence.

A PR counts as reviewed when either:
  - it has a GitHub review (APPROVED or CHANGES_REQUESTED), or
  - a comment on it carries a review verdict marker.

Trivial diffs are exempt: a PR touching no code file, or under the line
threshold, merges without ceremony. The point is to stop unreviewed
*behaviour* changes, not to add friction to a typo fix.

Escape hatch: set SKIP_REVIEW_GATE=1 for the single command. That is
deliberate and visible, unlike forgetting.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# A verdict marker any of our review flows emit.
#
# Two patterns, not one alternation, and deliberately so.
#
# The bare uppercase markers stay case-SENSITIVE. Lower-casing them would let
# the word "blocked" in ordinary prose ("blocked on #123") satisfy the gate,
# which is a false pass on the exact check that is meant to be hard to pass by
# accident.
#
# `verdict:` is case-insensitive and carries NO trailing `\b`. The original
# pattern ended `|Verdict:)\b`, which never matched: `\b` needs a word
# character on one side, and a colon followed by a space has non-word
# characters on both. So it matched `Verdict:approve` and not
# `Verdict: approve`, and every review writes the second. The gate was
# unsatisfiable by its own documented marker, and the only way past it was
# SKIP_REVIEW_GATE=1. A safety gate that can only be passed by disabling it
# teaches you to disable it.
# Found 2026-08-05 merging synthweave #181, which had a posted review verdict.
# The third pattern is anchored to the start of a line, on purpose. Reviews
# very often open "**Approve with nits.**" and never write the word "verdict",
# so matching only `Verdict:` still reads a real review as no review. But
# matching "approve" anywhere would pass on "I approve of this direction",
# which is a false pass on the check that most needs to resist one. A verdict
# is stated up front; prose about approving is not. Leading `*`, `#` and `>`
# are skipped so bold, headings and quotes still count.
#
# `READY TO MERGE`/`DO-NOT-MERGE` were missing entirely until 2026-08-28, even
# though they are LOOP.md's and tools/loop_gate.py's own verdict words in
# EdSim (and any repo that adopts the same LOOP.md convention) and this
# session's real reviewer comments used them verbatim. A same-shape gap to the
# `Verdict:` one above: this hook has its own separate vocabulary from the
# repo's `loop_gate.py`, so a comment that satisfies one satisfies neither
# automatically, and the only way past it was SKIP_REVIEW_GATE=1 again. Found
# 2026-08-28 merging EdSim #366 and #368, both with a posted, real,
# independent-review-backed verdict this hook still could not see.
VERDICT_MARKERS = re.compile(
    r"\b(APPROVE|APPROVE_WITH_NITS|CHANGES_MADE|BLOCKED|READY TO MERGE|DO-NOT-MERGE)\b"
)
VERDICT_LINE = re.compile(r"verdict\s*:", re.IGNORECASE)
#
# `pass` and `block` were the fourth instance of the same vocabulary gap, found
# 2026-09-02 merging office-weather-bot #1 and #3. The fresh-eye skill tells its
# reviewers to open with exactly one word, `PASS`, `BLOCK` or `REVIEW`, and this
# hook knew none of them. Nine independent adversarial review rounds across two
# PRs, every verdict posted as a comment, and the gate still read them as no
# review, so the only way to merge was SKIP_REVIEW_GATE=1 three times in one
# session. A gate that a real review cannot satisfy trains you to disable it.
#
# They go in the line-anchored pattern, not the bare-marker one, for the reason
# that pattern already exists: `PASS` and `BLOCK` appear in ordinary prose about
# CI ("the check must PASS", "this will BLOCK the post") far too often to accept
# anywhere in a body. A verdict is stated up front.
#
# `review` is deliberately NOT here. In that skill it means "a human has to
# decide", which is the one verdict that must not satisfy a merge gate on its
# own, and "Review the diff" is a common way to open a comment.
VERDICT_OPENER = re.compile(
    r"^[\s*#>_]*(approve|approved|approve with nits|lgtm|request changes|"
    r"requesting changes|changes requested|blocking|ready to merge|do-not-merge|"
    r"pass|block)\b",
    re.IGNORECASE | re.MULTILINE,
)


def has_verdict(body: str) -> bool:
    return bool(
        VERDICT_MARKERS.search(body)
        or VERDICT_LINE.search(body)
        or VERDICT_OPENER.search(body)
    )
# Files whose change is behaviour, not prose.
CODE_SUFFIXES = (".py", ".yml", ".yaml", ".toml", ".cfg", ".sh", ".ts", ".js")
# Below this, a code diff is treated as trivial.
TRIVIAL_LINES = 25


def gh(*args: str) -> str:
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=25
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def deny(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (event.get("tool_input") or {}).get("command", "")

    m = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", cmd)
    if not m:
        sys.exit(0)
    if os.environ.get("SKIP_REVIEW_GATE") == "1" or "SKIP_REVIEW_GATE=1" in cmd:
        sys.exit(0)

    pr = m.group(1)

    # --- Gate 1: every check must be passing -------------------------------
    # Added 2026-08-04. The review gate below is not enough on its own: a PR
    # can be reviewed and still be red, or still have a check pending that
    # nobody waited for. "100% green" means zero failing AND zero pending, not
    # "green apart from the one we know about".
    #
    # This runs BEFORE the triviality check on purpose. A one-line change that
    # turns CI red is exactly the merge worth stopping, and skipping the gate
    # for small diffs would let the most common red slip through.
    checks = gh("pr", "checks", pr, "--json", "name,state",
                "--jq", '.[] | "\\(.state) \\(.name)"')
    if checks.strip():
        bad = []
        for line in checks.strip().splitlines():
            state, _, name = line.partition(" ")
            if state.upper() not in ("SUCCESS", "SKIPPED", "NEUTRAL"):
                bad.append(f"  {state.lower():<12} {name}")
        if bad:
            deny(
                f"BLOCKED: PR #{pr} is not 100% green.\n\n"
                + "\n".join(bad)
                + "\n\nA pending check is not a passing check: wait for it "
                "rather than merging past it.\n"
                f"  gh pr checks {pr} --watch\n\n"
                f"Deliberate override: SKIP_REVIEW_GATE=1 gh pr merge {pr} ...\n"
            )

    # --- Gate 2: a code review must have run -------------------------------
    files = gh("pr", "view", pr, "--json", "files",
               "--jq", ".files[] | \"\\(.path) \\(.additions) \\(.deletions)\"")
    if not files.strip():
        sys.exit(0)  # cannot tell; do not block on a broken lookup

    code_lines = 0
    for line in files.strip().splitlines():
        parts = line.rsplit(" ", 2)
        if len(parts) != 3:
            continue
        path, add, dele = parts
        if path.endswith(CODE_SUFFIXES):
            try:
                code_lines += int(add) + int(dele)
            except ValueError:
                pass

    if code_lines == 0:
        sys.exit(0)  # docs or data only
    if code_lines < TRIVIAL_LINES:
        sys.exit(0)  # trivial code change

    states = gh("pr", "view", pr, "--json", "reviews",
                "--jq", "[.reviews[].state] | join(\" \")")
    if "APPROVED" in states or "CHANGES_REQUESTED" in states:
        sys.exit(0)

    body = gh("pr", "view", pr, "--json", "comments", "--jq", ".comments[].body")
    if has_verdict(body or ""):
        sys.exit(0)

    deny(
        f"BLOCKED: PR #{pr} changes {code_lines} lines of code and nothing has "
        f"reviewed it.\n\n"
        f"CLAUDE.md Section 2 step 3: run the code-review skill on non-trivial "
        f"diffs before calling anything done. Green CI proves the tests pass. "
        f"It does not prove the change matches its issue, and it does not catch "
        f"a bad design decision.\n\n"
        f"Do one of:\n"
        f"  1. Run an independent code-review on #{pr}, post the verdict as a PR "
        f"comment, then merge.\n"
        f"  2. Approve it on GitHub if a human read it.\n"
        f"  3. SKIP_REVIEW_GATE=1 gh pr merge {pr} ...  (deliberate, and it shows)\n"
    )


if __name__ == "__main__":
    main()
