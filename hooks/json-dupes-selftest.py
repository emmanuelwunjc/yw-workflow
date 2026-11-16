#!/usr/bin/env python3
"""Self-test for tools/json_dupes.py, the check that hooks/hooks.json names
no key twice in one object.

Each case is an input and the problem text it must contain. The valid case
must give no problem. It lives in hooks/ so the loop that runs every
self-test, in CI and by hand, runs it too.

Run: ./hooks/json-dupes-selftest.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("json_dupes", ROOT / "tools" / "json_dupes.py")
jd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jd)

CASES = [
    # name, JSON text, problem text it must contain
    ("valid, one key name in two objects",
     '{"hooks": {"Stop": [{"matcher": "a"}], "SessionStart": [{"matcher": "a"}]}}', None),
    ("valid, two keys that differ only in case", '{"a": 1, "A": 2}', None),
    ("duplicate key at the top", '{"hooks": {}, "hooks": {}}', "duplicate key: hooks"),
    ("duplicate key two levels down",
     '{"hooks": {"SessionStart": [], "Stop": [], "SessionStart": []}}',
     "duplicate key: SessionStart"),
]

failures = 0
for name, text, want in CASES:
    got = jd.duplicate_keys(text)
    ok = (got == []) if want is None else any(want in p for p in got)
    if not ok:
        failures += 1
        print("FAIL %s: want %r, got %r" % (name, want, got))

print("json-dupes: all %d checks pass" % len(CASES) if not failures
      else "json-dupes: %d FAILED" % failures)
sys.exit(1 if failures else 0)
