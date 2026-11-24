#!/usr/bin/env python3
"""Self-test for handoff-freshness.py. Run it after any edit to that hook.

Each case is a temp git repo shaped one way, the hook run inside it on a Stop
event, and the warning it prints (or the silence) compared with what the
shape rule in skills/handoff/SKILL.md says should happen.

Run: ./hooks/handoff-freshness-selftest.py
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import shutil
import tempfile
import time

from handoff_sent import SENT_FILE
from handoff_shape import FENCED

HOOK = str(pathlib.Path(__file__).with_name("handoff-freshness.py"))

SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "handoff" / "SKILL.md"
REPO_HANDOFF = SKILL.parent.parent.parent / "docs" / "HANDOFF.md"

# The block skills/handoff/SKILL.md tells every repo to paste. Pinned here so
# the skill cannot drift from it without this test noticing.
BLOCK = r"""# Handoff

## Start here

You are a fresh session. This file and the repo's open tickets are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Run the repo's free work check, the command its `CLAUDE.md` names. It
   prints the tickets that may start now, first one first. The repo names
   no free work check: read `## Next` in this file for the tasks, and go
   to step 4.
3. Take tickets. The owner named one: take it. If the check does not print
   it, tell the owner why, and stop. Else take the first two to four the
   check prints. It prints none: tell the owner, and stop. Take each
   ticket with a branch linked to it, in its own worktree (`git-worktrees`):
   `gh issue develop <N> --name <type>/<N>-<short> --base <trunk> --checkout --worktree .worktrees/<NN>-<short>`
   The linked branch marks the ticket taken. If gh refuses, change
   nothing, stop, and tell the owner. Then run `gh issue develop --list <N>`.
   It lists a branch other than yours: another session took the ticket at
   the same time. Delete your branch on GitHub and your worktree, and take
   the next ticket.
4. Read `## Now` in this file. Run the recount commands before trusting
   any number. Start more tickets as earlier ones merge. Ask the owner
   nothing that this file or the tickets answer.

A ticket's state lives on GitHub, never in this file. A "blocked by" link
holds it back. The label `needs-owner` or `wayfinder:grilling` makes it
wait. A linked branch marks it taken. When you stop with a ticket not
finished, push its branch and comment on the ticket where the work stopped.
Delete the branch only when it holds no work: that frees the ticket.
Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
"""

# The free work block, in use from 2026-11-24 until each pass rewrote
# `## Now` and `## Next` (#198). Its step 2 reads the LAST section, so a
# repo still on it must warn.
OLD_FREE_WORK_BLOCK = r"""# Handoff

## Start here

You are a fresh session. This file and the repo's open tickets are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
   anything. Read the repo `CLAUDE.md`.
2. Run the repo's free work check, the command its `CLAUDE.md` names. It
   prints the tickets that may start now, first one first. The repo names
   no free work check: read the LAST section of this file for the tasks,
   and go to step 4.
3. Take tickets. The owner named one: take it. If the check does not print
   it, tell the owner why, and stop. Else take the first two to four the
   check prints. It prints none: tell the owner, and stop. Take each
   ticket with a branch linked to it, in its own worktree (`git-worktrees`):
   `gh issue develop <N> --name <type>/<N>-<short> --base <trunk> --checkout --worktree .worktrees/<NN>-<short>`
   The linked branch marks the ticket taken. If gh refuses, change
   nothing, stop, and tell the owner. Then run `gh issue develop --list <N>`.
   It lists a branch other than yours: another session took the ticket at
   the same time. Delete your branch on GitHub and your worktree, and take
   the next ticket.
4. Read the recent sections of this file for traps. Run the recount
   commands before trusting any number. Start more tickets as earlier ones
   merge. Ask the owner nothing that this file or the tickets answer.

A ticket's state lives on GitHub, never in this file. A "blocked by" link
holds it back. The label `needs-owner` or `wayfinder:grilling` makes it
wait. A linked branch marks it taken. When you stop with a ticket not
finished, push its branch and comment on the ticket where the work stopped.
Delete the branch only when it holds no work: that frees the ticket.
Leave this block alone.

Judgment and reasoning only. No counts, no SHAs, no issue tallies: those rot
within hours. Derive them with `gh issue list` and the scripts in the repo.
"""

# The lane block, in use from 2026-11-10 until lane issues retired on
# 2026-11-24 (#228, from twenty #672). A repo still on it must warn.
OLD_LANE_BLOCK = r"""# Handoff

## Start here

You are a fresh session. This file and the open `lane` issues are your
whole briefing. Nobody writes you a separate prompt. Do these in order.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
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
   task it names in the same turn, each in its own worktree (`git-worktrees`), two
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

# What SessionStart adds to the shape warning (issue #117), word for word.
# The session runs this to find an open migration PR before it migrates.
OPEN_PR_CMD = ("gh pr list --state open --limit 100 --json number,title,files "
               "--jq '.[] | select(any(.files[]; .path == \"docs/HANDOFF.md\")) "
               "| \"#\\(.number) \\(.title)\"'")
FIRST_TASK = (f"First run `{OPEN_PR_CMD}`. It prints a PR: a migration is "
              "open, so skip it. It prints nothing: migrate docs/HANDOFF.md to "
              "this shape as your first task, before you take a ticket or start "
              "any other work.")

# The block before 2026-11-10: one first task for every session, so two
# sessions on two lanes both took the same one. It must warn.
OLD_BLOCK = """# Handoff

## Start here

You are a fresh session and this file is your whole briefing. Nobody
writes you a separate prompt. Do these in order, then work.

1. Load skills `ship-loop`, `git-worktrees` and `fresh-eye` before touching
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
# The old checks for a copy of scripts/lane_claim.py and for the lane list
# past line 40 retired with lane issues (#228). Their messages must not come
# back, e.g. for a repo that still has the script.
SCRIPT = "scripts/lane_claim.py"
RETIRED = ["lane_claim.py differs", "has no scripts/lane_claim.py",
           "is not tracked", "past line 40"]
# the phrase past the 40-line window is body text, e.g. a quote of the old rule
LATE_PREAMBLE = GOOD + "\n" * 20 + "The old rule said: written at the end of the session.\n"
NO_BLOCK = "# Handoff\n\n## 2026-09-16\n\nFirst task: x.\n"
# Each wrong Start here block below must warn, each with its own text.
TAIL = "\n## 2026-09-16\n\nFirst task: x.\n"
STEP2 = "2. Run the repo's free work check, the command its `CLAUDE.md` names. It"
LAST_STEP = GOOD.replace(STEP2, "2. Read the LAST section. It names the first task.", 1)
assert LAST_STEP != GOOD
# the old lane block, as a repo that has not migrated still has it
OLD_LANE = OLD_LANE_BLOCK + TAIL
H3_START = GOOD.replace("## Start here\n", "### Start here\n", 1)
LATER_START = GOOD.replace("## Start here\n", "## Start here later\n", 1)
# "1. Read the LAST section" in a dated section below the block is history
OLD_STEP_BELOW = GOOD + "\n## 2026-09-17\n\n1. Read the LAST section of this file.\n"
LATER_ONLY = "# Handoff\n\n## Start here later\n\nFirst task: x.\n"
# the block pasted low, past line 40, is still the block
LOW = BLOCK.replace("## Start here\n", "\n" * 41 + "## Start here\n", 1) + TAIL
OLD_SINGLE_TASK = OLD_BLOCK + "\n## 2026-09-16\n\nFirst task: x.\n"
# Issue #118: the block PR #90 replaced. Step 6 said "Start the first task it
# names". No old-form pattern caught it, so only the comparison with the
# plugin's block does. The warning names the first line that differs.
STEP6 = "   it, tell the owner why, and stop. Else take the first two to four the"
OLD_STEP6 = GOOD.replace(STEP6, "   it, tell the owner why, and stop. Start the first task it names the", 1)
assert OLD_STEP6 != GOOD
STEP6_LINE = GOOD.splitlines().index(STEP6) + 1
DRIFT = "block differs from the plugin's"
# a block cut short ends where the plugin's block goes on
LAST_LINE = "within hours. Derive them with `gh issue list` and the scripts in the repo."
CUT = GOOD.replace(LAST_LINE + "\n", "", 1)
CUT_LINE = GOOD.splitlines().index(LAST_LINE) + 1
# Round 1 of the #118 review: an empty Start here block is drift too, and
# the warning names the plugin's first line as missing.
EMPTY = "block differs from the plugin's: it is empty"
FIRST_PLUGIN_LINE = "You are a fresh session. This file and the repo's open tickets are your"
EMPTY_BLOCK = "# Handoff\n\n## Start here\n\n## Next\nx\n"
BLANK_BLOCK = "# Handoff\n\n## Start here\n\n   \n\t\n\n## Next\nx\n"
LAST_HEADING = "# Handoff\n\n## Start here"
# trailing spaces and CRLF line ends are no drift
TRAILING = GOOD.replace("   anything. Read the repo `CLAUDE.md`.\n",
                        "   anything. Read the repo `CLAUDE.md`.   \n", 1)
assert TRAILING != GOOD
CRLF = GOOD.replace("\n", "\r\n")
OLD_PREAMBLE = ("# Handoff\n\n## Start here\n\nWritten at the end of a session, "
                "this file says where things stand.\n")
# Issue #201: a path in backticks in docs/HANDOFF.md or docs/adr/*.md that
# does not exist warns, with the file and the line. Each skip case below
# holds a path that does not exist, so a skip rule that breaks warns.
DEAD = "which does not exist"
DEAD_PATH = GOOD + "\nSee `docs/nope.md`.\n"
DEAD_LINE = len(GOOD.splitlines()) + 2
LIVE_PATH = GOOD + "\nSee `docs/real.md`.\n"
ADR = "docs/adr/0001-pick.md"
DEAD_ADR = "# 1. Pick\n\nThe rule lives in `hooks/gone.py`.\n"
FENCE = GOOD + "\n```\ncat `docs/nope.md`\n```\n"
SKIPS = [("a URL", "`https://example.org/docs/nope.md`"),
         ("a path with <", "`docs/<name>.md`"),
         ("a path with *", "`docs/adr/*.md`"),
         ("a path with ~", "`~/docs/nope.md`"),
         ("a path under .scratch/", "`.scratch/notes/nope.md`")]

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
     ["HANDOFF SHAPE", DRIFT, "skills/handoff"], []),
    ("the step 6 before PR #90 warns and names its line",
     {"docs/HANDOFF.md": OLD_STEP6}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", f"{DRIFT}, first at line {STEP6_LINE}",
      "Start the first task it names", STEP6.strip()], []),
    ("a block cut short warns where the plugin's block goes on",
     {"docs/HANDOFF.md": CUT}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", f"{DRIFT}, first at line {CUT_LINE}", LAST_LINE], []),
    ("a repo that still tracks the retired script gets no script warning",
     {"docs/HANDOFF.md": GOOD, SCRIPT: "x\n"}, ["docs/HANDOFF.md", SCRIPT],
     [], ["HANDOFF", *RETIRED]),
    ("the free work block that reads the LAST section warns",
     {"docs/HANDOFF.md": OLD_FREE_WORK_BLOCK + TAIL}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", DRIFT, "read the LAST section"], RETIRED),
    ("the retired lane block warns and names its first line",
     {"docs/HANDOFF.md": OLD_LANE}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", DRIFT, "open `lane` issues"], RETIRED),
    ("the repo's own lines after the plugin's block pass",
     {"docs/HANDOFF.md": BLOCK + "\nWhat this repo is: x.\n" + TAIL},
     ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    # The old-form checks went in #118. The comparison catches these now.
    ("a step that opens with Read the LAST section warns",
     {"docs/HANDOFF.md": LAST_STEP}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", DRIFT, "2. Read the LAST section"], []),
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
     ["has no `## Start here` line"], RETIRED),
    ("a block pasted past line 40 warns nothing",
     {"docs/HANDOFF.md": LOW}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("an empty block warns and names the plugin's first line",
     {"docs/HANDOFF.md": EMPTY_BLOCK}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", EMPTY, FIRST_PLUGIN_LINE], []),
    ("a block of blank lines warns as empty",
     {"docs/HANDOFF.md": BLANK_BLOCK}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", EMPTY, FIRST_PLUGIN_LINE], []),
    ("## Start here as the last line warns as empty",
     {"docs/HANDOFF.md": LAST_HEADING}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", EMPTY, FIRST_PLUGIN_LINE], ["has no `## Start here` line"]),
    ("trailing spaces in the block are no drift",
     {"docs/HANDOFF.md": TRAILING}, ["docs/HANDOFF.md"], [], ["HANDOFF"]),
    ("CRLF line ends are no drift",
     {"docs/HANDOFF.md": CRLF}, ["docs/HANDOFF.md"], [], ["HANDOFF"]),
    ("preamble phrase past line 40 is body text, no warning",
     {"docs/HANDOFF.md": LATE_PREAMBLE}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    ("a dead path in the handoff warns with its file and line",
     {"docs/HANDOFF.md": DEAD_PATH}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", f"docs/HANDOFF.md:{DEAD_LINE}", "`docs/nope.md`", DEAD], []),
    ("a live path in the handoff warns nothing",
     {"docs/HANDOFF.md": LIVE_PATH, "docs/real.md": "x\n"}, ["docs/HANDOFF.md"],
     [], ["HANDOFF SHAPE"]),
    ("a dead path in an ADR warns with its file and line",
     {"docs/HANDOFF.md": GOOD, ADR: DEAD_ADR}, ["docs/HANDOFF.md"],
     ["HANDOFF SHAPE", f"{ADR}:3", "`hooks/gone.py`", DEAD], []),
    ("a path in a fenced code block is skipped",
     {"docs/HANDOFF.md": FENCE}, ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]),
    *[(f"{label} is skipped", {"docs/HANDOFF.md": GOOD + f"\nSee {tok}.\n"},
       ["docs/HANDOFF.md"], [], ["HANDOFF SHAPE"]) for label, tok in SKIPS],
]


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def stop_text(got):
    """What a Stop run tells the model (issue #125): the additionalContext of
    one Stop JSON object on stdout. Claude never sees stderr from a hook that
    exits 0, so text there counts as nothing."""
    try:
        out = json.loads(got.stdout)["hookSpecificOutput"]
    except Exception:
        return ""
    if out.get("hookEventName") != "Stop" or got.returncode != 0:
        return ""
    return out.get("additionalContext", "")


def run_hook(cwd, env_extra=None, event=None, extra=None):
    env = {k: v for k, v in os.environ.items() if k != "SKIP_HANDOFF_CHECK"}
    env.update(env_extra or {})
    data = dict({"hook_event_name": event} if event else {}, **(extra or {}))
    got = subprocess.run([sys.executable, HOOK], input=json.dumps(data), cwd=cwd,
                         env=env, capture_output=True, text=True)
    got.warn = stop_text(got)
    return got


def session_start_failures():
    """Issue #117: at session start the hook runs only the shape check, and
    tells the session to migrate the file before anything else."""
    failures = 0
    # A shape problem: the Stop text, word for word, in additionalContext,
    # plus the first-task sentence. Nothing on stderr, exit 0. The old block
    # has two problems, so sending only the first one fails.
    # Issue #118: the block comparison reaches the session too, and so does
    # the retired lane block (#228). That block also points to the retired
    # `scripts/lane_claim.py`, which is a dead path (#201).
    for label, extra, count, want in (
            ("no block", {"docs/HANDOFF.md": NO_BLOCK}, 1, ""),
            ("old block", {"docs/HANDOFF.md": OLD_PREAMBLE}, 2, DRIFT),
            ("lane block", {"docs/HANDOFF.md": OLD_LANE}, 2, DRIFT)):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, extra, list(extra))
            stop = run_hook(tmp, event="Stop")
            got = run_hook(tmp, event="SessionStart")
        try:
            out = json.loads(got.stdout)["hookSpecificOutput"]
        except Exception:
            out = {}
        text = out.get("additionalContext", "")
        if (out.get("hookEventName") != "SessionStart" or got.returncode != 0
                or got.stderr or stop.warn.count("HANDOFF SHAPE") != count
                or stop.warn.strip() not in text or FIRST_TASK not in text
                or want not in text):
            failures += 1
            print(f"FAIL SessionStart, {label} (exit {got.returncode}):"
                  f"\n--- stdout ---\n{got.stdout}\n--- stderr ---\n{got.stderr}")
    # SessionStart with a session id and a shape problem writes no record,
    # so the first Stop of that session still sends the warning.
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        got = run_hook(tmp, event="SessionStart", extra={"session_id": "s1"})
        record = pathlib.Path(tmp, ".git", SENT_FILE)
        kept = record.read_text() if record.exists() else ""
    if "s1 " in kept or "HANDOFF SHAPE" not in got.stdout:
        failures += 1
        print(f"FAIL SessionStart wrote a Stop record: {kept!r}\n{got.stdout}")
    # The skip switch silences SessionStart too.
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        got = run_hook(tmp, {"SKIP_HANDOFF_CHECK": "1"}, event="SessionStart")
    if got.stdout or got.stderr or got.returncode != 0:
        failures += 1
        print(f"FAIL SessionStart with SKIP_HANDOFF_CHECK=1 printed:\n{got.stdout}{got.stderr}")
    # The jq filter in the sentence finds only an open PR that changes the file.
    if shutil.which("jq"):
        program = re.search(r"--jq '(.*)'$", OPEN_PR_CMD).group(1)
        prs = [{"number": 7, "title": "migrate", "files": [{"path": "docs/HANDOFF.md"}]},
               {"number": 8, "title": "other", "files": [{"path": "docs/HANDOFF.md.bak"}]},
               {"number": 9, "title": "none", "files": []}]
        got = subprocess.run(["jq", "-r", program], input=json.dumps(prs),
                             capture_output=True, text=True)
        if got.returncode != 0 or got.stdout != "#7 migrate\n":
            failures += 1
            print(f"FAIL open-PR jq printed (exit {got.returncode}):\n{got.stdout}{got.stderr}")
    # The Stop run carries no first-task sentence, and nothing on stderr.
    if not stop.warn or stop.stderr or FIRST_TASK in stop.warn or stop.returncode != 0:
        failures += 1
        print(f"FAIL Stop output changed:\n{stop.stdout}\n{stop.stderr}")
    # A correct block prints nothing. No handoff prints nothing, even with
    # two commits of real work: SessionStart skips the staleness check.
    for label, files, tracked in (
            ("correct block", {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"]),
            ("no handoff, real work", {"a.py": "1\n", "b.py": "2\n"}, [])):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, files, tracked)
            for name in tracked or ["a.py", "b.py"]:
                git(tmp, "add", name)
                git(tmp, "commit", "-q", "-m", name)
            got = run_hook(tmp, event="SessionStart")
        if got.stdout or got.stderr or got.returncode != 0:
            failures += 1
            print(f"FAIL SessionStart, {label}, printed (exit {got.returncode}):"
                  f"\n{got.stdout}{got.stderr}")
    return failures


def stale_repo(tmp):
    """Trunk with two commits of real work, the handoff commit before the
    8-hour window: a Stop here prints HANDOFF STALE."""
    make_repo(tmp, {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"])
    stamp = "@%d +0000" % (int(time.time()) - 2 * 24 * 3600)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "handoff"], cwd=tmp, check=True,
                   capture_output=True, env=dict(os.environ, GIT_AUTHOR_DATE=stamp,
                                                 GIT_COMMITTER_DATE=stamp))
    for name in ("a.py", "b.py"):
        pathlib.Path(tmp, name).write_text("1\n")
        git(tmp, "add", name)
        git(tmp, "commit", "-q", "-m", name)


def stop_channel_failures():
    """Issue #125: each Stop warning reaches the model as Stop
    additionalContext JSON on stdout, nothing on stderr, exit 0. It is sent
    once per session per warning, and never when stop_hook_active is true."""
    def shape(tmp):
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])

    def notes(tmp):
        make_repo(tmp, {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"])
        git(tmp, "commit", "-q", "-m", "base")
        git(tmp, "checkout", "-q", "-b", "feat/x")
        pathlib.Path(tmp, "a.py").write_text("1\n")
        git(tmp, "add", "a.py")
        git(tmp, "commit", "-q", "-m", "a")

    failures = 0
    for tag, setup in (("HANDOFF SHAPE", shape), ("HANDOFF NOTES", notes),
                       ("HANDOFF STALE", stale_repo)):
        with tempfile.TemporaryDirectory() as tmp:
            setup(tmp)
            first = run_hook(tmp, event="Stop",
                             extra={"session_id": "s1", "stop_hook_active": False})
            looping = run_hook(tmp, event="Stop",
                               extra={"session_id": "s0", "stop_hook_active": True})
            again = run_hook(tmp, event="Stop",
                             extra={"session_id": "s1", "stop_hook_active": False})
            other = run_hook(tmp, event="Stop",
                             extra={"session_id": "s2", "stop_hook_active": False})
        for label, got, want in (("first Stop", first, True),
                                 ("stop_hook_active", looping, False),
                                 ("same session again", again, False),
                                 ("a new session", other, True)):
            ok = (got.returncode == 0 and not got.stderr
                  and (tag in got.warn if want else not got.stdout))
            if not ok:
                failures += 1
                print(f"FAIL {tag} channel, {label}: exit={got.returncode}"
                      f"\n--- stdout ---\n{got.stdout}\n--- stderr ---\n{got.stderr}")
    return failures


def stop_once_failures():
    """Round 1 of the #125 review: the once-per-session record is keyed on
    each warning's variant, so a different message under the same tag still
    arrives, and a record that cannot be read or written never hides one."""
    stop = lambda cwd: run_hook(cwd, event="Stop", extra={"session_id": "s1"})
    commit = lambda tmp, rel, text: (pathlib.Path(tmp, rel).write_text(text),
                                     git(tmp, "add", rel),
                                     git(tmp, "commit", "-q", "-m", rel))
    edited = EDITED
    failures = 0

    def check(label, ok, got):
        nonlocal failures
        if not ok or got.returncode != 0:
            failures += 1
            print(f"FAIL once per session, {label}: exit={got.returncode}"
                  f"\n--- told the model ---\n{got.warn}\n--- stderr ---\n{got.stderr}")

    def on_branch(tmp, handoff=GOOD):
        make_repo(tmp, {"docs/HANDOFF.md": handoff}, ["docs/HANDOFF.md"])
        git(tmp, "commit", "-q", "-m", "base")
        git(tmp, "checkout", "-q", "-b", "feat/x")

    # NOTES "write your notes", then NOTES "you edited the handoff"
    with tempfile.TemporaryDirectory() as tmp:
        on_branch(tmp)
        commit(tmp, "a.py", "1\n")
        first = stop(tmp)
        commit(tmp, "docs/HANDOFF.md", GOOD + "\nbranch edit\n")
        second = stop(tmp)
    check("NOTES first variant", NOTES_ASK in first.warn, first)
    check("NOTES edited variant after the first", edited in second.warn, second)

    # the other order: NOTES "you edited the handoff", then real work
    # (key NOTES/real+edited differs from NOTES/edited, so it is sent again)
    with tempfile.TemporaryDirectory() as tmp:
        on_branch(tmp)
        commit(tmp, "docs/HANDOFF.md", GOOD + "\nbranch edit\n")
        first = stop(tmp)
        commit(tmp, "a.py", "1\n")
        second = stop(tmp)
    check("NOTES edited variant first", edited in first.warn
          and NOTES_ASK not in first.warn, first)
    check("NOTES real variant after the edited one", NOTES_ASK in second.warn, second)

    # one SHAPE problem, then a different one
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        first = stop(tmp)
        pathlib.Path(tmp, "old-handoff.md").write_text("x\n")
        git(tmp, "add", "old-handoff.md")
        second = stop(tmp)
    check("SHAPE first problem", "HANDOFF SHAPE" in first.warn, first)
    check("SHAPE second problem", "old-handoff.md" in second.warn
          and "has no `## Start here`" not in second.warn, second)

    # SHAPE sent first, then NOTES created in the same session
    with tempfile.TemporaryDirectory() as tmp:
        on_branch(tmp, NO_BLOCK)
        first = stop(tmp)
        commit(tmp, "a.py", "1\n")
        second = stop(tmp)
        third = stop(tmp)
    check("SHAPE before NOTES", "HANDOFF SHAPE" in first.warn
          and "HANDOFF NOTES" not in first.warn, first)
    check("NOTES after SHAPE", "HANDOFF NOTES" in second.warn
          and "HANDOFF SHAPE" not in second.warn, second)
    # the record keeps both keys, so neither comes back
    check("Stop 3 after SHAPE and NOTES", not third.stdout, third)

    # STALE once: another commit changes its count, never its key
    with tempfile.TemporaryDirectory() as tmp:
        stale_repo(tmp)
        first = stop(tmp)
        commit(tmp, "c.py", "1\n")
        second = stop(tmp)
    check("STALE first Stop", "HANDOFF STALE" in first.warn, first)
    check("STALE after one more commit", not second.stdout, second)

    # a record with a bad byte reads as nothing held back, never a crash
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        pathlib.Path(tmp, ".git", SENT_FILE).write_bytes(b"s1 \xff\n")
        got = stop(tmp)
    check("record with a bad byte", "HANDOFF SHAPE" in got.warn and not got.stderr, got)

    # two worktrees, one session id: each worktree has its own record
    with tempfile.TemporaryDirectory() as tmp:
        main_tree = pathlib.Path(tmp, "main")
        main_tree.mkdir()
        make_repo(main_tree, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        git(main_tree, "commit", "-q", "-m", "base")
        git(main_tree, "worktree", "add", "-q", "../wt", "-b", "wt")
        first = stop(main_tree)
        second = stop(pathlib.Path(tmp, "wt"))
    check("first worktree", "HANDOFF SHAPE" in first.warn, first)
    check("second worktree, same session", "HANDOFF SHAPE" in second.warn, second)

    # no session id: the warning arrives on every Stop, and no record is written
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        runs = [run_hook(tmp, event="Stop") for _ in range(2)]
        record = pathlib.Path(tmp, ".git", SENT_FILE).exists()
    for n, got in enumerate(runs, 1):
        check(f"no session id, Stop {n}", "HANDOFF SHAPE" in got.warn and not record, got)

    # a record that cannot be read, or a git dir that cannot be written:
    # the warning arrives on every Stop, exit 0. Root ignores the modes.
    if os.geteuid() != 0:
        for label, lock in (("unreadable record", "record"), ("read-only git dir", "gitdir")):
            with tempfile.TemporaryDirectory() as tmp:
                make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
                gitdir = pathlib.Path(tmp, ".git")
                record = gitdir / SENT_FILE
                if lock == "record":
                    record.write_text("")
                target = record if lock == "record" else gitdir
                target.chmod(0o000 if lock == "record" else 0o555)
                try:
                    runs = [stop(tmp), stop(tmp)]
                finally:
                    target.chmod(0o755 if lock == "gitdir" else 0o644)
            for n, got in enumerate(runs, 1):
                check(f"{label}, Stop {n}", "HANDOFF SHAPE" in got.warn, got)

    # A failed `git rev-parse --absolute-git-dir` gives "": the warnings still
    # go out, and no record lands in the working tree.
    sys.path.insert(0, os.path.dirname(HOOK))
    import handoff_sent as hook
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        real_git, hook.git = hook.git, lambda *a: ""
        out = __import__("io").StringIO()
        real_out, sys.stdout = sys.stdout, out
        try:
            hook.send_once("s1", [("STALE", "HANDOFF STALE: x\n")])
        finally:
            sys.stdout, hook.git = real_out, real_git
            os.chdir(cwd)
        leaked = os.listdir(tmp)
    if "HANDOFF STALE" not in out.getvalue() or leaked:
        failures += 1
        print(f"FAIL empty git dir: printed={out.getvalue()!r} wrote={leaked}")

    # The print fails (e.g. a closed pipe): the key is not recorded, so the
    # warning is sent at the next Stop. Record first and it is lost for good.
    class Broken:
        def write(self, _):
            raise OSError("closed")

        def flush(self):
            raise OSError("closed")
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {}, [])
        cwd = os.getcwd()
        os.chdir(tmp)
        real_out, sys.stdout = sys.stdout, Broken()
        try:
            hook.send_once("s1", [("STALE", "HANDOFF STALE: x\n")])
        except OSError:
            pass
        finally:
            sys.stdout = real_out
            os.chdir(cwd)
        record = pathlib.Path(tmp, ".git", SENT_FILE)
        kept = record.read_text() if record.exists() else ""
    if "s1 STALE" in kept:
        failures += 1
        print(f"FAIL failed print: the key was recorded anyway: {kept!r}")
    return failures


def failed_read_failures():
    """A read that fails names that read, never the problem it would have
    looked for (round 2 of the #118 review, then issue #145). Each case
    breaks one read in a repo that is otherwise clean, so the forbid list
    holds the warning the old code gave. Root reads past mode bits, so root
    skips the chmod cases. stop_text() is empty on a non-zero exit, so a
    crash fails the want list and needs no exit-code check of its own."""
    def chmod(rel, mode, back):
        return lambda tmp: pathlib.Path(tmp, rel).chmod(mode), (rel, back)

    def junk_index(tmp):
        # a tracked stray file, so the old silent pass hid a real finding
        pathlib.Path(tmp, "AGENT_HANDOFF.md").write_text("x\n")
        git(tmp, "add", "AGENT_HANDOFF.md")
        pathlib.Path(tmp, ".git", "index").write_bytes(b"junk")

    def unreadable_adr(tmp):
        pathlib.Path(tmp, "docs", "adr").mkdir()
        pathlib.Path(tmp, ADR).write_text(DEAD_ADR)
        pathlib.Path(tmp, ADR).chmod(0)

    cases = [("an unreadable docs/HANDOFF.md", *chmod("docs/HANDOFF.md", 0, 0o644),
              ["cannot read docs/HANDOFF.md at "], ["has no `## Start here` line"]),
             ("an unreadable ADR", unreadable_adr, (ADR, 0o644),
              [f"cannot read {ADR} at ", "its path check did not run"], [DEAD])]
    if os.geteuid() == 0:
        cases = []
    cases.append(("a git index that cannot be read", junk_index, None,
                  ["git cannot list the tracked files, so the check for "
                   "handoff files outside docs/ did not run"],
                  RETIRED))
    failures = 0
    for label, breaks, restore, want, forbid in cases:
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, {"docs/HANDOFF.md": GOOD}, ["docs/HANDOFF.md"])
            breaks(tmp)
            try:
                got = run_hook(tmp)
            finally:
                if restore:
                    pathlib.Path(tmp, restore[0]).chmod(restore[1])
        missing = [w for w in want if w not in got.warn]
        present = [f for f in forbid if f in got.warn]
        if missing or present:
            failures += 1
            print(f"FAIL failed read, {label}: missing={missing} unwanted={present}"
                  f"\n--- told the model ---\n{got.warn}")
    return failures


def make_repo(tmp, files, tracked):
    """Write files (None skips one) and `git add` the tracked ones."""
    git(tmp, "init", "-q")
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
BRANCH_WORK = [("commit", {"c.py": "3\n"}), ("commit", {"d.py": "4\n"})]
PASS = ("commit", {"docs/HANDOFF.md": GOOD})
TOUCH = ("commit", {"docs/HANDOFF.md": GOOD + "\nbranch edit\n"})
OTHER_WORK = [("commit", {"e.py": "5\n"}), ("commit", {"f.py": "6\n"})]
NOTES = ["HANDOFF NOTES", "## Handoff notes"]
EDITED = "Only a handoff branch edits"
QUIET = ["HANDOFF NOTES", EDITED, "HANDOFF STALE"]
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
# The pass turns each next step into ticket state, never lane issue text (#228).
BLOCKED_BY = 'Each "after #X" is a "blocked by" link on GitHub'
NEEDS_OWNER = "the label `needs-owner` on the ticket it holds back"
STALE = ["HANDOFF STALE", "handoff pass", BLOCKED_BY, NEEDS_OWNER]

# (name, first branch, steps, stderr must carry, stderr must not carry)
BRANCH_CASES = [
    ("branch with real work is told to use the PR body",
     "main", [BASE, ("branch", "feat/x"), *WORK], NOTES, ["HANDOFF STALE"]),
    ("branch that edited the handoff is told only a handoff branch edits it",
     "main", [BASE, ("branch", "feat/x"), WORK[0], TOUCH],
     ["HANDOFF NOTES", EDITED,
      "a branch that changes the `## Start here` block itself edits docs/HANDOFF.md, "
      "and this warning is expected there"], ["HANDOFF STALE"]),
    ("handoff branch keeps the stale warning",
     "main", [BASE, ("branch", "docs/handoff-0921"), *WORK], ["HANDOFF STALE"],
     ["HANDOFF NOTES"]),
    ("trunk keeps the stale warning",
     "main", [BASE, *WORK], STALE, ["HANDOFF NOTES", "lane"]),
    ("master is trunk when origin/HEAD is unknown",
     "master", [BASE, *WORK], STALE, ["HANDOFF NOTES"]),
    ("origin/HEAD names the trunk",
     "develop", [BASE, ("origin_head", "develop"), *WORK], STALE, ["HANDOFF NOTES"]),
    ("main stays trunk when origin/HEAD names another trunk",
     "develop", [BASE, ("origin_head", "develop"), ("branch", "main"), *WORK],
     STALE, ["HANDOFF NOTES"]),
    ("docs/handoffish is a branch, the prefix carries its dash",
     "main", [BASE, ("branch", "docs/handoffish"), *WORK], NOTES, ["HANDOFF STALE"]),
    ("fresh branch does not inherit trunk's handoff pass",
     "main", [BASE, *WORK, PASS, ("branch", "feat/new")], [],
     ["HANDOFF NOTES", EDITED, "HANDOFF STALE"]),
    ("branch after trunk's handoff pass counts only its own commits",
     "main", [BASE, *WORK, PASS, ("branch", "feat/new"), *BRANCH_WORK],
     NOTES, [EDITED, "HANDOFF STALE"]),
    ("detached HEAD is a branch and gets no trunk message",
     "main", [BASE, ("detach",), *BRANCH_WORK], [],
     ["HANDOFF STALE", "handoff pass", "HANDOFF NOTES"]),
    ("detached HEAD that edited the handoff hears only the edit warning",
     "main", [BASE, ("detach",), BRANCH_WORK[0], TOUCH],
     ["HANDOFF NOTES", EDITED, "these commits touched it"],
     ["HANDOFF STALE", "changes real files", NOTES_ASK]),
    ("branch whose only change is the handoff hears only the edit warning",
     "main", [BASE, ("branch", "feat/doc"), TOUCH],
     ["HANDOFF NOTES", EDITED],
     ["HANDOFF STALE", "changes real files", NOTES_ASK]),
    # Round 2: judged by the net diff against the closest trunk ref, with a
    # real origin so origin/main and main can differ.
    ("branch that reverted its handoff edit is not told to revert again",
     "main", [BASE, ("branch", "feat/x"), *WORK, TOUCH,
              ("git", "revert", "--no-edit", "HEAD")],
     NOTES, [EDITED, "HANDOFF STALE"]),
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
    ("origin/HEAD naming a deleted feature branch leaves that local branch a branch",
     "main", [BASE, ("git", "symbolic-ref", "refs/remotes/origin/HEAD",
                     "refs/remotes/origin/feat/x"), ("branch", "feat/x"), *WORK],
     NOTES, ["HANDOFF STALE"]),
    ("branch cut from local main ahead of origin by work and a pass is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              *WORK, PASS, ("branch", "feat/new")], [], QUIET),
    ("branch cut from origin/main ahead of local main is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "up"), PASS, ("git", "push", "-q", "origin", "up:main"),
              ("git", "checkout", "-q", "main"), ("git", "branch", "-q", "-D", "up"),
              ("git", "checkout", "-q", "-b", "feat/new", "origin/main")],
     [], QUIET),
    ("shallow branch with no merge-base says nothing",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "feat/x"), BRANCH_WORK[0],
              ("git", "push", "-q", "origin", "feat/x"),
              ("git", "checkout", "-q", "main"), *WORK, PASS,
              ("git", "push", "-q", "origin", "main"),
              ("shallow", "feat/x"), *OTHER_WORK],
     [], QUIET),
    # Round 3: a local trunk that diverged from origin is closest to the branch,
    # but the branch's handoff matches origin/main, so the branch did not edit it.
    ("branch merged origin/main's pass while local main is 2 unpushed ahead",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("commit", {"local1.py": "1\n"}), ("commit", {"local2.py": "2\n"}),
              ("branch", "feat/x"), ("commit", {"x.py": "x\n"}),
              *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
              ("git", "merge", "-q", "--no-edit", "origin/main")],
     NOTES, [EDITED, "HANDOFF STALE"]),
    ("branch off a local-only master merged origin/main's pass",
     "master", [BASE, ("remote",), ("git", "push", "-q", "origin", "master:main"),
                *WORK, ("branch", "feat/x"), *BRANCH_WORK,
                *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
                ("git", "merge", "-q", "--no-edit", "origin/main")],
     NOTES, [EDITED, "HANDOFF STALE"]),
    # Round 4: a stale trunk ref must not count as a match. Its merge-base is
    # an ancestor of origin/main's, so matching it deletes origin's passes.
    ("branch reverted to a stale local main's handoff is still warned",
     "main", [TRUNK_BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              *TWO_PASSES, ("git", "checkout", "-q", "main"),
              ("git", "checkout", "-q", "-b", "feat/x", "origin/main"),
              ("commit", {"x.py": "x\n", "docs/HANDOFF.md": H2 + "my notes\n"}),
              ("git", "checkout", "main", "--", "docs/HANDOFF.md"),
              ("git", "commit", "-q", "-m", "revert as told")],
     [EDITED, REVERT_ADVICE], ["HANDOFF STALE"]),
    ("branch off an in-sync origin/main with real work gets the notes",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("branch", "feat/x"), *WORK], NOTES, [EDITED]),
    ("branch with no work of its own, off a diverged local main, is silent",
     "main", [BASE, ("remote",), ("git", "push", "-q", "origin", "main"),
              ("commit", {"local1.py": "1\n"}), ("commit", {"local2.py": "2\n"}),
              ("branch", "feat/x"), *UPSTREAM_PASS, ("git", "checkout", "-q", "feat/x"),
              ("git", "merge", "-q", "--no-edit", "origin/main")], [], QUIET),
    ("branch trimmed to a stale local master's handoff is still warned",
     "master", [TRUNK_BASE, ("remote",), ("git", "push", "-q", "origin", "master:main"),
                *TWO_PASSES, ("git", "checkout", "-q", "master"),
                ("git", "checkout", "-q", "-b", "feat/x", "origin/main"),
                ("commit", {"x.py": "x\n", "docs/HANDOFF.md": GOOD})],
     [EDITED], ["HANDOFF STALE"]),
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
        err = got.warn
        missing = [w for w in want if w not in err]
        present = [f for f in forbid if f in err]
        # warn only, never block: a Stop hook that exits non-zero strands work
        if missing or present or got.returncode != 0:
            failures += 1
            print(f"FAIL {name}: exit={got.returncode} missing={missing} "
                  f"unwanted={present}\n--- told the model ---\n{err}")

    # Round 9: run from a subfolder, the hook checks the handoff at the top.
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        sub = pathlib.Path(tmp, "src", "deep")
        sub.mkdir(parents=True)
        got = run_hook(sub)
    if "has no `## Start here` line" not in got.warn or got.returncode != 0:
        failures += 1
        print(f"FAIL from a subfolder: exit={got.returncode}\n{got.warn}")

    failures += failed_read_failures()

    # the escape hatch silences the shape check as well as the freshness one
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"docs/HANDOFF.md": NO_BLOCK}, ["docs/HANDOFF.md"])
        got = run_hook(tmp, {"SKIP_HANDOFF_CHECK": "1"})
    if got.stdout or got.stderr or got.returncode != 0:
        failures += 1
        print(f"FAIL SKIP_HANDOFF_CHECK=1 still printed (exit {got.returncode}):\n{got.warn}")

    # the pre-existing freshness warning still fires: two commits of real work,
    # nothing touching the handoff
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, {"a.py": "1\n"}, ["a.py"])
        git(tmp, "commit", "-q", "-m", "one")
        pathlib.Path(tmp, "b.py").write_text("2\n")
        git(tmp, "add", "b.py")
        git(tmp, "commit", "-q", "-m", "two")
        got = run_hook(tmp)
    if "HANDOFF STALE" not in got.warn or got.returncode != 0:
        failures += 1
        print(f"FAIL freshness warning did not fire cleanly (exit {got.returncode}):\n{got.warn}")

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
        if ("HANDOFF STALE" in got.warn) != want or got.returncode != 0:
            failures += 1
            print(f"FAIL {label}: want stale={want} (exit {got.returncode}):\n{got.warn}")

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
    if "HANDOFF STALE" not in got.warn or got.returncode != 0:
        failures += 1
        print(f"FAIL handoff only on an unmerged branch still warns on trunk "
              f"(exit {got.returncode}):\n{got.warn}")

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
            print(f"FAIL helper {label}: exit={got.returncode}\n{got.warn}")

    # Round 1 of the #118 review: when the plugin's skill cannot be read,
    # the hook says so in one warning and does not crash.
    no_block = "cannot read the plugin's `## Start here` block at "
    # Round 2: a fence with no Start here line, an empty block, or a skill
    # that is not UTF-8 is a failed read too. Each runs against a stale
    # repo block. So the forbid list catches a hook that both warns and
    # compares. The bad byte sits inside a well-formed Start here block, so
    # a lenient decode would read a block and give no warning.
    fence = "# Handoff skill\n\n```\n# Handoff\n\n%s```\n"
    for label, skill_text, want, forbid in (
            ("no skill file", None, [no_block], []),
            ("a skill with no fenced block", "# Handoff skill\n", [no_block], []),
            ("a fence with no Start here line", fence % "Some text.\n",
             [no_block], [DRIFT]),
            ("a fence with an empty block", fence % "## Start here\n\n",
             [no_block], [DRIFT]),
            ("a skill that is not UTF-8", b"```\n# Handoff\n\n## Start here\n\nYou are \xff here.\n```\n",
             [no_block], [DRIFT, "Traceback"])):
        with tempfile.TemporaryDirectory() as tmp:
            hooks = pathlib.Path(tmp, "plugin", "hooks")
            hooks.mkdir(parents=True)
            for name in ("handoff-freshness.py", "handoff_shape.py", "handoff_touch.py",
                         "handoff_sent.py"):
                shutil.copy(pathlib.Path(HOOK).with_name(name), hooks / name)
            skill_dir = pathlib.Path(tmp, "plugin", "skills", "handoff")
            if skill_text is not None:
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_bytes(
                    skill_text if isinstance(skill_text, bytes) else skill_text.encode())
            repo = pathlib.Path(tmp, "repo")
            repo.mkdir()
            make_repo(repo, {"docs/HANDOFF.md": OLD_STEP6}, ["docs/HANDOFF.md"])
            env = {k: v for k, v in os.environ.items() if k != "SKIP_HANDOFF_CHECK"}
            got = subprocess.run([sys.executable, str(hooks / "handoff-freshness.py")],
                                 input="{}", cwd=repo, env=env,
                                 capture_output=True, text=True)
            got.warn = stop_text(got)
        want = want + [str(skill_dir / "SKILL.md")]
        missing = [w for w in want if w not in got.warn]
        present = [f for f in forbid if f in got.warn]
        if missing or present or got.returncode != 0 or "Traceback" in got.stderr:
            failures += 1
            print(f"FAIL unreadable plugin copy, {label}: exit={got.returncode} "
                  f"missing={missing} unwanted={present}\n{got.warn}")

    # Branch-aware freshness. Owner rule, 2026-09-21: branches write notes in the
    # PR body's "## Handoff notes" section and never edit the handoff; a
    # docs/handoff-* branch (or trunk) is where the log gets written.
    for name, first, steps, want, forbid in BRANCH_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            got = run_hook(build(tmp, first, steps))
        missing = [w for w in want if w not in got.warn]
        present = [f for f in forbid if f in got.warn]
        if missing or present or got.returncode != 0:
            failures += 1
            print(f"FAIL {name}: exit={got.returncode} missing={missing} "
                  f"unwanted={present}\n--- told the model ---\n{got.warn}")

    failures += session_start_failures()
    failures += stop_channel_failures()
    failures += stop_once_failures()

    # the block takes tickets, and names no lane issue or lane script (#228)
    for word in ("lane", "Held by"):
        if word in BLOCK:
            failures += 1
            print(f"FAIL the pinned block still says {word!r}")
    if "gh issue develop" not in BLOCK:
        failures += 1
        print("FAIL the pinned block does not take a ticket with gh issue develop")
    if "gh issue develop --list" not in BLOCK:
        failures += 1
        print("FAIL the pinned block does not say what to do when a ticket is already linked")

    # the block pinned above is the block the skill tells repos to paste, and
    # the block this repo's own handoff opens with
    fenced = FENCED.search(SKILL.read_text())
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
