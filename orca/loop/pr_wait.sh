#!/bin/bash
# usage: pr_wait.sh   (read-only: gh pr list, orca worktree ps, and gh api compare per fix-review and per merge)
# The open PR check of the sweep (retro of 2026-11-24: 6 PRs sat open and waited on nobody).
# Prints one line per open twenty PR that waits on nobody, the first reason that holds:
#   WAIT <pr> conflict          GitHub says the PR conflicts with main
#   WAIT <pr> fix-review <sha>  CI passes, the PR has a review but none at its head, and a commit
#                               after <sha> (the commit the last review read) is no merge
#   WAIT <pr> no-reviewer       CI passes, and the PR has no review
#   WAIT <pr> idle              no PR activity for 3 hours, and no working agent on its branch
# A draft gets no fix-review or no-reviewer line. Neither does a PR with a working reviewer: an agent
# whose prompt, task title or workspace name says "Review (of) PR <n>" or "FIX ROUND of PR <n>", any case
# (review-spec.sh writes it first, because orca worktree ps cuts a prompt to 200 characters).
# CI passes when no check failed and no check still runs. A push of only merges of main (gh pr update-branch)
# needs no new review, also a merge that resolved a conflict (by design). A merge of any other branch needs
# a review. A PENDING (unsent) review counts as no review. All lines print at the end: on any failure it prints no WAIT
# line and exits 1. PR_WAIT_NOW=<ISO time> sets the clock, for tests. Test: bash test-pr-wait.sh
set -u
R=georgetown-mdi-gates4/twenty
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
gh pr list -R $R --state open --limit 100 \
  --json number,headRefName,headRefOid,mergeable,updatedAt,statusCheckRollup,reviews,isDraft > "$T/prs" \
  || { echo "pr_wait: gh pr list failed" >&2; exit 1; }
orca worktree ps --since 1d --json > "$T/ps" || { echo "pr_wait: orca worktree ps failed" >&2; exit 1; }
python3 -I - "$T/prs" "$T/ps" "${PR_WAIT_NOW:-}" "$R" <<'PY'
import json, re, subprocess, sys, datetime
prs, ps, now, repo = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4]
t = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
now = t(now) if now else datetime.datetime.now(datetime.timezone.utc)
IDLE = datetime.timedelta(hours=3)
working = [(w, a) for w in ps["result"]["worktrees"] for a in (w.get("agents") or []) if a.get("state") == "working"]
on_branch = {re.sub(r"^refs/heads/", "", w.get("branch") or "") for w, a in working}
# Orca names a reviewer workspace from line 1 of its spec, e.g. "Review pr 793" or "Review pr 805 fix".
MARK = re.compile(r"\b(?:review(?: of)?|fix round of) pr (\d+)\b", re.I)
reviewing = {m for w, a in working
             for text in (a.get("prompt"), a.get("taskTitle"), w.get("displayName")) for m in MARK.findall(text or "")}

def gh(path, jq):
    out = subprocess.run(["gh", "api", f"repos/{repo}/compare/{path}", "--jq", jq], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"pr_wait: gh api compare {path} failed")
    return out.stdout.strip()

def on_main(sha):
    # main is "ahead" of an ancestor of main, or "identical" to it. A branch tip that is not on main
    # gives "diverged".
    return gh(f"{sha}...main", ".status") in ("ahead", "identical")

def only_merges(base, head):
    # Compare lists every commit after base, also the commits a merge brought in.
    # Walk the first-parent line from head back to base: those are the PR's own commits.
    # It is only merges of main when each of them has 2 parents and its second parent is on main
    # (a merge of ticket-650 brings in new code). A line that does not reach base (a force push)
    # needs a review.
    by = {c["sha"]: c["parents"] for c in json.loads(gh(f"{base}...{head}", "[.commits[] | {sha, parents: [.parents[].sha]}]"))}
    own, cur = [], head
    while cur != base and cur in by:
        own.append(by[cur]); cur = by[cur][0]
    return cur == base and all(len(ps) == 2 and on_main(ps[1]) for ps in own)

OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}
lines = []
for p in sorted(prs, key=lambda p: p["number"]):
    # A PENDING review is unsent: it has no submittedAt, and it counts as no review.
    checks, n = p["statusCheckRollup"], p["number"]
    reviews = [r for r in p["reviews"] if r.get("submittedAt")]
    ci = bool(checks) and all((c.get("conclusion") or c.get("state")) in OK for c in checks)
    at_head = any((r.get("commit") or {}).get("oid") == p["headRefOid"] for r in reviews)
    wants_review = ci and not p.get("isDraft") and str(n) not in reviewing
    last = (max(reviews, key=lambda r: r["submittedAt"]).get("commit") or {}).get("oid") if reviews else None
    fix = wants_review and not at_head and last and not only_merges(last, p["headRefOid"])
    if p["mergeable"] == "CONFLICTING": why = "conflict"
    elif fix: why = f"fix-review {last}"
    elif wants_review and not reviews: why = "no-reviewer"
    elif str(n) in reviewing: continue
    elif now - t(p["updatedAt"]) > IDLE and p["headRefName"] not in on_branch: why = "idle"
    else: continue
    lines.append(f"WAIT {n} {why}")
print("\n".join(lines)) if lines else None
PY
