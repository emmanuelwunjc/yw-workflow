#!/usr/bin/env python3
"""Check that a PR body opens with an `## ELI5` section that holds text.

Every yw-workflow PR starts with ELI5: two or three plain sentences that say
what the change is and why it matters (.github/pull_request_template.md).
HTML comments do not count as text, so a body that keeps only the template's
hint fails. The CI job in .github/workflows/ci.yml runs this file with the
body in the PR_BODY environment variable, and exits 1 on a problem.
Self-test: hooks/pr-eli5-selftest.py.
"""
import os
import re
import sys

HEADING = "## ELI5"


def problems(body):
    text = re.sub(r"<!--.*?-->", "", body.replace("\r\n", "\n"), flags=re.S)
    lines = [l.rstrip() for l in text.split("\n")]
    content = [l for l in lines if l.strip()]
    if not content or content[0] != HEADING:
        return ["first section is not %s (found: %r)"
                % (HEADING, content[0] if content else "an empty body")]
    rest = lines[lines.index(HEADING) + 1:]
    section = []
    for l in rest:
        if re.match(r"#{1,6} ", l):
            break
        section.append(l)
    if not any(l.strip() for l in section):
        return ["ELI5 section is empty: write two or three plain sentences"]
    return []


if __name__ == "__main__":
    body = os.environ.get("PR_BODY")
    if body is None:
        print("PR_BODY is not set, so there is no PR body to check")
        sys.exit(1)
    found = problems(body)
    for p in found:
        print("PR body: " + p)
    sys.exit(1 if found else 0)
