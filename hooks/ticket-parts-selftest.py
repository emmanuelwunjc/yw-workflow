#!/usr/bin/env python3
"""Self-test for tools/ticket_parts.py, the check that the issue template and
ship-loop step 1 name the same ticket parts.

Each case is a broken input and the problem text it must contain. The valid
case must give no problem. It lives in hooks/ so the loop that runs every
self-test, in CI and by hand, runs it too.

Run: ./hooks/ticket-parts-selftest.py
"""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

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
    ("template names a part twice", template(PARTS + PARTS[:1]),
     ship_loop(PARTS), "template names twice: Reproduction"),
    ("step 1 names a part twice", template(PARTS),
     ship_loop(PARTS + PARTS[1:2]),
     "ship-loop step 1 names twice: Acceptance criteria"),
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



def check_repo_in_copy(drop, path=None):
    """Run tools/check-repo.py in a copy of the repo, with the text `drop`
    removed from `path` (default: the ticket template) if given. The copy gets
    a git index, because check-repo reads exec bits from it. Return (exit
    code, output)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        files = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.splitlines()
        for rel in files:
            # a symlink (e.g. skills/orca-loop) stays a symlink, or the copy loses a skill
            if (ROOT / rel).is_symlink():
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                os.symlink(os.readlink(ROOT / rel), tmp / rel)
            elif (ROOT / rel).is_file():
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, tmp / rel)
        if drop:
            f = tmp / (path or tp.TEMPLATE)
            f.write_text(f.read_text().replace(drop, ""))
        # the commit and the origin/main ref make the copy look like the trunk,
        # so the version check has a trunk to compare against and passes
        for args in (["init", "-q"], ["add", "-A"],
                     ["commit", "-q", "--no-verify", "-m", "copy"],
                     ["update-ref", "refs/remotes/origin/main", "HEAD"]):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                            "-c", "commit.gpgsign=false", *args],
                           cwd=tmp, check=True)
        run = subprocess.run([sys.executable, "tools/check-repo.py"], cwd=tmp,
                             capture_output=True, text=True)
        return run.returncode, run.stdout + run.stderr
    finally:
        shutil.rmtree(tmp)


# The cases above test the comparison. These test that check-repo.py calls it
# and acts on the result. The unchanged copy must pass, so the failure of the
# changed copy comes from the dropped heading and nothing else.
WIRED = [
    ("check-repo passes on an unchanged copy", None, None, 0,
     "RESULT: repo checks pass"),
    ("check-repo fails when a template heading is dropped",
     "## Mutation check\n", None, 1, "template lacks: Mutation check"),
    # orca/README.md must link every file under orca/ (issue #238).
    ("check-repo fails when orca/README.md drops a link",
     "(loop/stall.sh)", "orca/README.md", 1,
     "FAIL orca/README.md links loop/stall.sh"),
]
for name, drop, path, want_code, want_text in WIRED:
    code, out = check_repo_in_copy(drop, path)
    if code != want_code or want_text not in out:
        failures += 1
        print("FAIL %s: want exit %d and %r, got exit %d\n%s"
              % (name, want_code, want_text, code, out[-1500:]))

total = len(CASES) + len(WIRED)
print("ticket-parts: all %d checks pass" % total if not failures
      else "ticket-parts: %d FAILED" % failures)
sys.exit(1 if failures else 0)
