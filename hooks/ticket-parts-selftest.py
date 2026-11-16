#!/usr/bin/env python3
"""Self-test for tools/ticket_parts.py, the check that the issue template and
ship-loop step 1 name the same ticket parts.

Each case is a broken input and the problem text it must contain. The valid
case must give no problem. It lives in hooks/ so the loop that runs every
self-test, in CI and by hand, runs it too.

Run: ./hooks/ticket-parts-selftest.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "ticket_parts", ROOT / "tools" / "ticket_parts.py")
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)

PARTS = ["Reproduction", "Acceptance criteria", "Verification", "Mutation check"]


def template(parts):
    head = "---\nname: Ticket\nabout: x\n---\n\nSay what is wrong.\n\n"
    return head + "".join("## %s\n\ntext\n\n" % p for p in parts)


def ship_loop(parts):
    bullets = "".join("- **%s.** text\n" % p for p in parts)
    return ("# Ship loop\n\n## 1. Ticket\n\nIntro.\n\n" + bullets
            + "\nOutro.\n\n## 2. Branch\n\n- **Reproduction.** not step 1\n")


CASES = [
    # name, template text, ship-loop text, problem text it must contain
    ("valid", template(PARTS), ship_loop(PARTS), None),
    ("part dropped from the template", template(PARTS[:3]), ship_loop(PARTS),
     "template lacks: Mutation check"),
    ("part dropped from step 1", template(PARTS), ship_loop(PARTS[1:]),
     "ship-loop step 1 lacks: Reproduction"),
    ("template heading differs only in case",
     template(PARTS[:3] + ["Mutation Check"]), ship_loop(PARTS),
     "template lacks: Mutation check"),
    ("template part is a ### heading",
     template(PARTS[:3]) + "### Mutation check\n\ntext\n", ship_loop(PARTS),
     "template lacks: Mutation check"),
    ("template has no headings", "no headings here", ship_loop(PARTS),
     "found no parts in the template"),
    ("ship-loop has no step 1", template(PARTS), "# Ship loop\n",
     "found no parts in ship-loop step 1"),
]

failures = 0
for name, tmpl, ship, want in CASES:
    got = tp.problems(tmpl, ship)
    ok = (got == []) if want is None else any(want in p for p in got)
    if not ok:
        failures += 1
        print("FAIL %s: want %r, got %r" % (name, want, got))

print("ticket-parts: all %d checks pass" % len(CASES) if not failures
      else "ticket-parts: %d FAILED" % failures)
sys.exit(1 if failures else 0)
