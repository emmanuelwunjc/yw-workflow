#!/usr/bin/env python3
"""Self-test for unpushed-branches.py. Run it after any edit to that hook.

Builds a bare "origin" and a clone with four branches: one ahead with no
upstream, one pushed, one ahead with an open PR, one pushed then ahead. A fake
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

HOOK = str(pathlib.Path(__file__).with_name("unpushed-branches.py"))
HEADING = "Local branches with commits GitHub does not have and no open PR:"
GIT = shutil.which("git")
failures = []


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def commit(cwd, subject):
    sh(cwd, "git", "commit", "-q", "--allow-empty", "-m", subject)


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
        commit(clone, "local one")
        commit(clone, "local two")

        sh(clone, "git", "switch", "-q", "-c", "feat/pushed", "main")
        commit(clone, "pushed work")
        sh(clone, "git", "push", "-q", "-u", "origin", "feat/pushed")

        sh(clone, "git", "switch", "-q", "-c", "feat/has-pr", "main")
        commit(clone, "pr work")

        sh(clone, "git", "switch", "-q", "-c", "feat/behind-pr", "main")
        commit(clone, "first")
        sh(clone, "git", "push", "-q", "-u", "origin", "feat/behind-pr")
        commit(clone, "after push")
        sh(clone, "git", "switch", "-q", "main")

        prs = 'echo \'[{"headRefName":"feat/has-pr"}]\'\n'
        code, out = run_hook(clone, bin_dir(root, prs))
        expect("gh answers: only branches with no open PR, sorted", out, [
            HEADING,
            "  feat/behind-pr: 1 ahead. after push",
            "  feat/local: 2 ahead, no upstream. local two",
        ])
        expect("gh answers: exit 0", code, 0)

        unknown = [
            HEADING,
            "  feat/behind-pr: 1 ahead, PR unknown. after push",
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
                   '{"headRefName":"feat/behind-pr"}]\'\n')
        code, out = run_hook(clone, bin_dir(root, all_prs))
        expect("nothing qualifies: no output", out, [])

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
