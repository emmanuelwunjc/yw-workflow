#!/usr/bin/env python3
"""At SessionStart, list local branches whose commits GitHub does not have.

On 2026-11-11 reviewed work sat on two local branches for a day, and nobody saw
it (issue #58). handoff-freshness.py looks at the current branch only. This
prints one line per local branch that is ahead of its upstream, or has no
upstream and holds commits no remote has, and has no open PR. SessionStart
stdout reaches the model.

Left out: main, master, the branch origin/HEAD names, a branch equal to its
upstream, and a branch with an open PR. The PR lookup is one `gh pr list`
call. When gh is missing, fails, or takes over 3 seconds, every ahead branch
is listed, marked "PR unknown". Prints nothing when no branch qualifies.
Always exits 0, also outside a git repo.

Self-test: ./hooks/unpushed-branches-selftest.py
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_touch import git  # noqa: E402

GH_TIMEOUT = 3
HEADING = "Local branches with commits GitHub does not have and no open PR:"
TRUNKS = {"main", "master"}
FORMAT = ("%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)"
          "%09%(contents:subject)")


def open_pr_heads():
    """Head branch names of open PRs, or None when gh cannot say."""
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "1000",
             "--json", "headRefName"],
            capture_output=True, text=True, timeout=GH_TIMEOUT)
        if out.returncode != 0:
            return None
        return {pr["headRefName"] for pr in json.loads(out.stdout)}
    except Exception:
        return None


def unpushed_counter():
    """count(sha): commits reachable from sha that no remote has. One git call
    for every branch, since one call per branch took 4.7s on 229 branches."""
    parents = {}
    for line in git("rev-list", "--parents", "--branches", "--not", "--remotes").splitlines():
        sha, *ps = line.split()
        parents[sha] = ps

    def count(tip):
        seen, stack = set(), [tip]
        while stack:
            c = stack.pop()
            if c in parents and c not in seen:
                seen.add(c)
                stack.extend(parents[c])
        return len(seen)
    return count


def main():
    trunks = TRUNKS | {git("symbolic-ref", "--short",
                           "refs/remotes/origin/HEAD").strip().partition("/")[2]}
    count = None
    ahead = []
    for line in git("for-each-ref", "--format=" + FORMAT, "refs/heads").splitlines():
        name, sha, upstream, track, subject = line.split("\t", 4)
        if name in trunks:
            continue
        if upstream and "gone" not in track:
            n = int((re.search(r"ahead (\d+)", track) or [0, 0])[1])
        else:  # no upstream, or it was deleted: count commits no remote has
            upstream = ""
            count = count or unpushed_counter()
            n = count(sha)
        if n:
            ahead.append((name, n, upstream, subject))
    if not ahead:
        return
    heads = open_pr_heads()
    lines = []
    for name, n, upstream, subject in ahead:
        if heads is not None and name in heads:
            continue
        marks = [f"{n} ahead"] + ["no upstream"] * (not upstream) + ["PR unknown"] * (heads is None)
        lines.append(f"  {name}: {', '.join(marks)}. {subject}")
    if lines:
        print("\n".join([HEADING] + lines))


if __name__ == "__main__":
    try:
        sys.stdin.read()
        main()
    except Exception:
        pass
    sys.exit(0)
