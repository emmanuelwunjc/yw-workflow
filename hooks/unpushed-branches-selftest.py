#!/usr/bin/env python3
"""Self-test for unpushed-branches.py. Run it after any edit to that hook.

Builds a bare "origin" and a clone whose origin URL reads as GitHub (an
insteadOf rule sends it to the bare repo). A fake `gh` first on PATH answers
the PR lookup with each PR's head commit. Each case compares the hook's stdout
line by line, or checks one branch's line.

Branches in the clone: ahead with no upstream, pushed, open PR at the tip,
merged PR at the tip, closed unmerged PR, merged PR then one more commit,
open PR then one more commit, an open PR whose head only local main holds,
pushed then ahead, ahead of its upstream but on another remote branch, a
review-round chain, two branches on one tip, an upstream gone from the
remote, and `develop`, which origin/HEAD names. Other repos: 12 ahead branches for the 10-line cap, no remote, a remote off GitHub,
a git that fails on rev-list, and a folder outside any repo.

Run: ./hooks/unpushed-branches-selftest.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = str(pathlib.Path(__file__).with_name("unpushed-branches.py"))
HEADING = "Local branches with commits no remote has and no open or merged PR:"
GITHUB_URL = "https://github.com/t/t.git"
GIT = shutil.which("git")
failures = []


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(cwd, subject, days_ago=0):
    date = "@%d +0000" % (time.time() - days_ago * 86400)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", subject], cwd=cwd,
                   check=True, capture_output=True,
                   env=dict(os.environ, GIT_COMMITTER_DATE=date))


def clone(root, origin, name, github=True):
    path = os.path.join(root, name)
    sh(root, "git", "clone", "-q", origin, path)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        sh(path, "git", "config", k, v)
    if github:  # the URL reads as GitHub, and git still reaches the bare repo
        sh(path, "git", "config", "remote.origin.url", GITHUB_URL)
        sh(path, "git", "config", "url.%s.insteadOf" % origin, GITHUB_URL)
    return path


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


def bin_dir(root, gh_script, git_script=None):
    """A PATH dir with git (or a fake git), and a fake gh when gh_script is given."""
    d = pathlib.Path(root, "bin-%d" % len(list(pathlib.Path(root).glob("bin-*"))))
    d.mkdir()
    for name, script in (("gh", gh_script), ("git", git_script)):
        if script is not None:
            (d / name).write_text("#!/bin/sh\n" + script)
            (d / name).chmod(0o755)
    if git_script is None:
        (d / "git").symlink_to(GIT)
    return str(d)


def gh_says(prs):
    """A fake gh that answers with these (branch, state, head commit) PRs."""
    rows = [{"headRefName": b, "state": st, "headRefOid": oid} for b, st, oid in prs]
    return "echo '%s'\n" % json.dumps(rows)


def main():
    root = tempfile.mkdtemp()
    try:
        origin = os.path.join(root, "origin.git")
        sh(root, "git", "init", "-q", "--bare", "-b", "main", origin)
        c = clone(root, origin, "clone")
        tip = lambda ref: sh(c, "git", "rev-parse", ref)  # noqa: E731
        commit(c, "base")
        sh(c, "git", "push", "-q", "-u", "origin", "main")
        commit(c, "main local work")  # the default branch is never listed

        sh(c, "git", "switch", "-q", "-c", "develop")  # origin/HEAD names it
        sh(c, "git", "push", "-q", "-u", "origin", "develop")
        sh(c, "git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
        commit(c, "develop local work")

        sh(c, "git", "switch", "-q", "-c", "feat/local", "main")
        commit(c, "local one", days_ago=0.2)  # distinct dates fix the order
        commit(c, "local two", days_ago=0.2)

        sh(c, "git", "switch", "-q", "-c", "feat/pushed", "main")
        commit(c, "pushed work")
        sh(c, "git", "push", "-q", "-u", "origin", "feat/pushed")

        sh(c, "git", "switch", "-q", "-c", "feat/has-pr", "main")
        commit(c, "pr work", days_ago=0.1)

        sh(c, "git", "switch", "-q", "-c", "feat/behind-pr", "main")
        commit(c, "first")
        sh(c, "git", "push", "-q", "-u", "origin", "feat/behind-pr")
        commit(c, "after push")

        sh(c, "git", "switch", "-q", "-c", "feat/elsewhere", "main")
        commit(c, "elsewhere base")
        sh(c, "git", "push", "-q", "-u", "origin", "feat/elsewhere")
        commit(c, "elsewhere work")  # ahead of its upstream, but on origin/feat/other
        sh(c, "git", "push", "-q", "origin", "feat/elsewhere:feat/other")

        for i, name in enumerate(("feat/r1", "feat/r2", "feat/tip")):  # a review-round chain
            sh(c, "git", "switch", "-q", "-c", name, *["main"] * (i == 0))
            commit(c, "round %d" % (i + 1), days_ago=0.05)

        sh(c, "git", "switch", "-q", "-c", "feat/twin-a", "main")  # two branches, one tip
        commit(c, "twin work", days_ago=0.12)
        sh(c, "git", "branch", "feat/twin-b")

        sh(c, "git", "switch", "-q", "-c", "feat/gone", "main")  # upstream deleted
        commit(c, "gone one", days_ago=0.13)
        sh(c, "git", "push", "-q", "-u", "origin", "feat/gone")
        commit(c, "gone two", days_ago=0.13)
        sh(c, "git", "push", "-q", "origin", "--delete", "feat/gone")

        # PR closed unmerged / squash-merged. Distinct ages fix the order.
        for name, age in (("feat/closed", 0.15), ("feat/merged", 0.16)):
            sh(c, "git", "switch", "-q", "-c", name, "main")
            commit(c, name[5:] + " work", days_ago=age)

        sh(c, "git", "switch", "-q", "-c", "feat/merged-more", "main")
        commit(c, "merged more one", days_ago=0.17)
        merged_head = tip("HEAD")
        commit(c, "merged more two", days_ago=0.17)  # made after the merge

        sh(c, "git", "switch", "-q", "-c", "feat/open-more", "main")
        commit(c, "open base", days_ago=0.18)
        sh(c, "git", "push", "-q", "-u", "origin", "feat/open-more")
        open_head = tip("HEAD")
        commit(c, "open more", days_ago=0.18)  # not yet pushed to the open PR

        # The PR head is a later commit that only local main holds, so the
        # branch tip is an ancestor of the head, and no ahead branch contains it.
        sh(c, "git", "switch", "-q", "-c", "feat/behind-head", "main")
        commit(c, "behind head", days_ago=0.25)
        sh(c, "git", "switch", "-q", "main")
        sh(c, "git", "merge", "-q", "--ff-only", "feat/behind-head")
        commit(c, "pr head on main")

        prs = gh_says([("feat/has-pr", "OPEN", tip("feat/has-pr")),
                       ("feat/closed", "CLOSED", tip("feat/closed")),
                       ("feat/merged", "MERGED", tip("feat/merged")),
                       ("feat/merged-more", "MERGED", merged_head),
                       ("feat/open-more", "OPEN", open_head),
                       ("feat/behind-head", "OPEN", tip("main"))])
        code, out = run_hook(c, bin_dir(root, prs))
        expect("gh answers: only branches with no open or merged PR at their tip, newest first",
               out, [
                   HEADING,
                   "  feat/behind-pr: 1 ahead. after push",
                   "  feat/tip: 3 ahead, no upstream. round 3",
                   "  feat/twin-a: 1 ahead, no upstream. twin work",
                   "  feat/gone: 2 ahead, no upstream. gone two",
                   "  feat/closed: 1 ahead, no upstream. closed work",
                   "  feat/merged-more: 2 ahead, no upstream. merged more two",
                   "  feat/open-more: 1 ahead. open more",
                   "  feat/local: 2 ahead, no upstream. local two",
               ])
        expect("gh answers: exit 0", code, 0)
        names = [ln.split(":")[0].strip() for ln in out[1:]]
        expect("merged PR, then one more local commit: listed", "feat/merged-more" in names, True)
        expect("merged PR whose head is the tip: hidden", "feat/merged" in names, False)
        expect("open PR, then one unpushed local commit: listed", "feat/open-more" in names, True)
        expect("open PR whose head the tip is an ancestor of: hidden",
               "feat/behind-head" in names, False)
        expect("two branches on one tip: exactly one listed",
               [n for n in names if n.startswith("feat/twin-")], ["feat/twin-a"])
        expect("origin/HEAD names develop, which has local work: not listed",
               "develop" in names, False)
        expect("upstream gone from the remote: marked no upstream",
               "  feat/gone: 2 ahead, no upstream. gone two" in out, True)

        unknown = [
            HEADING,
            "  feat/behind-pr: 1 ahead, PR unknown. after push",
            "  feat/tip: 3 ahead, no upstream, PR unknown. round 3",
            "  feat/has-pr: 1 ahead, no upstream, PR unknown. pr work",
            "  feat/twin-a: 1 ahead, no upstream, PR unknown. twin work",
            "  feat/gone: 2 ahead, no upstream, PR unknown. gone two",
            "  feat/closed: 1 ahead, no upstream, PR unknown. closed work",
            "  feat/merged: 1 ahead, no upstream, PR unknown. merged work",
            "  feat/merged-more: 2 ahead, no upstream, PR unknown. merged more two",
            "  feat/open-more: 1 ahead, PR unknown. open more",
            "  feat/local: 2 ahead, no upstream, PR unknown. local two",
            "  ... and 1 more",  # feat/behind-head, the oldest
        ]
        code, out = run_hook(c, bin_dir(root, None))
        expect("gh missing: ahead branches, marked PR unknown", out, unknown)
        expect("gh missing: exit 0", code, 0)

        code, out = run_hook(c, bin_dir(root, "echo offline >&2; exit 1\n"))
        expect("gh offline: ahead branches, marked PR unknown", out, unknown)

        code, out = run_hook(c, bin_dir(root, 'exec %s -c "import time; time.sleep(10); print(\'[]\')"\n'
                                        % sys.executable))
        expect("gh slow: times out, marked PR unknown", out, unknown)

        all_prs = gh_says([(b, st, tip(b)) for b, st in (
            ("feat/has-pr", "OPEN"), ("feat/local", "MERGED"), ("feat/behind-pr", "OPEN"),
            ("feat/tip", "MERGED"), ("feat/closed", "OPEN"), ("feat/merged", "MERGED"),
            ("feat/twin-a", "OPEN"), ("feat/gone", "MERGED"),
            ("feat/merged-more", "MERGED"), ("feat/open-more", "OPEN"))]
                          + [("feat/behind-head", "OPEN", tip("main"))])
        code, out = run_hook(c, bin_dir(root, all_prs))
        expect("nothing qualifies: no output", out, [])

        fails_rev_list = ('case " $* " in *" rev-list "*) echo "fatal: boom" >&2; exit 128;; esac\n'
                          'exec %s "$@"\n' % GIT)
        code, out = run_hook(c, bin_dir(root, prs, fails_rev_list))
        expect("git rev-list fails: one line says the check could not run, and why", out, [
            "Could not check local branches for unpushed work: "
            "git rev-list exited 128: fatal: boom"])
        expect("git rev-list fails: exit 0", code, 0)

        many = clone(root, origin, "many")
        for i in range(1, 13):  # feat/b12 is newest
            sh(many, "git", "switch", "-q", "-c", "feat/b%02d" % i, "main")
            commit(many, "work %d" % i, days_ago=(13 - i) / 24)
        code, out = run_hook(many, bin_dir(root, "echo '[]'\n"))
        expect("12 qualify: newest 10, then the count of the rest", out, [HEADING] + [
            "  feat/b%02d: 1 ahead, no upstream. work %d" % (i, i) for i in range(12, 2, -1)
        ] + ["  ... and 2 more"])

        lone = os.path.join(root, "no-remote")
        sh(root, "git", "init", "-q", "-b", "main", lone)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            sh(lone, "git", "config", k, v)
        commit(lone, "base")
        sh(lone, "git", "switch", "-q", "-c", "feat/x")
        commit(lone, "x work")
        code, out = run_hook(lone, bin_dir(root, prs))
        expect("no remote: no output", out, [])

        off = clone(root, origin, "off-github", github=False)
        sh(off, "git", "switch", "-q", "-c", "feat/x", "main")
        commit(off, "x work")
        code, out = run_hook(off, bin_dir(root, prs))
        expect("remote is not on GitHub: no output", out, [])

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
