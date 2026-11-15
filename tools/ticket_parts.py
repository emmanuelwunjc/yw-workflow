"""Compare the ticket parts in the issue template with ship-loop step 1.

The template's parts are its `## ` headings. Step 1's parts are the bold lead
of each bullet, e.g. `- **Reproduction.** ...`, inside `## 1. Ticket`.
`problems()` returns one line per difference, and an empty list when both
name the same parts. tools/check-repo.py runs it on the real files.
Self-test: hooks/ticket-parts-selftest.py.
"""
import re

TEMPLATE = ".github/ISSUE_TEMPLATE/ticket.md"
SHIP_LOOP = "skills/ship-loop/SKILL.md"


def template_parts(text):
    return re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)


def step1_parts(text):
    section = text.split("\n## 1. Ticket\n", 1)
    if len(section) < 2:
        return []
    body = section[1].split("\n## ", 1)[0]
    return re.findall(r"^- \*\*(.+?)\.\*\*", body, re.MULTILINE)


def problems(template_text, ship_loop_text):
    tmpl = template_parts(template_text)
    step = step1_parts(ship_loop_text)
    out = []
    if not tmpl:
        out.append("found no parts in the template")
    if not step:
        out.append("found no parts in ship-loop step 1")
    out += ["template lacks: " + p for p in step if p not in tmpl]
    out += ["ship-loop step 1 lacks: " + p for p in tmpl if p not in step]
    return out
