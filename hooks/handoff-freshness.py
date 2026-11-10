#!/usr/bin/env python3
"""Warn when a session commits real work and never touches docs/HANDOFF.md.

CLAUDE.md Section 6 says the handoff is written down AS WORK HAPPENS. An
end-of-session handoff is composed from a compacted, lossy memory of the
session, and the reasoning that mattered (why an alternative was rejected, what
trap cost an hour) is exactly what drops out first.

Where it is written depends on the branch. The owner decided on 2026-09-21
that lanes do not edit docs/HANDOFF.md, because every concurrent lane that
appended to it hit a merge conflict there. A lane writes its notes in a
"## Handoff notes" section of its PR body. After merges, one handoff pass on a
docs/handoff-* branch copies those notes into the log.

That rule was prose. On 2026-08-05 a session merged five PRs, filed sixteen
issues and made a dozen judgment calls before anyone asked whether a handoff
existed. It did not. So this is the mechanism, per CLAUDE.md's own rule that a
broken rule gets a hook rather than a stronger sentence.

WARNS, does not block. Blocking a Stop on a documentation rule would strand
real work over a doc, and some sessions legitimately commit nothing worth
handing off (a one-line typo fix, a revert). The warning is addressed to the
model, which can act on it in the same turn.

Fires on Stop, in a git repo. What it checks depends on the branch.

Trunk is main, master, and whatever refs/remotes/origin/HEAD names if that
ref exists. A lane is any other branch, and a detached HEAD too. A lane is
judged by its net diff from a base, never by its commits one at a time, so
a lane that reverts a handoff edit is clean again:
  - named lane: base is the merge-base with the closest trunk ref (origin/
    or local, whichever is nearer HEAD)
  - detached HEAD (a reviewer worktree, by design): only commits on no
    branch and no remote are its own; base is the parent of the oldest
  - no base (a shallow clone, no trunk ref): the hook says nothing
There is no time window for lanes.

A named lane whose diff changes real files gets HANDOFF NOTES: put the notes
in the PR body's "## Handoff notes" section. A lane has edited the handoff
only when its copy differs from the copy in every trunk ref (a detached HEAD:
from its base), because the closest base can be a local trunk that diverged
from origin. A stale trunk ref, one whose merge-base with HEAD is an ancestor
of another's, is left out, since matching it would delete the newer passes.
Such a lane is told lanes do not edit it, with the exact command that
restores the file from where the work left trunk. A detached HEAD, or a
lane that changes nothing but docs, hears only that warning. The hook does not look at the PR itself, because that needs the
network and a Stop hook must work offline.

On trunk or a docs/handoff-* branch it prints HANDOFF STALE, as before, only
when ALL of these hold:
  - the last 8 hours hold MIN_COMMITS commits touching real files
  - none of those commits touched the handoff
  - the handoff was not modified in the working tree either

A second check runs on the same Stop whenever the cwd is a git repo, whatever
the commit count. The owner decided on 2026-09-16 that pointing a fresh agent
at docs/HANDOFF.md is the whole prompt. Since 2026-11-10 its Start here
block sends the session on to one open `lane` issue. That only works if the
file has the shape skills/handoff/SKILL.md describes. So it warns when:
  - docs/HANDOFF.md exists and has no "## Start here" line
  - its first 40 lines still carry the old "end of a session" preamble, which
    told the reader the file was written at close and contradicts the block
  - it has the block, and the block lacks a command line that runs
    `gh issue list --label lane` within the first 40 lines of the file. The
    block runs from the `## Start here` line to the next `## ` heading. Or a
    numbered step of the block opens with "Read the LAST section". Both are
    the block before 2026-11-10, which gave every session the same first
    task, so two sessions on two lanes both took one. Offline by design: the
    hook reads the file only.
  - a file named like a handoff (HANDOFF.md, AGENT_HANDOFF.md, *handoff*.md,
    any case) is tracked anywhere outside docs/, because two handoffs means
    the next session reads the wrong one
  - the block runs scripts/lane_claim.py and the repo top has no such file,
    so every claim would fail. The warning prints the command that copies it
    from this plugin to the repo top. A copy that git does not track warns
    too, because a fresh clone would not have it.

Escape hatch: SKIP_HANDOFF_CHECK=1 in the environment, for all of it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from handoff_touch import HANDOFF, git, touched_since
except Exception:  # a missing or broken helper: no check, and never a crash
    sys.exit(0)

# A commit touching only these is not "real work" needing a handoff entry.
DOC_SUFFIXES = (".md", ".txt", ".rst")

# Below this, a session is too small to be worth a handoff entry.
MIN_COMMITS = 2

# Branches where the handoff itself is written. Anything else is a lane.
# Fallback trunk names, used only when refs/remotes/origin/HEAD is not set.
FALLBACK_TRUNKS = ("main", "master")
HANDOFF_BRANCH_PREFIX = "docs/handoff-"
NOTES_HEADING = "## Handoff notes"
# The one stop rule of skills/handoff, word for word. The self-test checks it.
STOP_RULE = ("Write a lane body only with `scripts/lane_claim.py write` or "
             "`release`, and if it refuses, change nothing, stop, and tell "
             "the owner.")
# Step 5's rule for an exit that is no refusal, word for word. Self-tested.
EXIT_RULE = ("Any other exit, e.g. no `scripts/lane_claim.py` or a failed "
             "`gh`: change nothing, stop, and tell the owner.")

START_HERE = "## Start here"
OLD_PREAMBLE = ("end of a session", "end of the session")
PREAMBLE_LINES = 40
LANE_LIST = "gh issue list --label lane"
# The block runs this script. A repo copies it from the plugin (review round 8).
LANE_SCRIPT = "scripts/lane_claim.py"
PLUGIN_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "skills", "handoff", "lane_claim.py")
# a command line, maybe in backticks, for exactly the label `lane`
LANE_CMD = re.compile(r"^\s*`?gh issue list --label lane(?![\w-])")
ANY_LIST = re.compile(r"gh issue list --label ([^\s`']+)")
LANE_WORD = re.compile(r"--label lane(?![\w-])")
OLD_STEP = re.compile(r"^\s*\d+\.\s+read the last section", re.I)
SHAPE_HELP = ("The shape, with the block to paste, is in the yw-workflow skill "
              "skills/handoff (invoke /yw-workflow:handoff).")


def is_ancestor(a: str, b: str) -> bool:
    try:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                              capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def block_lines(lines: list[str]) -> list[tuple[int, str]]:
    """(1-based number, line) from the Start here line to the next `## `
    heading. Empty when the file has no block."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == START_HERE), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    return list(enumerate(lines[start + 1:end], start + 2))


def script_problems(top: str, lines: list[str]) -> list[str]:
    """The block runs scripts/lane_claim.py, so the repo must have it, at its
    top and tracked, since a fresh clone or a cloud routine has only what git
    tracks."""
    if not any(LANE_SCRIPT in ln for _, ln in block_lines(lines)):
        return []
    target = os.path.join(top, LANE_SCRIPT)
    if not os.path.isfile(target):
        return [f"{HANDOFF}'s `{START_HERE}` block runs {LANE_SCRIPT}, and "
                f"this repo has no {LANE_SCRIPT}, so every lane claim fails. "
                f"Copy it from the plugin and commit it:\n"
                f"  mkdir -p '{os.path.dirname(target)}' && "
                f"cp '{PLUGIN_SCRIPT}' '{target}'"]
    if not git("-C", top, "ls-files", "--", LANE_SCRIPT).strip():
        return [f"{LANE_SCRIPT} is not tracked, so a fresh clone or a cloud "
                f"routine has no copy and every lane claim there fails. "
                f"Commit it:\n  git -C '{top}' add {LANE_SCRIPT}"]
    return []


def lane_problems(lines: list[str]) -> list[str]:
    """The Start here block must list the open `lane` issues. Silent when the
    file has no block, which the missing-block warning already covers."""
    if not any(ln.strip() == START_HERE for ln in lines):
        return []
    section = block_lines(lines)
    fix = (f"Paste the current block, whose step runs `{LANE_LIST}` so each "
           f"session claims one open lane.")
    problems = []
    hits = [n for n, ln in section if LANE_CMD.match(ln)]
    if hits and hits[0] > PREAMBLE_LINES:
        why = (f"runs `{LANE_LIST}` at line {hits[0]}, past line {PREAMBLE_LINES}, "
               f"where a fresh session may stop reading.")
    elif hits:
        why = ""
    elif any(LANE_CMD.match(ln) for ln in lines):
        why = (f"has `{LANE_LIST}` in the file, but outside its `{START_HERE}` "
               f"section, so the block never tells a session to run it.")
    elif other := [m.group(1) for _, ln in section
                   for m in ANY_LIST.finditer(ln) if m.group(1) != "lane"]:
        why = f"asks for label `{other[0]}` where the lane list needs `lane`."
    elif any(LANE_WORD.search(ln) for _, ln in section):
        why = (f"says `--label lane` only in prose, with no command line that "
               f"runs `{LANE_LIST}`.")
    else:
        why = (f"has no line that runs `{LANE_LIST}`. That is the block before "
               f"2026-11-10, which gave every session one first task.")
    if why:
        problems.append(f"{HANDOFF}'s `{START_HERE}` block {why} {fix}")
    old = next((n for n, ln in section if OLD_STEP.match(ln)), None)
    if old:
        problems.append(
            f"{HANDOFF}'s `{START_HERE}` block, line {old}, opens a step with "
            f"\"Read the LAST section\". That sends every session to the LAST "
            f"section, so two sessions take the same first task. {fix}")
    return problems


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
        problems += lane_problems(lines) + script_problems(top, lines)
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


def trunks() -> set[str]:
    """main, master, and origin/HEAD's target if that ref really exists."""
    names = set(FALLBACK_TRUNKS)
    ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    if "/" in ref and git("rev-parse", "--verify", "--quiet", ref).strip():
        names.add(ref.split("/", 1)[1])
    return names


def lane_base(branch: str, names: set[str]) -> tuple[str, list[str]]:
    """The commit a lane's work is diffed from ("" when none exists), and the
    refs its handoff is compared with, closest first."""
    if not branch:
        # ponytail: a detached HEAD that merged another unpushed line is
        # judged from its oldest unpushed commit; fine for reviewer worktrees
        own = git("rev-list", "--reverse", "--topo-order", "HEAD",
                  "--not", "--branches", "--remotes").split()
        start = own[0] + "^" if own else "HEAD"
        base = git("rev-parse", "--verify", "--quiet", start).strip()
        return base, [base] if base else []
    found = []
    for ref in [f"{r}{n}" for n in sorted(names) for r in ("origin/", "")]:
        base = git("merge-base", "HEAD", ref).strip()
        if base:
            n = int(git("rev-list", "--count", f"{base}..HEAD").strip() or 0)
            found.append((n, ref, base))
    # A trunk ref whose merge-base is a strict ancestor of another's is stale
    # (e.g. a local main never pulled). Matching its handoff would delete the
    # passes the newer ref carries, so it drops out. The closest survives.
    keep = sorted((f for f in found if not any(
        o[2] != f[2] and is_ancestor(f[2], o[2]) for o in found)),
        key=lambda f: f[0])
    return (keep[0][2] if keep else ""), [ref for _, ref, _ in keep]


def lane_notes(touched_handoff: bool, real: bool, ref: str, detached: bool) -> None:
    who = "these commits" if detached else "this branch"
    edited = (f"Lanes do not edit {HANDOFF}: {who} touched it, and every "
              f"concurrent lane that does hits a merge conflict there. Move "
              f"those lines into the PR body and restore the file from where "
              f"this work left trunk:\n"
              f"  git checkout $(git merge-base HEAD {ref}) -- {HANDOFF}\n"
              f"One exception: a lane that changes the `{START_HERE}` block "
              f"itself edits {HANDOFF}, and this warning is expected there.\n\n"
              if touched_handoff else "")
    if not real:
        print(f"HANDOFF NOTES: {edited}Deliberate skip: SKIP_HANDOFF_CHECK=1\n",
              file=sys.stderr)
        return
    print(
        f"HANDOFF NOTES: this lane changes real files.\n\n"
        f"{edited}"
        f"Write what the next session needs in a `{NOTES_HEADING}` section of "
        f"this branch's PR body, now, while you still remember why: decisions "
        f"and why, what was deliberately not done, which alternative lost, what "
        f"trap cost time. No test counts, no SHAs. After merge, a handoff pass "
        f"on a {HANDOFF_BRANCH_PREFIX}* branch copies it into {HANDOFF}.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n",
        file=sys.stderr,
    )


def main() -> None:
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)

    if os.environ.get("SKIP_HANDOFF_CHECK") == "1":
        sys.exit(0)
    top = git("rev-parse", "--show-toplevel").strip()
    if not top:
        sys.exit(0)

    for problem in shape_problems(top):
        print(f"HANDOFF SHAPE: {problem}\n{SHAPE_HELP}\n"
              f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n", file=sys.stderr)

    branch = git("branch", "--show-current").strip()
    names = trunks()
    if branch not in names and not branch.startswith(HANDOFF_BRANCH_PREFIX):
        base, refs = lane_base(branch, names)
        if not base:
            sys.exit(0)
        files = git("diff", "--name-only", f"{base}..HEAD").splitlines()
        real = bool(branch) and any(not f.endswith(DOC_SUFFIXES) for f in files)
        # Edited only if the handoff differs from EVERY trunk ref. The closest
        # base can be a local trunk that diverged from origin, and a lane that
        # merged origin's handoff pass must not be told to revert it.
        touched = bool(refs) and all(
            git("diff", "--name-only", ref, "HEAD", "--", HANDOFF).strip()
            for ref in refs)
        if touched or real:
            lane_notes(touched, real, refs[0], not branch)
        sys.exit(0)

    # Trunk or a handoff branch: commits made in roughly this session.
    # Wall-clock is the only signal available here, so it is deliberately
    # generous: a false negative (no warning) is much cheaper than nagging a
    # session that did nothing.
    log = git("log", "--since=8.hours", "--pretty=%H", "--no-merges")
    shas = [s for s in log.split() if s]

    real_work = 0
    for sha in shas:
        files = [f for f in git("show", "--name-only", "--pretty=", sha).split() if f]
        if any(not f.endswith(DOC_SUFFIXES) for f in files):
            real_work += 1

    # A commit in the window that touched the handoff, or an uncommitted edit
    # to it (the session is mid-update), means it is being kept.
    if real_work < MIN_COMMITS or touched_since("8.hours"):
        sys.exit(0)

    exists = bool(git("ls-files", HANDOFF).strip())
    if exists:
        what = (f"run the handoff pass now, on a {HANDOFF_BRANCH_PREFIX}* "
                f"branch: copy the `{NOTES_HEADING}` of each PR merged since "
                f"the last pass into {HANDOFF}, and rewrite `## Next` (or the closing section) "
                f"if the first task changed")
    else:
        what = (f"{HANDOFF} does not exist yet. Create it in a handoff pass "
                f"on a {HANDOFF_BRANCH_PREFIX}* branch")

    print(
        f"HANDOFF STALE: {real_work} commits of real work this session and "
        f"nothing touched {HANDOFF}.\n\n"
        f"CLAUDE.md Section 6: the handoff is written down AS WORK HAPPENS. "
        f"Written at the end, it is composed from a compacted memory of the "
        f"session, and the reasoning that mattered is what drops out first.\n\n"
        f"So: {what}. Put each next step for open work in its `lane` issue's "
        f"`## Next`: claim the lane first with `python3 scripts/lane_claim.py "
        f"claim <N> \"<name>\"`, then write with `python3 scripts/lane_claim.py "
        f"write <N> \"<name>\" <file>` and release it. A claim that exits 1 "
        f"is a refusal: leave that lane to its holder. {EXIT_RULE} "
        f"{STOP_RULE} Then close a `lane` "
        f"issue only when a "
        f"merged PR's notes have the exact line `Lane: #<N>. finished`. A few lines per meaningful step. Judgment, not derivable "
        f"state: why a decision went the way it did, what was deliberately not "
        f"done, which alternative was rejected and why, what trap cost time. "
        f"No test counts, no SHAs, no issue counts.\n\n"
        f"Reorganize only at a real milestone, not on every touch.\n"
        f"Deliberate skip: SKIP_HANDOFF_CHECK=1\n",
        file=sys.stderr,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
