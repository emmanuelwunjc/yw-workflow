#!/usr/bin/env python3
"""Self-test for unpushed-branches.py. Run it after any edit to that hook.

Builds a bare "origin" and a clone with these branches: one ahead with no
upstream, one pushed, one ahead with an open PR, one pushed then ahead, one
ahead of its upstream whose commits sit on another remote branch, a chain of
three review-round branches where only the tip shows, and one ahead but 15
days old. A second clone holds 12 ahead branches, to check
the 10-line cap. A fake
`gh` first on PATH answers the PR lookup. Each case compares the hook's stdout
line by line.

Run: ./hooks/unpushed-branches-selftest.py
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = str(pathlib.Path(__file__).with_name("unpushed-branches.py"))
HEADING = "Local branches with commits GitHub does not have and no open PR:"
GIT = shutil.which("git")
failures = []


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def commit(cwd, subject, days_ago=0):
    date = "@%d +0000" % (time.time() - days_ago * 86400)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", subject], cwd=cwd,
                   check=True, capture_output=True,
                   env=dict(os.environ, GIT_COMMITTER_DATE=date))


def run_hook(cwd, path):
    env = dict(os.environ, PATH=path)
    out = subprocess.run([sys.executable, HOOK], cwd=cwd, input="{}", env=env,
                         capture_output=True, text=True, timeout=30)
    return out.returncode, out.stdout.splitlines()


def expect(name, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print("       want: %r\n       got:  %r" % (want, got))
        failures.append(name)


def bin_dir(root, gh_script):
    """A PATH dir with git, and a fake gh when gh_script is given."""
    d = pathlib.Path(root, "bin-%d" % len(list(pathlib.Path(root).glob("bin-*"))))
    d.mkdir()
    (d / "git").symlink_to(GIT)
    if gh_script is not None:
        (d / "gh").write_text("#!/bin/sh\n" + gh_script)
        (d / "gh").chmod(0o755)
    return str(d)


def main():
    root = tempfile.mkdtemp()
    try:
        origin, clone = os.path.join(root, "origin.git"), os.path.join(root, "clone")
        sh(root, "git", "init", "-q", "--bare", "-b", "main", origin)
        sh(root, "git", "clone", "-q", origin, clone)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            sh(clone, "git", "config", k, v)
        commit(clone, "base")
        sh(clone, "git", "push", "-q", "-u", "origin", "main")
        commit(clone, "main local work")  # the default branch is never listed

        sh(clone, "git", "switch", "-q", "-c", "feat/local")
        commit(clone, "local one", days_ago=0.2)  # distinct dates fix the order
        commit(clone, "local two", days_ago=0.2)

        sh(clone, "git", "switch", "-q", "-c", "feat/pushed", "main")
        commit(clone, "pushed work")
        sh(clone, "git", "push", "-q", "-u", "origin", "feat/pushed")

        sh(clone, "git", "switch", "-q", "-c", "feat/has-pr", "main")
        commit(clone, "pr work", days_ago=0.1)

        sh(clone, "git", "switch", "-q", "-c", "feat/behind-pr", "main")
        commit(clone, "first")
        sh(clone, "git", "push", "-q", "-u", "origin", "feat/behind-pr")
        commit(clone, "after push")

        sh(clone, "git", "switch", "-q", "-c", "feat/elsewhere", "main")
        commit(clone, "elsewhere base")
        sh(clone, "git", "push", "-q", "-u", "origin", "feat/elsewhere")
        commit(clone, "elsewhere work")  # ahead of its upstream, but on origin/feat/other
        sh(clone, "git", "push", "-q", "origin", "feat/elsewhere:feat/other")

        for i, name in enumerate(("feat/r1", "feat/r2", "feat/tip")):  # a review-round chain
            sh(clone, "git", "switch", "-q", "-c", name, *["main"] * (i == 0))
            commit(clone, "round %d" % (i + 1), days_ago=0.05)

        sh(clone, "git", "switch", "-q", "-c", "feat/old", "main")
        commit(clone, "old work", days_ago=15)  # past the 14-day window
        sh(clone, "git", "switch", "-q", "main")

        prs = 'echo \'[{"headRefName":"feat/has-pr"}]\'\n'
        code, out = run_hook(clone, bin_dir(root, prs))
        expect("gh answers: only branches with no open PR, newest first", out, [
            HEADING,
            "  feat/behind-pr: 1 ahead. after push",
            "  feat/tip: 3 ahead, no upstream. round 3",
            "  feat/local: 2 ahead, no upstream. local two",
        ])
        expect("gh answers: exit 0", code, 0)

        unknown = [
            HEADING,
            "  feat/behind-pr: 1 ahead, PR unknown. after push",
            "  feat/tip: 3 ahead, no upstream, PR unknown. round 3",
            "  feat/has-pr: 1 ahead, no upstream, PR unknown. pr work",
            "  feat/local: 2 ahead, no upstream, PR unknown. local two",
        ]
        code, out = run_hook(clone, bin_dir(root, None))
        expect("gh missing: every ahead branch, marked PR unknown", out, unknown)
        expect("gh missing: exit 0", code, 0)

        code, out = run_hook(clone, bin_dir(root, "echo offline >&2; exit 1\n"))
        expect("gh offline: every ahead branch, marked PR unknown", out, unknown)

        code, out = run_hook(clone, bin_dir(root, 'exec %s -c "import time; time.sleep(10); print(\'[]\')"\n'
                                         % sys.executable))
        expect("gh slow: times out, marked PR unknown", out, unknown)

        all_prs = ('echo \'[{"headRefName":"feat/has-pr"},{"headRefName":"feat/local"},'
                   '{"headRefName":"feat/behind-pr"},{"headRefName":"feat/tip"}]\'\n')
        code, out = run_hook(clone, bin_dir(root, all_prs))
        expect("nothing qualifies: no output", out, [])

        many = os.path.join(root, "many")
        sh(root, "git", "clone", "-q", origin, many)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            sh(many, "git", "config", k, v)
        for i in range(1, 13):  # feat/b12 is newest
            sh(many, "git", "switch", "-q", "-c", "feat/b%02d" % i, "main")
            commit(many, "work %d" % i, days_ago=(13 - i) / 24)
        code, out = run_hook(many, bin_dir(root, "echo '[]'\n"))
        expect("12 qualify: newest 10, then the count and the command", out, [HEADING] + [
            "  feat/b%02d: 1 ahead, no upstream. work %d" % (i, i) for i in range(12, 2, -1)
        ] + ["  ... and 2 more: git for-each-ref --sort=-committerdate refs/heads"])

        outside = os.path.join(root, "not-a-repo")
        os.mkdir(outside)
        code, out = run_hook(outside, bin_dir(root, prs))
        expect("outside a git repo: no output", out, [])
        expect("outside a git repo: exit 0", code, 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print("RESULT: %d failed" % len(failures))
        sys.exit(1)
    print("RESULT: unpushed-branches self-test passes")


main()
