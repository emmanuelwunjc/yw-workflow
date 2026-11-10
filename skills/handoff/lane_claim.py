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

Usage, in USAGE below. Exit 0: done. Exit 1: refused, nothing changed by this run (a lost claim
leaves the winner's line). Exit 2: bad arguments or a failed `gh` call.
LANE_CLAIM_WAIT_SECONDS sets the wait after a claim (default 30).
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


def read(issue):
    out = subprocess.run(["gh", "issue", "view", issue, "--json", "body"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"gh issue view {issue} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)["body"] or ""


def write(issue, body):
    out = subprocess.run(["gh", "issue", "edit", issue, "--body-file", "-"],
                         input=body, capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"gh issue edit {issue} failed: {out.stderr.strip()}")


def split(body):
    """(line one, the rest from its newline on)."""
    first, nl, rest = body.partition("\n")
    return first, nl + rest


def refuse(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def fail(msg):
    refuse(msg, 2)


def claim(issue, name, holder_not_live):
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
    time.sleep(float(os.environ.get("LANE_CLAIM_WAIT_SECONDS", "30")))
    first, _ = split(read(issue))
    held = holder(first)
    if not held or held[0] != name:
        refuse(f"lane #{issue}: line one changed during the wait, to: {first}\n"
               f"You do not hold the lane. Change nothing. Pick another lane.")
    print(f"you hold lane #{issue}: {first}")


def check_holder(issue, name):
    """The body's rest, when line one is this name's holder line. Else refuse."""
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
    cmd, issue, name = args[:3]
    stamp = now_minute()
    if holder(f"Held by: {name}, since {stamp}") != (name, stamp):
        fail(f"{name!r} is not a usable name for a holder line.")
    if cmd == "claim":
        claim(issue, name, flag)
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
    main(sys.argv[1:])
