#!/usr/bin/env python3
"""Does docs/HANDOFF.md have the shape skills/handoff/SKILL.md describes?

handoff-freshness.py asks this on Stop and at SessionStart (issue #117). The
owner decided on 2026-09-16 that pointing a fresh agent at docs/HANDOFF.md is
the whole prompt, and its Start here block sends the session on to the repo's
free work check. That works only if the file has the shape the
skill describes. shape_problems() returns one string per problem:
  - docs/HANDOFF.md has no "## Start here" line
  - its Start here block does not open with the block in the plugin's
    skills/handoff/SKILL.md (issue #118). The block runs from the
    `## Start here` line to the next `## ` heading. The plugin's block is read
    from the skill's fenced block, so no copy of its text lives here. Lines
    after the plugin's last line are the repo's own and pass. So if a later
    plugin release removes its last step, an old repo keeps that step as its
    own lines and passes. An empty block warns. The warning names the first
    line that differs. A plugin skill that cannot be read or decoded gets
    one warning that the check did not run. So does a skill whose fenced
    block has no Start here block or an empty one.
  - its first 40 lines still carry the old "end of a session" preamble
  - a file named like a handoff is tracked outside docs/
  - a path in backticks in docs/HANDOFF.md or a docs/adr/*.md file does not
    exist (issue #201). A path is a token with a `/` and a file extension,
    e.g. `docs/nope.md`, read from the repo top. Skipped: fenced code, a URL
    or any token with `:`, a token with `<`, `*` or `~`, an absolute path,
    and a path under .scratch/. A `#heading` after the path is dropped.
  - a read that fails (docs/HANDOFF.md, an ADR, or git ls-files) gets a warning that names that read and says which check did
    not run (issue #145). It never warns for the problem the check would
    have looked for, and it never passes silently.

Offline by design: it reads files and git only.
"""

from __future__ import annotations

import os
import re

from handoff_touch import HANDOFF, git

START_HERE = "## Start here"
OLD_PREAMBLE = ("end of a session", "end of the session")
PREAMBLE_LINES = 40
# The old checks for `gh issue list --label lane` past line 40 and for a copy
# of scripts/lane_claim.py retired with lane issues on 2026-11-24 (#228,
# from twenty #672). An old block that still runs them fails the drift check.
SKILL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "skills", "handoff", "SKILL.md")
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


ADR_DIR = "docs/adr"
TICKED = re.compile(r"`([^`\s]+)`")
FENCE = re.compile(r"\s*(```|~~~)")
SKIP_CHARS = ":<*~"
SKIP_DIRS = (".scratch/",)


def is_path(tok: str) -> bool:
    """A repo-relative file path, by shape: e.g. `docs/HANDOFF.md`, never
    `origin/main`, `/dump` or `https://x.org/a.md`."""
    base = tok.rstrip("/").rsplit("/", 1)[-1]
    return ("/" in tok and not tok.startswith("/") and "." in base.lstrip(".")
            and not any(c in tok for c in SKIP_CHARS)
            and not tok.startswith(SKIP_DIRS))


def dead_paths(top: str, rel: str, lines: list[str]) -> list[str]:
    """One warning per backticked path in rel that is not on disk."""
    problems, fenced = [], False
    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for tok in TICKED.findall(line):
            path = tok.split("#", 1)[0]
            if is_path(path) and not os.path.exists(os.path.join(top, path)):
                problems.append(f"{rel}:{n} points to `{path}`, which does not "
                                f"exist. Fix the path or drop the pointer.")
    return problems


def adr_problems(top: str) -> list[str]:
    """dead_paths() for each docs/adr/*.md. A read that fails names it."""
    adr_dir = os.path.join(top, ADR_DIR)
    if not os.path.isdir(adr_dir):
        return []
    try:
        names = sorted(f for f in os.listdir(adr_dir) if f.endswith(".md"))
    except OSError as exc:
        return [f"cannot list {ADR_DIR} at {adr_dir} ({exc.strerror}), "
                f"so its path check did not run. Fix its permissions."]
    problems = []
    for name in names:
        rel = f"{ADR_DIR}/{name}"
        try:
            with open(os.path.join(adr_dir, name), encoding="utf-8",
                      errors="replace") as fh:
                problems += dead_paths(top, rel, fh.read().splitlines())
        except OSError as exc:
            problems.append(f"cannot read {rel} at {os.path.join(adr_dir, name)} "
                            f"({exc.strerror}), so its path check did not run. "
                            f"Fix its permissions.")
    return problems


def shape_problems(top: str) -> list[str]:
    """Each string is one warning; empty means the handoff has the right shape."""
    problems = []
    lines = None
    handoff = os.path.join(top, HANDOFF)
    if os.path.isfile(handoff):
        try:
            with open(handoff, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            problems.append(f"cannot read {HANDOFF} at {handoff} ({exc.strerror}), "
                            f"so its shape checks did not run. Fix its permissions.")
    if lines is not None:
        if not any(ln.strip() == START_HERE for ln in lines):
            problems.append(
                f"{HANDOFF} has no `{START_HERE}` line. A fresh session starts from "
                f"that block, which sends it to the free work check, so paste "
                f"the Start here block at the top, above everything else.")
        problems += drift_problems(lines)
        head = "\n".join(lines[:PREAMBLE_LINES]).lower()
        hit = next((p for p in OLD_PREAMBLE if p in head), None)
        if hit:
            problems.append(
                f"{HANDOFF} still says \"{hit}\" in its first {PREAMBLE_LINES} "
                f"lines. That preamble told the reader the file was written at "
                f"close; the file is written as work happens. Delete it.")
        problems += dead_paths(top, HANDOFF, lines)
    problems += adr_problems(top)
    try:
        tracked = git("-C", top, "ls-files", "-z", check=True).split("\0")
    except RuntimeError as exc:
        return problems + [f"git cannot list the tracked files, so the check for "
                           f"handoff files outside docs/ did not run: {exc}"]
    stray = [f for f in tracked
             if "handoff" in os.path.basename(f).lower()
             and f.lower().endswith(".md")
             and not f.startswith("docs/")]
    if stray:
        problems.append(
            f"handoff-named files tracked outside docs/: {', '.join(sorted(stray))}. "
            f"The one handoff lives at {HANDOFF}. Fold these into it and delete them.")
    return problems
