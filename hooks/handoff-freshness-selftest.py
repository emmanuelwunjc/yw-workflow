#!/usr/bin/env python3
"""Self-test for handoff-freshness.py. Run it after any edit to that hook.

Each case is a temp git repo shaped one way, the hook run inside it on a Stop
event, and the warning it prints (or the silence) compared with what the
shape rule in skills/handoff/SKILL.md says should happen.

Run: ./hooks/handoff-freshness-selftest.py
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HOOK = str(pathlib.Path(__file__).with_name("handoff-freshness.py"))

SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "handoff" / "SKILL.md"
REPO_HANDOFF = SKILL.parent.parent.parent / "docs" / "HANDOFF.md"

# The block skills/handoff/SKILL.md tells every repo to paste. Pinned here so
# the skill cannot drift from it without this test noticing.
BLOCK = """# Handoff

## Start here

You are a fresh session and this file is your whole briefing. Nobody
writes you a separate prompt. Do these in order, then work.

1. Load skills `ship-loop`, `git-lanes` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Read the LAST section of this file (the most recent date). It names
   the first task, the tickets in order, and what waits on the owner.
3. Run the recount commands that section carries before trusting any
   number in it.
4. Start the first task it names. Ask the owner nothing that section
   already answers.

The handoff pass rewrites the last section (`## Next`, or the closing
section) so step 2 stays true, and leaves this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
"""

GOOD = BLOCK + "\n## 2026-09-16\n\nFirst task: x.\n"
# the phrase past the 40-line window is body text, e.g. a quote of the old rule
LATE_PREAMBLE = GOOD + "\n" * 20 + "The old rule said: written at the end of the session.\n"
NO_BLOCK = "# Handoff\n\n## 2026-09-16\n\nFirst task: x.\n"
OLD_PREAMBLE = ("# Handoff\n\n## Start here\n\nWritten at the end of a session, "
                "this file says where things stand.\n")

# (name, files to write, files to `git add`, substrings stderr must carry,
#  substrings stderr must not carry)
CASES = [
    ("clean handoff warns nothing",
     {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"], [], ["HANDOFF"]),
    ("missing Start here block",
     {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "## Start here", "skills/handoff"], []),
    ("old end-of-session preamble",
     {"docs/HANDOFF.md": OLD_PREAMBLE}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "end of a session", "skills/handoff"], []),
    ("stray handoff file tracked outside docs/",
     {"docs/HANDOFF.md": GOOD, "AGENT_HANDOFF.md": "x\n"},
     ["docs/HANDOFF.md", "AGENT_HANDOFF.md"],
     ["HANDOFF SHAPE", "AGENT_HANDOFF.md", "skills/handoff"], []),
    ("stray file matched case-insensitively",
     {"docs/HANDOFF.md": GOOD, "notes/Session-Handoff-v2.md": "x\n"},
     ["docs/HANDOFF.md", "notes/Session-Handoff-v2.md"],
     ["notes/Session-Handoff-v2.md"], []),
    ("untracked stray file is not a finding yet",
     {"docs/HANDOFF.md": GOOD, "HANDOFF.md": "x\n"}, ["docs/HANDOFF.md"],
     [], ["HANDOFF SHAPE"]),
    ("no handoff at all says nothing about shape",
     {"README.md": "x\n"}, ["README.md"], [], ["HANDOFF SHAPE"]),
    ("untracked but present handoff is still shape-checked",
     {"docs/HANDOFF.md": NO_BLOCK}, [], ["HANDOFF SHAPE"], []),
    ("preamble phrase past line 40 is body text, no warning",
     {"docs/HANDOFF.md": LATE_PREAMBLE}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
]


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def run_hook(cwd, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "SKIP_HANDOFF_CHECK"}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, HOOK], input="{}", cwd=cwd, env=env,
                          capture_output=True, text=True)


def make_repo(tmp, files, tracked):
    git(tmp, "init", "-q")
    for rel, text in files.items():
        p = pathlib.Path(tmp, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if tracked:
        git(tmp, "add", *tracked)


# Steps a branch case replays in a fresh repo:
#   ("commit", {path: text})  write, add -A, commit
#   ("branch", name)          checkout -B name
#   ("detach",)               checkout --detach, as a reviewer worktree is
#   ("origin_head", name)     make refs/remotes/origin/HEAD point at name
#   ("remote",)               a real bare origin beside the repo
#   ("git", *args)            any git command
#   ("shallow", branch)       depth-1 clone of origin at branch; later steps
#                             and the hook run in the clone
BASE = ("commit", {"README.md": "x\n"})
WORK = [("commit", {"a.py": "1\n"}), ("commit", {"b.py": "2\n"})]
LANE_WORK = [("commit", {"c.py": "3\n"}), ("commit", {"d.py": "4\n"})]
PASS = ("commit", {"docs/HANDOFF.md": GOOD})
TOUCH = ("commit", {"docs/HANDOFF.md": GOOD + "\nlane edit\n"})
OTHER_WORK = [("commit", {"e.py": "5\n"}), ("commit", {"f.py": "6\n"})]
LANE = ["HANDOFF NOTES", "## Handoff notes"]
QUIET = ["HANDOFF NOTES", "Lanes do not edit", "HANDOFF STALE"]
STALE = ["HANDOFF STALE", "handoff pass"]

# (name, first branch, steps, stderr must carry, stderr must not carry)
BRANCH_CASES = [
    ("lane with real work is told to use the PR body",
     "main", [BASE, ("branch", "feat/x"), *WORK], LANE, ["HANDOFF STALE"]),
    ("lane that edited the handoff is told lanes do not",
     "main", [BASE, ("branch", "feat/x"), WORK[0], TOUCH],
     ["HANDOFF NOTES", "Lanes do not edit"], ["HANDOFF STALE"]),
    ("handoff branch keeps the stale warning",
     "main", [BASE, ("branch", "docs/handoff-0921"), *WORK], ["HANDOFF STALE"],
     ["HANDOFF NOTES"]),
    ("trunk keeps the stale warning",
     "main", [BASE, *WORK], STALE, ["HANDOFF NOTES"]),
    ("master is trunk when origin/HEAD is unknown",
     "master", [BASE, *WORK], STALE, ["HANDOFF NOTES"]),
    ("origin/HEAD names the trunk",
     "develop", [BASE, ("origin_head", "develop"), *WORK], STALE, ["HANDOFF NOTES"]),
    ("main stays trunk when origin/HEAD names another trunk",
     "develop", [BASE, ("origin_head", "develop"), ("branch", "main"), *WORK],
     STALE, ["HANDOFF NOTES"]),
    ("docs/handoffish is a lane, the prefix carries its dash",
     "main", [BASE, ("branch", "docs/handoffish"), *WORK], LANE, ["HANDOFF STALE"]),
    ("fresh lane does not inherit trunk's handoff pass",
     "main", [BASE, *WORK, PASS, ("branch", "feat/new")], [],
     ["HANDOFF NOTES", "Lanes do not edit", "HANDOFF STALE"]),
    ("lane after trunk's handoff pass counts only its own commits",
     "main", [BASE, *WORK, PASS, ("branch", "feat/new"), *LANE_WORK],
     LANE, ["Lanes do not edit", "HANDOFF STALE"]),
    ("detached HEAD is a lane and gets no trunk message",
     "main", [BASE, ("detach",), *LANE_WORK], [],
     ["HANDOFF STALE", "handoff pass", "HANDOFF NOTES"]),
    ("detached HEAD that edited the handoff is warned",
     "main", [BASE, ("detach",), LANE_WORK[0], TOUCH],
     ["HANDOFF NOTES", "Lanes do not edit"], ["HANDOFF STALE"]),
    # Round 2: judged by the net diff against the closest trunk ref, with a
    # real origin so origin/main and main can differ.
    ("lane that reverted its handoff edit is not told to revert again",
     "main", [BASE, ("branch", "feat/x"), *WORK, TOUCH,
              ("git", "revert", "--no-edit", "HEAD")],
     LANE, ["Lanes do not edit", "HANDOFF STALE"]),
    ("reviewer detached at a pushed handoff-pass branch is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "docs/handoff-0921"), PASS,
              ("git", "push", "-q", "origin", "docs/handoff-0921"),
              ("git", "checkout", "-q", "main"),
              ("git", "branch", "-q", "-D", "docs/handoff-0921"),
              ("git", "checkout", "-q", "--detach", "origin/docs/handoff-0921")],
     [], QUIET),
    ("origin/HEAD naming a deleted branch leaves main as trunk",
     "main", [BASE, ("git", "symbolic-ref", "refs/remotes/origin/HEAD",
                     "refs/remotes/origin/master"), *WORK],
     STALE, ["HANDOFF NOTES"]),
    ("origin/HEAD naming a deleted feature branch leaves that local lane a lane",
     "main", [BASE, ("git", "symbolic-ref", "refs/remotes/origin/HEAD",
                     "refs/remotes/origin/feat/x"), ("branch", "feat/x"), *WORK],
     LANE, ["HANDOFF STALE"]),
    ("lane cut from local main ahead of origin by a handoff pass is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"), PASS,
              ("branch", "feat/new")], [], QUIET),
    ("lane cut from origin/main ahead of local main is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "up"), PASS, ("git", "push", "-q", "origin", "up:main"),
              ("git", "checkout", "-q", "main"), ("git", "branch", "-q", "-D", "up"),
              ("git", "checkout", "-q", "-b", "feat/new", "origin/main")],
     [], QUIET),
    ("shallow lane with no merge-base says nothing",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "feat/x"), LANE_WORK[0],
              ("git", "push", "-q", "origin", "feat/x"),
              ("git", "checkout", "-q", "main"), *WORK, PASS,
              ("git", "push", "-q", "origin", "main"),
              ("shallow", "feat/x"), *OTHER_WORK],
     [], QUIET),
]


def build(tmp, first, steps):
    """Replay steps in tmp/w; return the directory the hook should run in."""
    cwd = os.path.join(tmp, "w")
    origin = os.path.join(tmp, "origin.git")
    os.mkdir(cwd)
    git(cwd, "init", "-q", "-b", first)
    for step in steps:
        if step[0] == "commit":
            for rel, text in step[1].items():
                f = pathlib.Path(cwd, rel)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text)
            git(cwd, "add", "-A")
            git(cwd, "commit", "-q", "-m", "step")
        elif step[0] == "branch":
            git(cwd, "checkout", "-q", "-B", step[1])
        elif step[0] == "detach":
            git(cwd, "checkout", "-q", "--detach")
        elif step[0] == "origin_head":
            git(cwd, "update-ref", f"refs/remotes/origin/{step[1]}", "HEAD")
            git(cwd, "symbolic-ref", "refs/remotes/origin/HEAD",
                f"refs/remotes/origin/{step[1]}")
        elif step[0] == "remote":
            git(tmp, "init", "-q", "--bare", "-b", first, origin)
            git(cwd, "remote", "add", "origin", origin)
        elif step[0] == "git":
            git(cwd, *step[1:])
        elif step[0] == "shallow":
            clone = os.path.join(tmp, "shallow")
            git(tmp, "clone", "-q", "--depth", "1", "--no-single-branch",
                "-b", step[1], "file://" + origin, clone)
            cwd = clone
    return cwd


def main():
    failures = 0
    for name, files, tracked, want, forbid in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, files, tracked)
            got = run_hook(tmp)
        err = got.stderr
        missing = [w for w in want if w not in err]
        present = [f for f in forbid if f in err]
        # warn only, never block: a Stop hook that exits non-zero strands work
        if missing or present or got.returncode != 0:
            failures += 1
            print(f"FAIL {name}: exit={got.returncode} missing={missing} "
                  f"unwanted={present}\n--- stderr ---\n{err}")

    # the escape hatch silences the shape check as well as the freshness one
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        got = run_hook(tmp, {"SKIP_HANDOFF_CHECK": "1"})
    if got.stderr or got.returncode != 0:
        failures += 1
        print(f"FAIL SKIP_HANDOFF_CHECK=1 still printed (exit {got.returncode}):\n{got.stderr}")

    # the pre-existing freshness warning still fires: two commits of real work,
    # nothing touching the handoff
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"a.py": "1\n"}, ["a.py"])
        git(tmp, "commit", "-q", "-m", "one")
        pathlib.Path(tmp, "b.py").write_text("2\n")
        git(tmp, "add", "b.py")
        git(tmp, "commit", "-q", "-m", "two")
        got = run_hook(tmp)
    if "HANDOFF STALE" not in got.stderr or got.returncode != 0:
        failures += 1
        print(f"FAIL freshness warning did not fire cleanly (exit {got.returncode}):\n{got.stderr}")

    # Branch-aware freshness. Owner rule, 2026-09-21: lanes write notes in the
    # PR body's "## Handoff notes" section and never edit the handoff; a
    # docs/handoff-* branch (or trunk) is where the log gets written.
    for name, first, steps, want, forbid in BRANCH_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            got = run_hook(build(tmp, first, steps))
        missing = [w for w in want if w not in got.stderr]
        present = [f for f in forbid if f in got.stderr]
        if missing or present or got.returncode != 0:
            failures += 1
            print(f"FAIL {name}: exit={got.returncode} missing={missing} "
                  f"unwanted={present}\n--- stderr ---\n{got.stderr}")

    # the block pinned above is the block the skill tells repos to paste, and
    # the block this repo's own handoff opens with
    fenced = re.search(r"```\n(# Handoff\n.*?)```", SKILL.read_text(), re.S)
    if not fenced or fenced.group(1) != BLOCK:
        failures += 1
        print("FAIL skills/handoff/SKILL.md fenced block differs from the pinned BLOCK")
    if not REPO_HANDOFF.read_text().startswith(BLOCK):
        failures += 1
        print("FAIL docs/HANDOFF.md does not open with the pinned BLOCK")

    print("handoff-freshness: all checks pass" if not failures
          else f"handoff-freshness: {failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
