#!/usr/bin/env python3
"""At SessionStart, list local branches with commits that no remote has.

On 2026-11-11 reviewed work sat on two local branches for a day, and nobody saw
it (issue #58). handoff-freshness.py looks at the current branch only. This
prints one line per local branch that holds commits no remote ref has (pushed
under another branch name counts as pushed), unless an open or merged PR
already has its tip. SessionStart stdout reaches the model.

Lists branches newest first, at most MAX_LINES of them, then one line with the
count of the rest.

Left out: main, master, the branch origin/HEAD names, a branch whose commits
a remote has, a branch whose tip is the head of an open or merged PR or an
ancestor of it (a PR closed unmerged does not count), and a branch whose tip
another ahead branch contains (e.g. an earlier review round of the same branch;
of two branches on one tip, the first stays). The PR lookup is one
`gh pr list` call. When gh is missing, fails, or takes over GH_TIMEOUT
seconds, no branch is left out for a PR. The other rules and the cap still
apply, and each line is marked "PR unknown".

Prints nothing when no branch qualifies, in a repo with no remote on GitHub,
and outside a git repo. When a git read fails, prints one line that says the
check could not run and why. Always exits 0.

Self-test: ./hooks/unpushed-branches-selftest.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_touch import git  # noqa: E402

# EdSim: 1000 PRs took about 1s, so a lower limit could mark every branch "PR unknown".
GH_TIMEOUT = 3
HEADING = "Local branches with commits that no remote and no open or merged PR has:"
FAILED = "Could not check local branches for unpushed work: %s"
TRUNKS = {"main", "master"}
MAX_LINES = 10
MORE = "  ... and %d more"
# One gh call pages through PRs 100 at a time. EdSim had 199 PRs on
# 2026-11-11. Past GH_TIMEOUT every branch is marked "PR unknown", so a larger
# limit only helps until it gets too slow.
PR_LIMIT = 1000
FORMAT = "%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)%09%(contents:subject)"


def pr_heads():
    """{branch name: head commits of its open or merged PRs}, or None when gh
    cannot say. A squash merge writes a new commit on main, so a merged branch
    still looks unpushed. A PR closed unmerged does not count."""
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", str(PR_LIMIT),
             "--json", "headRefName,headRefOid,state"],
            capture_output=True, text=True, timeout=GH_TIMEOUT)
        if out.returncode != 0:
            return None
        heads = {}
        for pr in json.loads(out.stdout):
            if pr["state"] in ("OPEN", "MERGED"):
                heads.setdefault(pr["headRefName"], set()).add(pr["headRefOid"])
        return heads
    except Exception:
        return None


def unpushed_reach():
    """reach(sha): the set of commits reachable from sha that no remote ref
    has. One git call for every branch, since one call per branch took 4.7s
    on 229 branches."""
    parents = {}
    for line in git("rev-list", "--parents", "--branches", "--not", "--remotes",
                    check=True).splitlines():
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


def on_github():
    """Raw remote URLs, before any insteadOf rewrite, name GitHub. Each output
    line is "key URL". Only the URL counts, so a remote named github that
    points elsewhere does not."""
    # ponytail: a substring test on the URL. A GitHub Enterprise host without
    # "github" in its name reads as off GitHub, and a URL with "github" only in
    # its path (e.g. gitlab.com/github-mirror/x) reads as on GitHub. Parse the
    # host and match a host list if either ever matters.
    return any("github" in line.partition(" ")[2].lower()
               for line in git("config", "--get-regexp", r"^remote\..*\.url$").splitlines())


def main():
    if not on_github():
        return
    trunks = TRUNKS | {git("symbolic-ref", "--short",
                           "refs/remotes/origin/HEAD").strip().partition("/")[2]}
    reach = unpushed_reach()
    ahead = []
    for line in git("for-each-ref", "--sort=refname", "--sort=-committerdate",
                    "--format=" + FORMAT, "refs/heads", check=True).splitlines():
        name, sha, upstream, track, subject = line.split("\t", 4)
        if name in trunks:
            continue
        commits = reach(sha)  # commits no remote ref has, wherever they were pushed
        if commits:
            ahead.append((name, sha, commits, upstream and "gone" not in track, subject))
    if not ahead:
        return
    heads = pr_heads()
    lines = []
    for i, (name, sha, commits, upstream, subject) in enumerate(ahead):
        # A PR has this branch's work when the tip is its head or an ancestor of
        # it. The tip is unpushed, so every commit between it and the head is
        # too, and reach(head) finds it. A head no local branch holds is
        # unknown here, so the branch stays listed.
        has_pr = heads is not None and any(
            sha == head or sha in reach(head) for head in heads.get(name, ()))
        # A review round whose tip another ahead branch contains adds nothing,
        # also when that branch has an open or merged PR. Two branches on one
        # tip: the first one stays.
        if has_pr or any(sha in other[2] and (sha != other[1] or j < i)
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
    except Exception as exc:  # noqa: BLE001 - any failure must show, never hide work
        print(FAILED % (str(exc) or type(exc).__name__))
    sys.exit(0)
