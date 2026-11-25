#!/usr/bin/env python3
"""Self-test for tools/pr_eli5.py, the CI check that a PR body opens with an
ELI5 section that holds text.

Each case is a PR body and the problem text it must contain. A valid case
must give no problem. It lives in hooks/ so the loop that runs every
self-test, in CI and by hand, runs it too.

Run: ./hooks/pr-eli5-selftest.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "pr_eli5.py"
spec = importlib.util.spec_from_file_location("pr_eli5", TOOL)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)

TEMPLATE = (ROOT / ".github" / "pull_request_template.md").read_text()
# The template with text after its last comment, ELI5 left as shipped. A
# greedy comment strip would eat everything from the ELI5 hint to the last
# comment and leave this text as ELI5 "text", whatever the template holds.
FILLED = TEMPLATE + "\nText after the last comment.\n"
assert TEMPLATE.lstrip().startswith("## ELI5\n"), "the PR template must open with ## ELI5"

GOOD = "## ELI5\n\nThe robot now says hello. People like hello.\n\n## What changed\n\nx\n"

CASES = [
    # name, body, problem text it must contain (None: no problem)
    ("valid", GOOD, None),
    ("valid with CRLF line ends", GOOD.replace("\n", "\r\n"), None),
    ("valid after a leading HTML comment", "<!-- note -->\n" + GOOD, None),
    ("valid heading with trailing space", GOOD.replace("## ELI5\n", "## ELI5  \n"), None),
    ("empty body", "", "first section is not ## ELI5"),
    ("no heading at all", "Fixes a thing.\n", "first section is not ## ELI5"),
    ("ELI5 is second", "## What changed\n\nx\n\n## ELI5\n\ny\n",
     "first section is not ## ELI5"),
    ("text before the ELI5 heading", "Hi.\n\n" + GOOD,
     "first section is not ## ELI5"),
    ("ELI5 as a ### heading", GOOD.replace("## ELI5", "### ELI5"),
     "first section is not ## ELI5"),
    ("ELI5 heading with other words", GOOD.replace("## ELI5", "## ELI5 summary"),
     "first section is not ## ELI5"),
    ("ELI5 holds only the template comment",
     "## ELI5\n\n<!-- Two or three plain sentences. -->\n\n## What changed\n\nx\n",
     "ELI5 section is empty"),
    ("ELI5 holds only blank lines", "## ELI5\n\n\n## What changed\n\nx\n",
     "ELI5 section is empty"),
    ("ELI5 is the whole body and empty", "## ELI5\n", "ELI5 section is empty"),
    ("ELI5 holds only a comment over two lines",
     "## ELI5\n\n<!-- Two or three\nplain sentences. -->\n\n## Why\n\nx\n",
     "ELI5 section is empty"),
    ("a leading comment, then the template as shipped",
     "<!-- note -->\n" + TEMPLATE, "ELI5 section is empty"),
    ("the PR template as shipped", TEMPLATE, "ELI5 section is empty"),
    ("the PR template with ELI5 left blank", FILLED, "ELI5 section is empty"),
    ("the PR template with ELI5 filled",
     FILLED.replace("## ELI5\n", "## ELI5\n\nThe robot says hello now.\n"), None),
]

# Every comment shape, in every place, at 1 to 5 copies. Hand-picked cases
# left a new variant of the comment strip alive each review round (a count
# limit, `[^>]*`, `.+?`). A sweep leaves no such gap between its picks.
COMMENTS = ["<!---->", "<!-- x -->", "<!-- old -> new -->", "<!-- a > b -->",
            "<!-- two\nlines -->", "<!-- a --><!-- b -->"]
for c in COMMENTS:
    for k in range(1, 6):
        lead = (c + "\n") * k
        CASES += [
            ("%d x %r before an empty ELI5" % (k, c),
             lead + "## ELI5\n\n" + c + "\n\n## Why\n\n" + c + "\nx\n",
             "ELI5 section is empty"),
            ("%d x %r around real ELI5 text" % (k, c),
             lead + "## ELI5\n\n" + c + "\nReal text.\n" + c + "\n\n## Why\n\n" + c + "\n",
             None),
            ("%d x %r inside an ELI5 that is empty" % (k, c),
             "## ELI5\n\n" + lead + "\n## Why\n\nx\n" + lead, "ELI5 section is empty"),
        ]

failures = 0
for name, body, want in CASES:
    try:
        got = pe.problems(body)
    except Exception as e:  # one crash must not hide the other cases
        got = ["crashed: %r" % e]
    ok = (got == []) if want is None else any(want in p for p in got)
    if not ok:
        failures += 1
        print("FAIL %s: want %r, got %r" % (name, want, got))

# The CI step runs the tool as a script with the body in PR_BODY. The exit
# code is what fails the job, so test it through that same entry point.
for name, body, code in [("script passes a good body", GOOD, 0),
                         ("script fails a body with no ELI5", "## Why\n\nx\n", 1),
                         ("script fails when PR_BODY is unset", None, 1)]:
    env = {k: v for k, v in os.environ.items() if k != "PR_BODY"}
    if body is not None:
        env["PR_BODY"] = body
    run = subprocess.run([sys.executable, str(TOOL)], env=env,
                         capture_output=True, text=True)
    if run.returncode != code:
        failures += 1
        print("FAIL %s: want exit %d, got %d: %s"
              % (name, code, run.returncode, run.stdout + run.stderr))

total = len(CASES) + 3
print("pr-eli5 selftest: %d/%d pass" % (total - failures, total))
sys.exit(1 if failures else 0)
