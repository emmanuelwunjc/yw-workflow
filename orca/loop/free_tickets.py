import json, os, subprocess, sys
# The free work check of one project (twenty ticket #689, owner decisions of the #672 grill, 2026-11-23).
# Usage: free_tickets.py [--project <name>]. The repo, labels and caps come from projects.json (projects.py).
# It reads GitHub state only, never the words of an issue: labels, "blocked by" links, sub-issues,
# branches linked with `gh issue develop`, and open PRs. Output, in this order:
#   CAP: <n> open PRs ...   more than pr_cap non-draft PRs are open: nothing else is printed
#   TAKEN: #<n> <branch> [PR #<p>]  a branch linked to ticket <n>, and its open PR when it has one (slots.py reads it)
#   WORKERS: <n>/<cap>      taken tickets with no open PR yet (a linked branch that is no PR head).
#                           slots.py adds live work and prints SLOTS: the most workers the sweep may START.
#   NO SLICE: #<n>          an open ticket with no work label (labels.work, a prefix): reported, never started
#   BUSY: <path> <where>    a file that an open PR or a taken ticket's branch changes (the real diff)
#   FREE: #<n>              a ticket that may start now, best first. Every free ticket prints, so the sweep
#                           can skip one that clashes or waits on the owner and take the next (bug of 2026-11-24).
# A ticket is FREE when it is open, has a work label and no sub-issues (no tracker, no layer), no open
# blocker (the GitHub link only), none of the labels.skip labels, and is not taken: no linked branch and no
# open PR that closes it. Order: labels.first (a prefix) by number, then other work labels by number, then
# labels.last only when nothing else is free (twenty: slice:mvp-*, other slices, slice:nits).
# The sweep drops a FREE ticket that would change a BUSY file. Which files a ticket will change is known
# only to a reader of the ticket, so this script does not guess them.
# GitHub calls per run: 1 PR list, 1 paged GraphQL query, 1 compare per linked branch with no PR.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projects  # noqa: E402

NAME, _ = projects.from_argv(sys.argv[1:])
P = projects.project(NAME)
R, BASE = P["repo"], P.get("base", "main")
WORKER_CAP, PR_CAP = P["worker_cap"], P["pr_cap"]
L = P["labels"]
SKIP, SLICE, MVP, NITS = set(L.get("skip", [])), L["work"], L.get("first"), L.get("last")
QUERY = """query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        labels(first: 30) { nodes { name } }
        subIssues { totalCount }
        blockedBy(first: 20) { nodes { state } }
        linkedBranches(first: 5) { nodes { ref { name } } }
        closedByPullRequestsReferences(first: 1, includeClosedPrs: false) { totalCount }
      } } } }"""


def gh(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"free_tickets: gh {' '.join(args[:2])} failed: {out.stderr.strip()[:500]}")
    return json.loads(out.stdout)


def issues():
    owner, name = R.split("/")
    pages = gh("api", "graphql", "--paginate", "--slurp", "-F", f"owner={owner}", "-F", f"name={name}",
               "-f", "query=" + QUERY)
    errors = [e for p in pages for e in p.get("errors") or []]
    if errors:  # a ticket it could not read is never FREE
        raise SystemExit(f"free_tickets: gh api graphql failed: {errors}")
    return [i for p in pages for i in p["data"]["repository"]["issues"]["nodes"]]


def rank(labels):
    # 0: labels.first, 1: another work label, 2: labels.last (it wins over the others).
    return 2 if NITS in labels else 0 if MVP and any(l.startswith(MVP) for l in labels) else 1


def main():
    prs = gh("pr", "list", "-R", R, "--state", "open", "--limit", "200",
             "--json", "number,headRefName,files,isDraft")
    waiting = sum(not p["isDraft"] for p in prs)
    if waiting > PR_CAP:
        print(f"CAP: {waiting} open PRs, more than {PR_CAP}: start nothing")
        return
    heads = {p["headRefName"]: p["number"] for p in prs}
    busy = {f["path"]: f"PR #{p['number']}" for p in prs for f in p["files"] or []}
    workers, free = 0, []
    for i in sorted(issues(), key=lambda i: i["number"]):
        n, labels = i["number"], {l["name"] for l in i["labels"]["nodes"]}
        if i["subIssues"]["totalCount"]:
            continue
        branches = [b["ref"]["name"] for b in i["linkedBranches"]["nodes"] if b["ref"]]
        for b in branches:
            print(f"TAKEN: #{n} {b}" + (f" PR #{heads[b]}" if b in heads else ""))
        closing_pr = i["closedByPullRequestsReferences"]["totalCount"]
        no_pr = [b for b in branches if b not in heads]
        if no_pr:
            workers += 1
        for b in no_pr:
            for path in gh("api", f"repos/{R}/compare/{BASE}...{b}", "--jq", "[.files[].filename]"):
                busy.setdefault(path, f"#{n} branch {b}")
        if not any(l.startswith(SLICE) for l in labels):
            print(f"NO SLICE: #{n}")
        elif not (labels & SKIP or branches or closing_pr
                  or any(b["state"] == "OPEN" for b in i["blockedBy"]["nodes"])):
            free.append((rank(labels), n))
    print(f"WORKERS: {workers}/{WORKER_CAP}")
    for path, where in sorted(busy.items()):
        print(f"BUSY: {path} {where}")
    if any(r < 2 for r, _ in free):
        free = [f for f in free if f[0] < 2]
    for _, n in sorted(free):
        print(f"FREE: #{n}")


if __name__ == "__main__":
    sys.exit(main())
