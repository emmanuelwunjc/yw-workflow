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
import shutil
import tempfile
import time

HOOK = str(pathlib.Path(__file__).with_name("handoff-freshness.py"))

SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "handoff" / "SKILL.md"
REPO_HANDOFF = SKILL.parent.parent.parent / "docs" / "HANDOFF.md"

# The block skills/handoff/SKILL.md tells every repo to paste. Pinned here so
# the skill cannot drift from it without this test noticing.
BLOCK = r"""# Handoff

## Start here

You are a fresh session. This file and the open `lane` issues are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-lanes` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Check that the repo has the label. This prints `lane` if it does:
   `gh label list --search lane --json name --jq '.[] | select(.name == "lane") | .name'`
   It prints nothing: this repo has no lane label yet. Read the LAST
   section of this file for the tasks, and go to step 6.
3. List the open lanes. Free lanes come first, lowest issue number
   first. Held lanes follow, oldest time first:

   gh issue list --label lane --state open --limit 100 --json number,title,body --jq '(now | strftime("%Y-%m-%dT%H:%MZ")) as $now | map(((.body // "") | split("\n") | first // "" | rtrimstr("\r")) as $h | {n: .number, t: .title, h: $h, s: (($h | capture("^Held by: (?<name>.+), since (?<time>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z)$") | select(.name != "nobody" and .time <= $now) | .time) // null)}) | sort_by(if .s then [1, .s, .n] else [0, .n] end) | .[] | "#\(.n) \(.t) | \(if .s or .h == "Held by: nobody" then .h else "Held by: (malformed)" end)"'

   No lines: no lane is open. Read the LAST section of this file for the
   tasks, and go to step 6. 100 lines: raise `--limit`, list again.
4. Pick a lane. A lane is free when its `Held by:` line says nobody or
   is malformed, or its time is over 24 hours old and ListAgents does
   not show that session live. Else it is held. The owner named a lane:
   take it, and if it is held, tell the owner and stop. Else, one free
   lane: take it. More than one: ask the owner with one AskUserQuestion,
   one option per free lane in list order, the first recommended. No
   owner present (a cloud routine, a headless run): take the first free
   lane. No free lane: tell the owner, and stop.
5. Claim it, after any answer from the owner:
   `python3 scripts/lane_claim.py claim <N> "<name>"`. Add
   `--holder-not-live` only when step 4 found the lane free by its
   24-hour rule. Exit 0: you hold the lane. Exit 1: it says why. Change
   nothing. The owner named this lane: tell the owner and stop. Else go
   back to step 4. Any other exit, e.g. no `scripts/lane_claim.py` or a
   failed `gh`: change nothing, stop, and tell the owner. <name> is your
   session name as ListAgents prints it. With no ListAgents, use your
   harness and worktree, e.g. `laptop:04-handoff-lanes`. A cloud routine
   adds its run start, e.g. `cloud routine nightly 2026-11-10T06:17Z`.
6. Read the lane issue's `## Next`, or with no lane the LAST section.
   Read the recent sections of this file for traps. Run the recount
   commands before trusting any number. A task with no mark is `parallel`
   unless it names another task it waits for. Start every `parallel`
   task it names in the same turn, each in its own worktree (`git-lanes`), two
   to four at once. Start any more as earlier tasks merge or stop. Start an
   `after` task when its dependency merges. If you stop before that,
   leave it in `## Next` with its `after` mark for the next session. Ask
   the owner nothing it already answers.

Write a lane body only with `scripts/lane_claim.py write` or `release`,
and if it refuses, change nothing, stop, and tell the owner. Update
`## Next` with `python3 scripts/lane_claim.py write <N> "<name>" <file>`,
and free the lane with `python3 scripts/lane_claim.py release <N> "<name>"`
when you stop. Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
"""

# The block before 2026-11-10: one first task for every session, so two
# sessions on two lanes both took the same one. It must warn.
OLD_BLOCK = """# Handoff

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

Whoever closes a session rewrites the last section so step 2 stays true,
and leaves this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
"""

GOOD = BLOCK + "\n## 2026-09-16\n\nFirst task: x.\n"
# The block runs this script, so a repo without it gets a copy command
# naming the plugin's file (review round 8).
SCRIPT = "scripts/lane_claim.py"
PLUGIN_SCRIPT = SKILL.parent / "lane_claim.py"
NO_SCRIPT = f"has no {SCRIPT}"
# Step 5 treats exit 1 and any other exit apart, so a missing script or a
# failed `gh` stops the session instead of walking every lane (round 8).
EXIT_RULE = ("Any other exit, e.g. no `scripts/lane_claim.py` or a failed "
             "`gh`: change nothing, stop, and tell the owner.")
# the phrase past the 40-line window is body text, e.g. a quote of the old rule
LATE_PREAMBLE = GOOD + "\n" * 20 + "The old rule said: written at the end of the session.\n"
NO_BLOCK = "# Handoff\n\n## 2026-09-16\n\nFirst task: x.\n"
# Each wrong Start here block below must warn, each with its own text.
CMD = "   gh issue list --label lane --state open"
CMD_LINE = BLOCK.splitlines().index(next(l for l in BLOCK.splitlines() if l.startswith(CMD))) + 1
assert CMD_LINE < 40, "the pinned block's lane list must sit inside the 40-line window"
TAIL = "\n## 2026-09-16\n\nFirst task: x.\n"
OTHER_LABEL = {lbl: GOOD.replace(CMD, CMD.replace("--label lane", "--label " + lbl), 1)
               for lbl in ("lanes", "bug")}
PROSE_ONLY = GOOD.replace(CMD, "   We stopped using `--label lane` here.", 1)
PROSE_CMD = GOOD.replace(CMD, "   We used to run `gh issue list --label lane` here.", 1)
STEP2 = "2. Check that the repo has the label."
LAST_STEP = GOOD.replace(STEP2, "2. Read the LAST section. It names the first task.", 1)
OUTSIDE = ("# Handoff\n\ngh issue list --label lane --state open\n" + "\n" * 41
           + OLD_BLOCK.split("# Handoff\n", 1)[1] + TAIL)
# the command in the dated section under the block, still inside 40 lines
BELOW = OLD_BLOCK + "\n## 2026-09-16\n\ngh issue list --label lane\n"
assert len(BELOW.splitlines()) <= 40
LANE_XYZ = GOOD.replace(CMD, CMD.replace("--label lane", "--label lane-xyz"), 1)
SUB_HEADING = GOOD.replace("1. Load skills", "### Note\n\n1. Load skills", 1)
TICKED = GOOD.replace(CMD, "   `" + CMD.strip() + "`", 1)
SECOND_LATE = BLOCK.replace("Judgment and reasoning only.",
                            "\n" * 30 + CMD + "\n\nJudgment and reasoning only.", 1) + TAIL
assert SECOND_LATE.splitlines().index(next(l for l in reversed(SECOND_LATE.splitlines())
                                           if l.startswith(CMD))) >= 40
H3_START = GOOD.replace("## Start here\n", "### Start here\n", 1)
LATER_START = GOOD.replace("## Start here\n", "## Start here later\n", 1)
# "1. Read the LAST section" in a dated section below the block is history
OLD_STEP_BELOW = GOOD + "\n## 2026-09-17\n\n1. Read the LAST section of this file.\n"
# a two-digit step that sends every session to the LAST section
STEP12 = GOOD.replace("2. Check that the repo has the label.",
                      "12. Read the LAST section. It names the first task.", 1)
# an indented step inside the block still sends sessions to the LAST section
INDENTED_STEP = GOOD.replace("1. Load skills", "   1. Read the LAST section. It names the first task.\n1. Load skills", 1)
LATER_ONLY = "# Handoff\n\n## Start here later\n\nFirst task: x.\n"
# pad inside the section so the lane list sits exactly at line 40, then 41
AT = {n: BLOCK.replace("## Start here\n", "## Start here\n" + "\n" * (n - CMD_LINE), 1) + TAIL
      for n in (40, 41)}
OLD_SINGLE_TASK = OLD_BLOCK + "\n## 2026-09-16\n\nFirst task: x.\n"
# the lane command only past the 40-line window is body text, not the block
LATE_LANE = (OLD_BLOCK + "\n" * 40 + "gh issue list --label lane\n")
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
    ("old single-first-task Start here block",
     {"docs/HANDOFF.md": OLD_SINGLE_TASK}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "has no line that runs", "skills/handoff"], []),
    ("lane command past line 40 does not count as the block",
     {"docs/HANDOFF.md": LATE_LANE}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "past line 40"], []),
    ("lane list for label lanes warns",
     {"docs/HANDOFF.md": OTHER_LABEL["lanes"]}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "asks for label `lanes`"], []),
    ("lane list for label bug warns",
     {"docs/HANDOFF.md": OTHER_LABEL["bug"]}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "asks for label `bug`"], []),
    ("--label lane only in prose warns",
     {"docs/HANDOFF.md": PROSE_ONLY}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "only in prose"], []),
    ("the whole lane command quoted mid-sentence is still prose",
     {"docs/HANDOFF.md": PROSE_CMD}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "only in prose"], ["asks for label"]),
    ("a step that opens with Read the LAST section warns",
     {"docs/HANDOFF.md": LAST_STEP}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "sends every session to the LAST section"], []),
    ("lane list above a Start here at line 45 warns",
     {"docs/HANDOFF.md": OUTSIDE}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "outside its `## Start here` section"], []),
    ("lane list under the next heading is outside the block",
     {"docs/HANDOFF.md": BELOW}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "outside its `## Start here` section"], []),
    ("lane list for label lane-xyz warns and names it",
     {"docs/HANDOFF.md": LANE_XYZ}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "asks for label `lane-xyz`"], []),
    ("a ### heading inside the block does not end it",
     {"docs/HANDOFF.md": SUB_HEADING}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("a command line in backticks counts",
     {"docs/HANDOFF.md": TICKED}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("the first command line decides, a second one past line 40 is fine",
     {"docs/HANDOFF.md": SECOND_LATE}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("### Start here is no Start here line",
     {"docs/HANDOFF.md": H3_START}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "has no `## Start here` line"], []),
    ("## Start here later is no Start here line",
     {"docs/HANDOFF.md": LATER_START}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "has no `## Start here` line"], []),
    ("a LAST-section step below the block is no warning",
     {"docs/HANDOFF.md": OLD_STEP_BELOW}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("## Start here later alone gets only the missing-block warning",
     {"docs/HANDOFF.md": LATER_ONLY}, ["docs/HANDOFF.md"],
     ["has no `## Start here` line"], ["--label lane"]),
    ("a two-digit step that opens with Read the LAST section warns",
     {"docs/HANDOFF.md": STEP12}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "sends every session to the LAST section"], []),
    ("an indented step that opens with Read the LAST section warns",
     {"docs/HANDOFF.md": INDENTED_STEP}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "sends every session to the LAST section"], []),
    ("lane list at line 40 is inside the window",
     {"docs/HANDOFF.md": AT[40]}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("lane list at line 41 is past the window",
     {"docs/HANDOFF.md": AT[41]}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", "at line 41, past line 40"], []),
    ("missing block gets one warning, the lane one stays quiet",
     {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"],
     ["## Start here"], ["--label lane"]),
    ("a block that runs the script, in a repo without it, warns with the copy",
     {"docs/HANDOFF.md": GOOD, SCRIPT: None}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", NO_SCRIPT, f"cp '{PLUGIN_SCRIPT}' '"], []),
    ("a copy git does not track warns",
     {"docs/HANDOFF.md": GOOD, SCRIPT: "x\n"}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", f"{SCRIPT} is not tracked"], [NO_SCRIPT]),
    ("a repo with the script gets no copy warning",
     {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"], [], [NO_SCRIPT]),
    ("the script named only below the block needs no copy",
     {"docs/HANDOFF.md": OLD_BLOCK + f"\n## 2026-09-17\n\nRun `python3 {SCRIPT}`.\n",
      SCRIPT: None}, ["docs/HANDOFF.md"], ["HANDOFF SHAPE"], [NO_SCRIPT]),
    ("preamble phrase past line 40 is body text, no warning",
     {"docs/HANDOFF.md": LATE_PREAMBLE}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
]


# Step 3's jq, run on sample lanes. The expected lines are the whole rule:
# free (nobody or malformed) by issue number, then held by oldest since.
LANES = [
    (9, "held late", "Held by: alpha, since 2026-11-10T09:00Z\n\n## Next\n1. a"),
    (3, "nobody", "Held by: nobody\n\n## Next\n1. b"),
    (8, "seconds", "Held by: beta, since 2026-11-10T09:00:30Z\n## Next"),
    (7, "future", "Held by: gamma, since 2099-01-01T00:00Z\n## Next"),
    (6, "nobody with since", "Held by: nobody, since 2026-11-01T00:00Z\n## Next"),
    (5, "no line", "## Next\nHeld by: delta, since 2026-11-01T00:00Z"),
    (4, "empty body", ""),
    (2, "crlf held", "Held by: eta, since 2026-11-08T05:00Z\r\n\r\n## Next"),
    (11, "same since, higher", "Held by: theta, since 2026-11-09T12:00Z\n## Next"),
    (10, "same since, lower", "Held by: iota, since 2026-11-09T12:00Z\n## Next"),
    (13, "text after the time", "Held by: a, since 2026-11-10T08:00Z (back at 3)"),
    (14, "quoted", "> Held by: a, since 2026-11-10T08:00Z"),
    (15, "empty name", "Held by: , since 2026-11-10T08:00Z"),
    (16, "one minute ahead", "Held by: b, since 2026-11-10T09:01Z"),
]
# "now" for the fixtures. Lane 9's time equals it, so `<=` must hold.
FIXED_NOW = "2026-11-10T09:00Z"
NOW_PREFIX = '(now | strftime("%Y-%m-%dT%H:%MZ")) as $now | ' 
LANE_ORDER = """#3 nobody | Held by: nobody
#4 empty body | Held by: (malformed)
#5 no line | Held by: (malformed)
#6 nobody with since | Held by: (malformed)
#7 future | Held by: (malformed)
#8 seconds | Held by: (malformed)
#13 text after the time | Held by: (malformed)
#14 quoted | Held by: (malformed)
#15 empty name | Held by: (malformed)
#16 one minute ahead | Held by: (malformed)
#2 crlf held | Held by: eta, since 2026-11-08T05:00Z
#10 same since, lower | Held by: iota, since 2026-11-09T12:00Z
#11 same since, higher | Held by: theta, since 2026-11-09T12:00Z
#9 held late | Held by: alpha, since 2026-11-10T09:00Z
"""


def check_lane_jq():
    """0 on pass, 1 on a wrong order or label, or when jq is missing."""
    import json
    if not shutil.which("jq"):
        print("FAIL step 3 jq: no jq on PATH. The block pins a jq program that "
              "must be run. Install jq (e.g. `brew install jq`) and run again.")
        return 1
    line = next(l for l in BLOCK.splitlines() if l.startswith(CMD))
    program = re.search(r"--jq '(.*)'$", line).group(1)
    if not program.startswith(NOW_PREFIX):
        print(f"FAIL step 3 jq does not start with {NOW_PREFIX!r}")
        return 1
    data = json.dumps([{"number": n, "title": t, "body": b} for n, t, b in LANES])
    got = subprocess.run(["jq", "-r", "--arg", "now", FIXED_NOW,
                          program[len(NOW_PREFIX):]],
                         input=data, capture_output=True, text=True)
    if got.returncode != 0 or got.stdout != LANE_ORDER:
        print(f"FAIL step 3 jq printed (exit {got.returncode}):\n{got.stdout}{got.stderr}")
        return 1
    return 0


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def run_hook(cwd, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "SKIP_HANDOFF_CHECK"}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, HOOK], input="{}", cwd=cwd, env=env,
                          capture_output=True, text=True)


def make_repo(tmp, files, tracked):
    """Every repo has the script the block runs, tracked, unless files names
    it: None leaves it out, text writes it untracked unless listed."""
    git(tmp, "init", "-q")
    if SCRIPT not in files:
        files, tracked = {SCRIPT: "x\n", **files}, [SCRIPT, *tracked]
    for rel, text in files.items():
        if text is None:
            continue
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
NOTES_ASK = "section of this branch's PR body"
# Round 4: two passes land on origin/main while the local trunk stays stale.
H1 = GOOD + "\n## pass 1\n"
H2 = H1 + "\n## pass 2\n"
TRUNK_BASE = ("commit", {"docs/HANDOFF.md": GOOD, "r.py": "0\n"})
TWO_PASSES = [("git", "checkout", "-q", "-b", "up", "origin/main"),
              ("commit", {"docs/HANDOFF.md": H1, "p1.py": "1\n"}),
              ("commit", {"docs/HANDOFF.md": H2, "p2.py": "2\n"}),
              ("git", "push", "-q", "origin", "up:main")]
REVERT_ADVICE = "git checkout $(git merge-base HEAD origin/main) -- docs/HANDOFF.md"
# a handoff pass lands on origin/main from elsewhere; cwd ends on branch up
UPSTREAM_PASS = [("git", "checkout", "-q", "-b", "up", "origin/main"), PASS,
                 ("git", "push", "-q", "origin", "up:main")]
CLOSE_RULE = "close a `lane` issue only when a merged PR's notes have the exact line `Lane: #<N>. finished`"
# The one stop rule. The skill rules, the block, this hook's STALE text and
# context-handoff.py's wind-down notice each carry it word for word.
STOP_RULE = ("Write a lane body only with `scripts/lane_claim.py write` or "
             "`release`, and if it refuses, change nothing, stop, and tell "
             "the owner.")
# the pass claims a lane before it writes its `## Next` (review round 7)
CLAIM_FIRST = 'claim the lane first with `python3 scripts/lane_claim.py claim <N> "<name>"`'
STALE = [STOP_RULE, "HANDOFF STALE", "handoff pass", "`lane` issue", CLOSE_RULE,
         CLAIM_FIRST, EXIT_RULE]

# (name, first branch, steps, stderr must carry, stderr must not carry)
BRANCH_CASES = [
    ("lane with real work is told to use the PR body",
     "main", [BASE, ("branch", "feat/x"), *WORK], LANE, ["HANDOFF STALE"]),
    ("lane that edited the handoff is told lanes do not",
     "main", [BASE, ("branch", "feat/x"), WORK[0], TOUCH],
     ["HANDOFF NOTES", "Lanes do not edit",
      "a lane that changes the `## Start here` block itself edits docs/HANDOFF.md, "
      "and this warning is expected there"], ["HANDOFF STALE"]),
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
    ("detached HEAD that edited the handoff hears only the edit warning",
     "main", [BASE, ("detach",), LANE_WORK[0], TOUCH],
     ["HANDOFF NOTES", "Lanes do not edit", "these commits touched it"],
     ["HANDOFF STALE", "changes real files", NOTES_ASK]),
    ("lane whose only change is the handoff hears only the edit warning",
     "main", [BASE, ("branch", "feat/doc"), TOUCH],
     ["HANDOFF NOTES", "Lanes do not edit"],
     ["HANDOFF STALE", "changes real files", NOTES_ASK]),
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
    ("lane cut from local main ahead of origin by work and a pass is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              *WORK, PASS, ("branch", "feat/new")], [], QUIET),
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
    # Round 3: a local trunk that diverged from origin is closest to the lane,
    # but the lane's handoff matches origin/main, so the lane did not edit it.
    ("lane merged origin/main's pass while local main is 2 unpushed ahead",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("commit", {"local1.py": "1\n"}), ("commit", {"local2.py": "2\n"}),
              ("branch", "feat/x"), ("commit", {"x.py": "x\n"}),
              *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
              ("git", "merge", "-q", "--no-edit", "origin/main")],
     LANE, ["Lanes do not edit", "HANDOFF STALE"]),
    ("lane off a local-only master merged origin/main's pass",
     "master", [BASE, ("remote",), ("git", "push", "-q", "origin", "master:main"),
                *WORK, ("branch", "feat/x"), *LANE_WORK,
                *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
                ("git", "merge", "-q", "--no-edit", "origin/main")],
     LANE, ["Lanes do not edit", "HANDOFF STALE"]),
    # Round 4: a stale trunk ref must not count as a match. Its merge-base is
    # an ancestor of origin/main's, so matching it deletes origin's passes.
    ("lane reverted to a stale local main's handoff is still warned",
     "main", [TRUNK_BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              *TWO_PASSES, ("git", "checkout", "-q", "main"),
              ("git", "checkout", "-q", "-b", "feat/x", "origin/main"),
              ("commit", {"x.py": "x\n", "docs/HANDOFF.md": H2 + "my notes\n"}),
              ("git", "checkout", "main", "--", "docs/HANDOFF.md"),
              ("git", "commit", "-q", "-m", "revert as told")],
     ["Lanes do not edit", REVERT_ADVICE], ["HANDOFF STALE"]),
    ("lane off an in-sync origin/main with real work gets the notes",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "feat/x"), *WORK], LANE, ["Lanes do not edit"]),
    ("lane with no work of its own, off a diverged local main, is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("commit", {"local1.py": "1\n"}), ("commit", {"local2.py": "2\n"}),
              ("branch", "feat/x"), *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
              ("git", "merge", "-q", "--no-edit", "origin/main")], [], QUIET),
    ("lane trimmed to a stale local master's handoff is still warned",
     "master", [TRUNK_BASE, ("remote",), ("git", "push", "-q", "origin", "master:main"),
                *TWO_PASSES, ("git", "checkout", "-q", "master"),
                ("git", "checkout", "-q", "-b", "feat/x", "origin/main"),
                ("commit", {"x.py": "x\n", "docs/HANDOFF.md": GOOD})],
     ["Lanes do not edit"], ["HANDOFF STALE"]),
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

    # Round 9: run from a subfolder, the hook checks the script at the repo
    # top, and the copy command it prints targets the repo top.
    for label, files, want, forbid in (
            ("missing", {"docs/HANDOFF.md": GOOD, SCRIPT: None},
             [NO_SCRIPT, "{top}/" + SCRIPT, "mkdir -p '{top}/scripts'"], []),
            ("present", {"docs/HANDOFF.md": GOOD}, [], [NO_SCRIPT, "not tracked"])):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, files, ["docs/HANDOFF.md"])
            sub = pathlib.Path(tmp, "src", "deep")
            sub.mkdir(parents=True)
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=tmp,
                                 capture_output=True, text=True).stdout.strip()
            got = run_hook(sub)
        missing = [w.format(top=top) for w in want if w.format(top=top) not in got.stderr]
        present = [f for f in forbid if f in got.stderr]
        if missing or present or got.returncode != 0:
            failures += 1
            print(f"FAIL from a subfolder, script {label}: missing={missing} "
                  f"unwanted={present}\n--- stderr ---\n{got.stderr}")

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

    # The "handoff was kept" branch: two commits of real work, and the handoff
    # touched by a commit in the window, or edited and not yet committed, or
    # only touched long before the window.
    day = 24 * 3600
    for label, handoff_age, edit, want in (
            ("handoff committed in the window", 0, False, False),
            ("handoff edited, not committed", 2 * day, True, False),
            ("handoff last committed two days ago", 2 * day, False, True)):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"])
            stamp = "@%d +0000" % (int(time.time()) - handoff_age)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                            "commit", "-q", "-m", "handoff"], cwd=tmp, check=True,
                           capture_output=True,
                           env=dict(os.environ, GIT_AUTHOR_DATE=stamp,
                                    GIT_COMMITTER_DATE=stamp))
            for name in ("a.py", "b.py"):
                pathlib.Path(tmp, name).write_text("1\n")
                git(tmp, "add", name)
                git(tmp, "commit", "-q", "-m", name)
            if edit:
                pathlib.Path(tmp, "docs/HANDOFF.md").write_text(GOOD + "\nmore\n")
            got = run_hook(tmp)
        if ("HANDOFF STALE" in got.stderr) != want or got.returncode != 0:
            failures += 1
            print(f"FAIL {label}: want stale={want} (exit {got.returncode}):\n{got.stderr}")

    # A handoff commit on an unmerged branch is no handoff on trunk. Trunk is
    # judged by its own history only, so this still warns.
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"a.py": "1\n"}, ["a.py"])
        git(tmp, "commit", "-q", "-m", "one")
        pathlib.Path(tmp, "b.py").write_text("2\n")
        git(tmp, "add", "b.py")
        git(tmp, "commit", "-q", "-m", "two")
        git(tmp, "checkout", "-q", "-b", "docs/handoff-open")
        pathlib.Path(tmp, "docs").mkdir()
        pathlib.Path(tmp, "docs/HANDOFF.md").write_text(GOOD)
        git(tmp, "add", "docs/HANDOFF.md")
        git(tmp, "commit", "-q", "-m", "unmerged pass")
        git(tmp, "checkout", "-q", "-")
        got = run_hook(tmp)
    if "HANDOFF STALE" not in got.stderr or got.returncode != 0:
        failures += 1
        print(f"FAIL handoff only on an unmerged branch still warns on trunk "
              f"(exit {got.returncode}):\n{got.stderr}")

    # A missing or broken handoff_touch.py must never crash the Stop hook.
    for label, helper in (("missing", None), ("raises", "raise RuntimeError('x')\n")):
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp, "plugin")
            copy.mkdir()
            shutil.copy(HOOK, copy / "handoff-freshness.py")
            if helper:
                (copy / "handoff_touch.py").write_text(helper)
            repo = pathlib.Path(tmp, "repo")
            repo.mkdir()
            make_repo(repo, {"a.py": "1\n"}, ["a.py"])
            git(repo, "commit", "-q", "-m", "one")
            env = {k: v for k, v in os.environ.items() if k != "SKIP_HANDOFF_CHECK"}
            got = subprocess.run([sys.executable, str(copy / "handoff-freshness.py")],
                                 input="{}", cwd=repo, env=env,
                                 capture_output=True, text=True)
        if got.returncode != 0 or got.stderr or got.stdout:
            failures += 1
            print(f"FAIL helper {label}: exit={got.returncode}\n{got.stderr}")

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

    failures += check_lane_jq()

    # the stop rule, word for word, in the block and in the skill's rules
    flat = lambda text: " ".join(text.split())
    rules = SKILL.read_text().split("## The rules", 1)[-1].split("\n## ", 1)[0]
    for where, text in (("the pinned block", BLOCK), ("the skill rules", rules)):
        if STOP_RULE not in flat(text):
            failures += 1
            print(f"FAIL {where} does not carry the stop rule word for word")
        if EXIT_RULE not in flat(text):
            failures += 1
            print(f"FAIL {where} does not tell exit 1 from any other exit")

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
