#!/usr/bin/env python3
"""Does docs/HANDOFF.md have the shape skills/handoff/SKILL.md describes?

handoff-freshness.py asks this on Stop and at SessionStart (issue #117). The
owner decided on 2026-09-16 that pointing a fresh agent at docs/HANDOFF.md is
the whole prompt, and since 2026-11-10 its Start here block sends the session
on to one open `lane` issue. That works only if the file has the shape the
skill describes. shape_problems() returns one string per problem:
  - docs/HANDOFF.md has no "## Start here" line
  - its Start here block does not open with the block in the plugin's
    skills/handoff/SKILL.md (issue #118). The block runs from the
    `## Start here` line to the next `## ` heading. The plugin's block is read
    from the skill's fenced block, so no copy of its text lives here. Lines
    after the plugin's last line are the repo's own and pass. So if a later
    plugin release removes its last step, an old repo keeps that step as its
    own lines and passes. An empty block warns. The warning names the first
    line that differs. A plugin skill that cannot be read or decoded, or
    whose fenced block has no Start here block or an empty one, gets one
    warning that the check did not run.
  - the block runs `gh issue list --label lane` past line 40 of the file,
    where a fresh session may stop reading (the block is pasted too low)
  - its first 40 lines still carry the old "end of a session" preamble
  - a file named like a handoff is tracked outside docs/
  - the block runs scripts/lane_claim.py and the repo top has no such file,
    or git does not track it, or it differs from the plugin's
    skills/handoff/lane_claim.py (issue #118). Each warning prints the fix.
    A plugin script that cannot be read gets one warning that the check did
    not run. A repo copy that cannot be read gets its own warning.

Offline by design: it reads files and git only.
"""

from __future__ import annotations

import os
import re

from handoff_touch import HANDOFF, git

START_HERE = "## Start here"
OLD_PREAMBLE = ("end of a session", "end of the session")
PREAMBLE_LINES = 40
LANE_LIST = "gh issue list --label lane"
# a command line, maybe in backticks, for exactly the label `lane`
LANE_CMD = re.compile(r"^\s*`?gh issue list --label lane(?![\w-])")
# The block runs this script. A repo copies it from the plugin (review round 8).
LANE_SCRIPT = "scripts/lane_claim.py"
SKILL_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "skills", "handoff")
PLUGIN_SCRIPT = os.path.join(SKILL_DIR, "lane_claim.py")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
# the block the skill tells every repo to paste, in its one fenced block
FENCED = re.compile(r"```\n(# Handoff\n.*?)```", re.S)


def block_lines(lines: list[str]) -> list[tuple[int, str]]:
    """(1-based number, line) from the Start here line to the next `## `
    heading. Empty when the file has no block."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == START_HERE), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    return list(enumerate(lines[start + 1:end], start + 2))


def trimmed(block: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Trailing spaces off each line, trailing blank lines off the block."""
    out = [(n, ln.rstrip()) for n, ln in block]
    while out and not out[-1][1]:
        out.pop()
    return out


def plugin_block() -> list[str] | None:
    """The plugin's current block, read from SKILL.md. None when the file
    cannot be read or decoded, or its fence has no block, or an empty one:
    comparing with nothing would pass every repo block."""
    try:
        with open(SKILL, encoding="utf-8") as fh:
            m = FENCED.search(fh.read())
    except (OSError, ValueError):
        return None
    block = [ln for _, ln in trimmed(block_lines(m.group(1).splitlines()))] if m else []
    return block or None


def drift_problems(lines: list[str]) -> list[str]:
    """The repo's block must open with the plugin's, line for line. Lines after
    the plugin's last line are the repo's own, e.g. what the repo is."""
    if not any(ln.strip() == START_HERE for ln in lines):
        return []  # shape_problems already warns that the line is missing
    want = plugin_block()
    if want is None:
        return [f"cannot read the plugin's `{START_HERE}` block at {SKILL}, "
                f"so the drift check did not run."]
    have = trimmed(block_lines(lines))
    end = "(the block ends here)"
    if not have:  # trimmed() drops blank lines at the end, so blank is empty
        first = next((ln for ln in want if ln), "")
        return [f"{HANDOFF}'s `{START_HERE}` block differs from the plugin's: "
                f"it is empty. Paste the current block from {SKILL}.\n"
                f"  this file: {end}\n  plugin:    {first}"]
    for i, theirs in enumerate(want):
        mine = have[i][1] if i < len(have) else end
        if mine != theirs:
            n = have[i][0] if i < len(have) else have[-1][0] + 1
            return [f"{HANDOFF}'s `{START_HERE}` block differs from the plugin's, "
                    f"first at line {n}. Paste the current block from {SKILL}.\n"
                    f"  this file: {mine}\n  plugin:    {theirs}"]
    return []


def late_problems(lines: list[str]) -> list[str]:
    """The block's lane list must sit where a fresh session still reads."""
    hit = next((n for n, ln in block_lines(lines) if LANE_CMD.match(ln)), 0)
    if hit <= PREAMBLE_LINES:
        return []
    return [f"{HANDOFF}'s `{START_HERE}` block runs `{LANE_LIST}` at line {hit}, "
            f"past line {PREAMBLE_LINES}, where a fresh session may stop reading. "
            f"Move the block to the top of the file."]


def read_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def script_problems(top: str, lines: list[str]) -> list[str]:
    """The block runs scripts/lane_claim.py, so the repo must have the
    plugin's current copy, at its top and tracked, since a fresh clone or a
    cloud routine has only what git tracks."""
    if not any(LANE_SCRIPT in ln for _, ln in block_lines(lines)):
        return []
    target = os.path.join(top, LANE_SCRIPT)
    copy = (f"  mkdir -p '{os.path.dirname(target)}' && "
            f"cp '{PLUGIN_SCRIPT}' '{target}'")
    if not os.path.isfile(target):
        return [f"{HANDOFF}'s `{START_HERE}` block runs {LANE_SCRIPT}, and "
                f"this repo has no {LANE_SCRIPT}, so every lane claim fails. "
                f"Copy it from the plugin and commit it:\n{copy}"]
    if not git("-C", top, "ls-files", "--", LANE_SCRIPT).strip():
        return [f"{LANE_SCRIPT} is not tracked, so a fresh clone or a cloud "
                f"routine has no copy and every lane claim there fails. "
                f"Commit it:\n  git -C '{top}' add {LANE_SCRIPT}"]
    plugin = read_bytes(PLUGIN_SCRIPT)
    if plugin is None:
        return [f"cannot read the plugin's {LANE_SCRIPT} at {PLUGIN_SCRIPT}, "
                f"so the copy check did not run."]
    mine = read_bytes(target)
    if mine is None:
        return [f"cannot read {LANE_SCRIPT} in this repo at {target}, so the "
                f"copy check did not run and a lane claim may fail. Fix its "
                f"permissions, or copy the current one:\n{copy}"]
    if mine != plugin:
        return [f"{LANE_SCRIPT} differs from the plugin's copy, so a fix to the "
                f"script has not reached this repo. Copy the current one and "
                f"commit it:\n{copy}"]
    return []


def shape_problems(top: str) -> list[str]:
    """Each string is one warning; empty means the handoff has the right shape."""
    problems = []
    handoff = os.path.join(top, HANDOFF)
    if os.path.isfile(handoff):
        try:
            with open(handoff, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
        if not any(ln.strip() == START_HERE for ln in lines):
            problems.append(
                f"{HANDOFF} has no `{START_HERE}` line. A fresh session starts from "
                f"that block, which sends it to one open `lane` issue, so paste "
                f"the Start here block at the top, above everything else.")
        problems += (drift_problems(lines) + late_problems(lines)
                     + script_problems(top, lines))
        head = "\n".join(lines[:PREAMBLE_LINES]).lower()
        hit = next((p for p in OLD_PREAMBLE if p in head), None)
        if hit:
            problems.append(
                f"{HANDOFF} still says \"{hit}\" in its first {PREAMBLE_LINES} "
                f"lines. That preamble told the reader the file was written at "
                f"close; the file is written as work happens. Delete it.")
    tracked = git("-C", top, "ls-files", "-z").split("\0")
    stray = [f for f in tracked
             if "handoff" in os.path.basename(f).lower()
             and f.lower().endswith(".md")
             and not f.startswith("docs/")]
    if stray:
        problems.append(
            f"handoff-named files tracked outside docs/: {', '.join(sorted(stray))}. "
            f"The one handoff lives at {HANDOFF}. Fold these into it and delete them.")
    return problems
