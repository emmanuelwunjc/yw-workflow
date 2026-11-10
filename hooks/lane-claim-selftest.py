#!/usr/bin/env python3
"""Self-test for lane_claim.py. Run it after any edit to that script.

Each case puts a fake `gh` first on PATH. The fake keeps one issue body in a
file, prints it for `gh issue view`, and stores it for `gh issue edit`. With
FAKE_GH_STEAL set, it then puts that line on line one, as another session
would that writes during the wait. LANE_CLAIM_WAIT_SECONDS=0 skips the wait.

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
if args[:2] == ["issue", "view"]:
    print(json.dumps({"body": open(body).read()}))
elif args[:2] == ["issue", "edit"]:
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


def run(tmp, body, args, steal=None, file_text=None):
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
    env.pop("FAKE_GH_STEAL", None)
    if steal:
        env["FAKE_GH_STEAL"] = steal
    got = subprocess.run([sys.executable, SCRIPT, *args], env=env,
                         capture_output=True, text=True)
    return got.returncode, got.stderr, body_path.read_text()


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
    failures = 0
    for name, body, args, steal, file_text, ok, carry, after in cases:
        with tempfile.TemporaryDirectory() as tmp:
            code, err, got = run(tmp, body, args, steal, file_text)
        problems = []
        if (code == 0) != ok:
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
