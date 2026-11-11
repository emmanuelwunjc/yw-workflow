#!/usr/bin/env python3
"""At SessionStart, list local branches whose commits GitHub does not have.

On 2026-11-11 reviewed work sat on two local branches for a day, and nobody saw
it (issue #58). handoff-freshness.py looks at the current branch only. This
prints one line per local branch that holds commits no remote ref has (pushed
under another branch name counts as pushed), and has no open or merged PR.
SessionStart stdout reaches the model.

Shows branches whose last commit is at most MAX_AGE_DAYS old, newest first,
at most MAX_LINES of them, then one line with the count of the rest.

Left out: main, master, the branch origin/HEAD names, a branch whose commits
a remote has, a branch with an open or merged PR (a PR closed unmerged does
not count), and a branch whose tip another ahead branch contains (e.g. an
earlier review round of the same lane). The PR lookup is one `gh pr list`
call. When gh is missing, fails, or takes over 3 seconds, every ahead branch
is listed, marked "PR unknown". Prints nothing when no branch qualifies.
Always exits 0, also outside a git repo.

Self-test: ./hooks/unpushed-branches-selftest.py
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_touch import git  # noqa: E402

GH_TIMEOUT = 3
HEADING = "Local branches with commits GitHub does not have and no open or merged PR:"
TRUNKS = {"main", "master"}
# Reviewed work left unpushed shows up within days. Older ahead branches are
# mostly finished review rounds and squash-merged lanes: 124 of them on EdSim
# hid the two that mattered, so they are left out.
MAX_AGE_DAYS = 14
MAX_LINES = 10
MORE = "  ... and %d more"
# One gh call pages through PRs 100 at a time. EdSim had 199 PRs on
# 2026-11-11 and 1000 took about 1s. Past GH_TIMEOUT every branch is marked
# "PR unknown", so a larger limit only helps until it gets too slow.
PR_LIMIT = 1000
FORMAT = ("%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)"
          "%09%(committerdate:unix)%09%(contents:subject)")


def pr_heads():
    """Head branch names of open or merged PRs, or None when gh cannot say.
    A squash merge writes a new commit on main, so a merged branch still
    looks unpushed. A PR closed unmerged does not count."""
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", str(PR_LIMIT),
             "--json", "headRefName,state"],
            capture_output=True, text=True, timeout=GH_TIMEOUT)
        if out.returncode != 0:
            return None
        return {pr["headRefName"] for pr in json.loads(out.stdout)
                if pr["state"] in ("OPEN", "MERGED")}
    except Exception:
        return None


def unpushed_reach():
    """reach(sha): the set of commits reachable from sha that no remote ref
    has. One git call for every branch, since one call per branch took 4.7s
    on 229 branches."""
    parents = {}
    for line in git("rev-list", "--parents", "--branches", "--not", "--remotes").splitlines():
        sha, *ps = line.split()
        parents[sha] = ps

    def reach(tip):
        seen, stack = set(), [tip]
        while stack:
            c = stack.pop()
            if c in parents and c not in seen:
                seen.add(c)
                stack.extend(parents[c])
        return seen
    return reach


def main():
    trunks = TRUNKS | {git("symbolic-ref", "--short",
                           "refs/remotes/origin/HEAD").strip().partition("/")[2]}
    reach = unpushed_reach()
    oldest = time.time() - MAX_AGE_DAYS * 86400
    ahead = []
    for line in git("for-each-ref", "--sort=refname", "--sort=-committerdate",
                    "--format=" + FORMAT, "refs/heads").splitlines():
        name, sha, upstream, track, date, subject = line.split("\t", 5)
        if name in trunks or int(date) < oldest:
            continue
        commits = reach(sha)  # commits no remote ref has, wherever they were pushed
        if commits:
            ahead.append((name, sha, commits, upstream and "gone" not in track, subject))
    if not ahead:
        return
    heads = pr_heads()
    lines = []
    for i, (name, sha, commits, upstream, subject) in enumerate(ahead):
        # A review round whose tip another ahead branch contains adds nothing,
        # also when that branch has an open or merged PR. Two branches on one tip: the
        # first one stays.
        if (heads is not None and name in heads) or any(
                sha in other[2] and (sha != other[1] or j < i)
                for j, other in enumerate(ahead) if j != i):
            continue
        marks = ([f"{len(commits)} ahead"] + ["no upstream"] * (not upstream)
                 + ["PR unknown"] * (heads is None))
        lines.append(f"  {name}: {', '.join(marks)}. {subject}")
    if lines:
        more = [MORE % (len(lines) - MAX_LINES)] * (len(lines) > MAX_LINES)
        print("\n".join([HEADING] + lines[:MAX_LINES] + more))


if __name__ == "__main__":
    try:
        sys.stdin.read()
        main()
    except Exception:
        pass
    sys.exit(0)
