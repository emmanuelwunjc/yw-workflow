#!/usr/bin/env python3
"""Claim, write and release a `lane` issue, so the holder rule runs in one process.

Canonical copy: the yw-workflow plugin, `skills/handoff/lane_claim.py`. A repo
copies this file verbatim to `scripts/lane_claim.py`. Edit it in the plugin,
then re-copy. `diff` against the plugin's file is the drift check.

Why a script: the claim used to be prose. An agent read the body in one tool
call and wrote it in a later one, and nothing bounded the gap, so a session
that read a free lane could overwrite a claim made since. Here the read and
the write are about one second apart.

Line one of the issue body is the holder line (docs/DECISIONS.md, 2026-11-10):
  Held by: nobody                               free
  Held by: <name>, since <YYYY-MM-DDTHH:MMZ>    held, if the time is not in
                                                the future
  anything else                                 malformed, so free

Usage, in USAGE below. Exit 0: done. Exit 1: a refusal, and only a
refusal. Nothing changed by this run (a lost claim leaves the winner's
line). Exit 2: everything else, e.g. bad arguments, a bad
LANE_CLAIM_WAIT_SECONDS, a `gh` that is missing, fails, times out or prints
no body, or any other error. The Start here block reads exit 1 as "pick
again" and any other exit as "stop", so an error never walks every lane.

The wait after a claim is 30 seconds. LANE_CLAIM_WAIT_SECONDS exists for
the self-test, which sets it to a few seconds or 0. Real runs leave it
unset, so the default is used.

The read before a write and the edit share one budget of half the wait,
counted from the start of the read to the end of the edit. Each `gh` call
gets what is left of it as its timeout. Past it, the run exits 2 and does
not write. Another session's read and edit then land inside half the wait,
before this session's second read.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HOLDER = re.compile(r"Held by: (?P<name>.+), since "
                    r"(?P<time>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z)")
FREE = "Held by: nobody"
HOLD_HOURS = 24
WAIT_ENV = "LANE_CLAIM_WAIT_SECONDS"
DEFAULT_WAIT_SECONDS = 30
BUDGET = None  # seconds for one read and its edit, set in main from the wait
DEADLINE = None  # when the current budget runs out, on the monotonic clock
USAGE = """usage:
  lane_claim.py claim <issue> <name> [--holder-not-live]
  lane_claim.py write <issue> <name> <file>
  lane_claim.py release <issue> <name>"""
# The one stop rule of skills/handoff, word for word.
STOP_RULE = ("Write a lane body only with `scripts/lane_claim.py write` or "
             "`release`, and if it refuses, change nothing, stop, and tell "
             "the owner.")


def now_minute():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def holder(line):
    """(name, time) of a holder line, or None when line one is free."""
    m = HOLDER.fullmatch(line.rstrip("\r"))
    if not m or m["name"] == "nobody" or m["time"] > now_minute():
        return None
    return m["name"], m["time"]


def wait_seconds(env):
    """The wait after a claim, from env. A bad value exits 2 before any write."""
    raw = env.get(WAIT_ENV, str(DEFAULT_WAIT_SECONDS))
    try:
        wait = float(raw)
    except ValueError:
        wait = -1.0
    if not 0 <= wait < float("inf"):  # NaN fails this too
        fail(f"{WAIT_ENV}={raw!r} is not a number of seconds, 0 or more.")
    return wait


def gh_budget(wait):
    """Seconds from the start of a read to the end of its edit: half the
    wait. Another session's read and edit then both fit inside one wait, so
    its edit lands before this session's second read.
    ponytail: a wait of 0 (the self-test) means no budget."""
    return wait / 2 or None


def start_budget():
    """Start the budget for one read and the edit that follows it."""
    global DEADLINE
    DEADLINE = time.monotonic() + BUDGET if BUDGET else None


def gh(args, body=None):
    what = "gh " + " ".join(args[:3])
    left = None if DEADLINE is None else DEADLINE - time.monotonic()
    if left is not None and left <= 0:
        fail(f"{what} timed out: the read and edit budget of {BUDGET:g} "
             f"seconds is spent.")
    try:
        out = subprocess.run(["gh", *args], input=body, capture_output=True,
                             text=True, timeout=left)
    except subprocess.TimeoutExpired:
        fail(f"{what} timed out: the read and edit budget of {BUDGET:g} "
             f"seconds is spent.")
    if out.returncode != 0:
        fail(f"{what} failed: {out.stderr.strip()}")
    return out.stdout


def read(issue):
    """The issue body. Output that is not JSON with a `body` raises, and the
    handler at the bottom turns that into exit 2."""
    return json.loads(gh(["issue", "view", issue, "--json", "body"]))["body"] or ""


def write(issue, body):
    gh(["issue", "edit", issue, "--body-file", "-"], body)


def split(body):
    """(line one, the rest from its newline on)."""
    first, nl, rest = body.partition("\n")
    return first, nl + rest


def refuse(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def fail(msg):
    refuse(msg, 2)


def claim(issue, name, holder_not_live, wait):
    start_budget()
    first, rest = split(read(issue))
    held = holder(first)
    if held and held[0] != name:
        since = datetime.strptime(held[1], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        stale = datetime.now(timezone.utc) - since > timedelta(hours=HOLD_HOURS)
        if not stale:
            refuse(f"lane #{issue} is held by {held[0]}, since {held[1]}. "
                   f"Change nothing. Pick another lane.")
        if not holder_not_live:
            refuse(f"lane #{issue} is held by {held[0]}, since {held[1]}, which "
                   f"is over {HOLD_HOURS} hours old. If ListAgents does not show "
                   f"that session live, run again with --holder-not-live.")
    line = f"Held by: {name}, since {now_minute()}"
    if first.startswith("Held by:"):
        write(issue, line + rest)
    else:
        write(issue, line + "\n" + first + rest)
    time.sleep(wait)
    start_budget()  # a fresh budget for the second read, which writes nothing
    first, _ = split(read(issue))
    held = holder(first)
    if not held or held[0] != name:
        refuse(f"lane #{issue}: line one changed during the wait, to: {first}\n"
               f"You do not hold the lane. Change nothing. Pick another lane.")
    print(f"you hold lane #{issue}: {first}")


def check_holder(issue, name):
    """The body's rest, when line one is this name's holder line. Else refuse."""
    start_budget()
    first, rest = split(read(issue))
    held = holder(first)
    if not held or held[0] != name:
        refuse(f"lane #{issue}: line one is not your own holder line: {first}\n"
               f"{STOP_RULE}")
    return rest


def main(argv):
    flag = "--holder-not-live" in argv
    args = [a for a in argv if a != "--holder-not-live"]
    need = {"claim": 3, "write": 4, "release": 3}
    if not args or need.get(args[0]) != len(args) or (flag and args[0] != "claim"):
        fail(USAGE)
    global BUDGET
    wait = wait_seconds(os.environ)
    BUDGET = gh_budget(wait)
    cmd, issue, name = args[:3]
    stamp = now_minute()
    if holder(f"Held by: {name}, since {stamp}") != (name, stamp):
        fail(f"{name!r} is not a usable name for a holder line.")
    if cmd == "claim":
        claim(issue, name, flag, wait)
    elif cmd == "write":
        with open(args[3], encoding="utf-8") as fh:
            text = fh.read()
        check_holder(issue, name)
        write(issue, f"Held by: {name}, since {now_minute()}\n" + text)
        print(f"wrote lane #{issue}")
    else:
        write(issue, FREE + check_holder(issue, name))
        print(f"released lane #{issue}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as e:  # exit 1 is a refusal only, so any error is a 2
        fail(f"lane_claim.py stopped on an error: {type(e).__name__}: {e}")
