#!/usr/bin/env python3
"""Self-test for lane_claim.py. Run it after any edit to that script.

Each case puts a fake `gh` first on PATH. The fake keeps one issue body in a
file, prints it for `gh issue view`, and stores it for `gh issue edit`. With
FAKE_GH_STEAL set, it then puts that line on line one, as another session
would that writes during the wait. With FAKE_GH_HANG set, an edit hangs
before it writes. FAKE_GH_VIEW_DELAY and FAKE_GH_EDIT_DELAY slow each call
down, and FAKE_GH_VIEW set to `nonjson`, `nobody` or `fail` breaks the view. LANE_CLAIM_WAIT_SECONDS=0 skips the wait, and one check
reads the default wait from the script, so a run never sleeps 30 seconds.

It lives in hooks/ so the loop that runs every self-test, in CI and by hand,
runs it too.

Run: ./hooks/lane-claim-selftest.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = str(HERE.parent / "skills" / "handoff" / "lane_claim.py")
HOOK = HERE / "handoff-freshness.py"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
body = os.environ["FAKE_GH_BODY"]
args = sys.argv[1:]
import time
if args[:2] == ["issue", "view"]:
    text = open(body).read()
    time.sleep(float(os.environ.get("FAKE_GH_VIEW_DELAY", "0")))
    mode = os.environ.get("FAKE_GH_VIEW")
    if mode == "fail":
        sys.exit("HTTP 401: Bad credentials")
    print("not json" if mode == "nonjson" else
          json.dumps({"title": "x"} if mode == "nobody" else {"body": text}))
elif args[:2] == ["issue", "edit"]:
    if os.environ.get("FAKE_GH_HANG"):
        time.sleep(10)
    time.sleep(float(os.environ.get("FAKE_GH_EDIT_DELAY", "0")))
    src = args[args.index("--body-file") + 1]
    text = sys.stdin.read() if src == "-" else open(src).read()
    steal = os.environ.get("FAKE_GH_STEAL")
    if steal:
        text = steal + "\n" + text.split("\n", 1)[1]
    open(body, "w").write(text)
else:
    sys.exit("fake gh: unexpected " + " ".join(args))
'''


def stop_rule():
    """The one stop rule, from the hook that owns it."""
    spec = importlib.util.spec_from_file_location("freshness", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STOP_RULE


def minute(delta_hours=0):
    t = datetime.now(timezone.utc) + timedelta(hours=delta_hours)
    return t.strftime("%Y-%m-%dT%H:%MZ")


def run(tmp, body, args, steal=None, file_text=None, env_extra=None):
    """(exit code, stderr, body after) for one run of the script."""
    body_path = pathlib.Path(tmp, "body")
    body_path.write_text(body)
    pathlib.Path(tmp, "gh").write_text(FAKE_GH)
    os.chmod(pathlib.Path(tmp, "gh"), 0o755)
    if file_text is not None:
        pathlib.Path(tmp, "next.md").write_text(file_text)
        args = args + [str(pathlib.Path(tmp, "next.md"))]
    env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
               FAKE_GH_BODY=str(body_path), LANE_CLAIM_WAIT_SECONDS="0")
    for key in [k for k in env if k.startswith("FAKE_GH_") and k != "FAKE_GH_BODY"]:
        del env[key]
    if steal:
        env["FAKE_GH_STEAL"] = steal
    env.update(env_extra or {})
    got = subprocess.run([sys.executable, SCRIPT, *args], env=env,
                         capture_output=True, text=True)
    return got.returncode, got.stderr, body_path.read_text()


def load_script():
    spec = importlib.util.spec_from_file_location("lane_claim", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    rule = stop_rule()
    rest = "\n## Next\n1. fix the wage table\n"
    mine = "Held by: me"
    old = minute(-48)
    recent = minute(-1)
    # (name, body, args, steal, file text, exit 0?, stderr must carry,
    #  body after: exact text, or a predicate)
    cases = [
        ("claim a free lane", "Held by: nobody" + rest, ["claim", "7", "me"],
         None, None, True, [],
         lambda b: b.startswith(mine + ", since ") and b.endswith(rest)),
        ("claim inserts line one when the body has none", rest.lstrip("\n"),
         ["claim", "7", "me"], None, None, True, [],
         lambda b: b.startswith(mine + ", since ") and b.endswith(rest.lstrip("\n"))),
        ("claim refused when held",
         f"Held by: other, since {recent}" + rest, ["claim", "7", "me"],
         None, None, False, [f"held by other, since {recent}"],
         f"Held by: other, since {recent}" + rest),
        ("claim lost when another name writes during the wait",
         "Held by: nobody" + rest, ["claim", "7", "me"],
         f"Held by: thief, since {recent}", None, False,
         ["line one changed during the wait", "thief"],
         f"Held by: thief, since {recent}" + rest),
        ("malformed line one counts as free (seconds in the time)",
         "Held by: other, since 2026-11-10T09:00:30Z" + rest,
         ["claim", "7", "me"], None, None, True, [],
         lambda b: b.startswith(mine + ", since ") and b.endswith(rest)
         and b.count("Held by:") == 1),
        ("malformed line one counts as free (a time in the future)",
         f"Held by: other, since {minute(5)}" + rest,
         ["claim", "7", "me"], None, None, True, [],
         lambda b: b.startswith(mine + ", since ") and b.endswith(rest)),
        ("claim over 24 hours old refused without --holder-not-live",
         f"Held by: other, since {old}" + rest, ["claim", "7", "me"],
         None, None, False, ["over 24 hours old", "--holder-not-live"],
         f"Held by: other, since {old}" + rest),
        ("claim over 24 hours old taken with --holder-not-live",
         f"Held by: other, since {old}" + rest,
         ["claim", "7", "me", "--holder-not-live"], None, None, True, [],
         lambda b: b.startswith(mine + ", since ") and b.endswith(rest)),
        ("--holder-not-live does not take a lane under 24 hours old",
         f"Held by: other, since {recent}" + rest,
         ["claim", "7", "me", "--holder-not-live"], None, None, False,
         [f"held by other, since {recent}"],
         f"Held by: other, since {recent}" + rest),
        ("write by the holder replaces the body after line one",
         f"Held by: me, since {old}" + rest, ["write", "7", "me"], None,
         "\n## Next\n1. new task\n", True, [],
         lambda b: b.startswith(mine + ", since ") and old not in b
         and b.endswith("\n## Next\n1. new task\n") and "wage" not in b),
        ("write refused when line one changed",
         f"Held by: other, since {recent}" + rest, ["write", "7", "me"], None,
         "\n## Next\n1. new task\n", False, ["not your own holder line", rule],
         f"Held by: other, since {recent}" + rest),
        ("release by the holder frees the lane",
         f"Held by: me, since {recent}" + rest, ["release", "7", "me"],
         None, None, True, [], "Held by: nobody" + rest),
        ("release refused when not holder",
         "Held by: nobody" + rest, ["release", "7", "me"], None, None, False,
         ["not your own holder line", rule], "Held by: nobody" + rest),
        ("the name nobody is refused", "Held by: nobody" + rest,
         ["claim", "7", "nobody"], None, None, False, ["not a usable name"],
         "Held by: nobody" + rest),
    ]
    # (name, env, exit code, stderr must carry). Each must exit 2 and leave
    # the body as it was (review round 8).
    free = "Held by: nobody" + rest
    env_cases = [
        ("a wait that is no number writes nothing",
         {"LANE_CLAIM_WAIT_SECONDS": "soon"}, ["LANE_CLAIM_WAIT_SECONDS"]),
        ("a negative wait writes nothing",
         {"LANE_CLAIM_WAIT_SECONDS": "-5"}, ["LANE_CLAIM_WAIT_SECONDS"]),
        ("a gh edit that hangs is a gh failure",
         {"LANE_CLAIM_WAIT_SECONDS": "1.5", "FAKE_GH_HANG": "1"}, ["timed out"]),
        # Round 9: any failure but a refusal exits 2, so step 5 stops.
        ("no gh on PATH is a failure, never a refusal",
         {"PATH": "/nonexistent-lane-claim-path"}, ["FileNotFoundError"]),
        ("gh that exits non-zero is a failure, never a refusal",
         {"FAKE_GH_VIEW": "fail"}, ["failed: HTTP 401: Bad credentials"]),
        ("gh output that is not JSON is a failure",
         {"FAKE_GH_VIEW": "nonjson"}, ["JSONDecodeError"]),
        ("gh JSON with no body is a failure",
         {"FAKE_GH_VIEW": "nobody"}, ["KeyError"]),
        # Round 9: the read and the edit share one budget of half the wait.
        # Each call here fits half the wait alone, and the two together do
        # not, so per-call timeouts, or a budget near the wait, let it write.
        # The margins are 0.6 seconds or more, for a busy machine.
        ("a read and an edit that together pass half the wait write nothing",
         {"LANE_CLAIM_WAIT_SECONDS": "3", "FAKE_GH_VIEW_DELAY": "0.9",
          "FAKE_GH_EDIT_DELAY": "0.9"}, ["timed out"]),
    ]
    for name, env, carry in env_cases:
        cases.append((name, free, ["claim", "7", "me"], None, None, 2, carry,
                      free, env))
    cases.append(("a read and an edit inside half the wait still claim",
                  free, ["claim", "7", "me"], None, None, True, [],
                  lambda b: b.startswith(mine + ", since ") and b.endswith(rest),
                  # a 1.5 second budget, so a slow start of the fake gh
                  # on a busy machine still fits
                  {"LANE_CLAIM_WAIT_SECONDS": "3"}))
    failures = 0
    # The default wait is what makes a claim see a later writer. The cases
    # above set the wait to 0, so this check is the one that sees the default.
    mod = load_script()
    wait = mod.wait_seconds({})
    if not wait >= 30:
        failures += 1
        print(f"FAIL the default wait is {wait} seconds, under 30")
    budget = mod.gh_budget(wait)
    if budget is None or not budget <= wait / 2:
        failures += 1
        print(f"FAIL the gh budget {budget} is over half the wait {wait}")
    for name, body, args, steal, file_text, ok, carry, after, *env in cases:
        with tempfile.TemporaryDirectory() as tmp:
            code, err, got = run(tmp, body, args, steal, file_text,
                                 env[0] if env else None)
        problems = []
        # ok: True means exit 0, False any other exit, an int that exit
        if (code != ok) if type(ok) is int else ((code == 0) != ok):
            problems.append(f"exit {code}")
        problems += [f"stderr lacks {c!r}" for c in carry if c not in err]
        if not (after(got) if callable(after) else got == after):
            problems.append(f"body is {got!r}")
        if problems:
            failures += 1
            print(f"FAIL {name}: {'; '.join(problems)}\n--- stderr ---\n{err}")
    print("lane-claim: all checks pass" if not failures
          else f"lane-claim: {failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
