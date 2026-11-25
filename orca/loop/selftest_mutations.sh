#!/bin/bash
# Proves selftest_free.sh can fail: each line removes one rule of the free work check (ticket #689)
# in a temp copy (../mutate.sh), and selftest_free.sh must catch it. Prints `caught:` per rule.
D=$(cd "$(dirname "$0")" && pwd); M="$D/../mutate.sh"; fail=0
m() { bash "$M" "$D" "$1" selftest_free.sh "$2" "$3" "$4" || fail=1; }
P=free_tickets.py
m $P 'print(f"NO SLICE: #{n}")' 'pass' 'no-slice-line'
m $P 'if not any(l.startswith(SLICE) for l in labels):' 'if False:' 'slice-label-required'
m $P 'any(b["state"] == "OPEN" for b in i["blockedBy"]["nodes"])' 'False' 'open-blocker'
for l in needs-owner wayfinder:grilling wayfinder:map deferred slice:later-slices tracker; do
  m $P "\"$l\"" '"x-none"' "skip-label-$l"
done
m $P 'if i["subIssues"]["totalCount"]:' 'if False:' 'tracker-or-layer'
m $P 'labels & SKIP or branches or closing_pr' 'labels & SKIP or closing_pr' 'taken-linked-branch'
m $P 'labels & SKIP or branches or closing_pr' 'labels & SKIP or branches' 'taken-closing-pr'
m $P 'busy = {f["path"]: f"PR #{p['"'"'number'"'"']}" for p in prs for f in p["files"] or []}' 'busy = {}' 'busy-pr-files'
m $P 'busy.setdefault(path, f"#{n} branch {b}")' 'pass' 'busy-branch-diff'
m $P 'else 0 if any(l.startswith(MVP) for l in labels) else 1' 'else 1' 'mvp-first'
m $P 'return 2 if NITS in labels else' 'return' 'nits-rank'
m $P 'if any(r < 2 for r, _ in free):' 'if False:' 'nits-wait'
m $P 'for _, n in sorted(free):' 'for _, n in sorted(free)[:max(0, WORKER_CAP - workers)]:' 'every-free-line-prints'
m $P 'workers += 1' 'pass' 'worker-count'
m $P 'no_pr = [b for b in branches if b not in heads]' 'no_pr = [b for b in branches if True]' 'pr-head-not-a-worker'
m $P 'if waiting > PR_CAP:' 'if False:' 'pr-cap'
m $P 'waiting = sum(not p["isDraft"] for p in prs)' 'waiting = len(prs)' 'drafts-not-counted'
m $P 'if errors:' 'if False:' 'graphql-error-stops'
m $P 'for p in pages for i in' 'for p in pages[:1] for i in' 'all-pages-read'
m precheck.sh "grep -q '^FREE: #'" 'true' 'precheck-needs-free'
m precheck.sh 'exit 0; }' 'exit 1; }' 'precheck-error-passes'
m $P 'WORKER_CAP, PR_CAP = 8, 6' 'WORKER_CAP, PR_CAP = 6, 6' 'worker-cap-8'
m $P 'print(f"TAKEN: #{n} {b}" + ' 'pass; (' 'taken-lines'
m $P '+ (f" PR #{heads[b]}" if b in heads else "")' '' 'taken-marks-pr-branch'
m precheck.sh "grep -q '^SLOTS: [1-9]'" 'true' 'precheck-needs-slot'
S=slots.py
m $S 'int(m[2]) - (int(m[1]) - len(freed)) - len(names)' 'int(m[2]) - len(names)' 'slots-count-workers'
m $S 'int(m[2]) - (int(m[1]) - len(freed)) - len(names)' 'int(m[2]) - (int(m[1]) - len(freed))' 'slots-count-live'
m $S 'int(m[2]) - (int(m[1]) - len(freed)) - len(names)' 'int(m[2]) - int(m[1]) - len(names)' 'dead-frees-slot'
m $S 'if held or n in own or' 'if held or' 'slot-own-link-held'
m slot.sh 'slots.py" "$@"' 'slots.py"' 'slot-passes-own-ticket'
m $S 'or branch in taken' '' 'live-skips-taken-branch'
m $S '(not path.startswith(WS) or branch' '(branch' 'live-twenty-only'
m $S 'if not w.get("isArchived")' 'if True' 'live-skips-archived'
m $S 'or re.match(r"review\b", w.get("displayName") or "", re.I)' '' 'live-skips-review-name'
m $S 'or branch.split("/")[-1].startswith("review")' '' 'live-skips-review-branch'
m $S 'a.get("state") == "working" and not REVIEW' 'True and not REVIEW' 'live-working-only'
m $S 'and not REVIEW.search(title(a))' '' 'live-skips-review-title'
m $S 'if ps.get("truncated") and len' 'if False and len' 'truncated-ps-stops'
m $S 'len(ps["worktrees"]) < ps.get("totalCount", float("inf"))' 'True' 'omitted-host-not-cut'
m $S 'for d in LOCK_DIRS' 'for d in [LOCKS]' 'other-home-locks'
m $S 'print(f"DEAD: #{n} {b}")' 'pass' 'dead-lines'
m $S 'a.get("state") == "working" and (w in on_branch' 'False and (w in on_branch' 'dead-working-agent-keeps'
m $S 'a.get("state") == "working" and (w in on_branch' 'True and (w in on_branch' 'dead-done-agent-does-not-keep'
m $S 'w in on_branch or re.search(rf"#{n}\b", title(a))' 'w in on_branch' 'dead-named-ticket-keeps'
m $S 'any(w.get("terminalVerdict") == "live" for w in on_branch) or ' '' 'dead-live-terminal-keeps'
m $S 'if not os.path.isdir(LOCKS):' 'if False:' 'missing-locks-folder-stops'
m $S 'if set(sys.argv[1:]) - set(taken.values()):' 'if False:' 'slots-rejects-untaken-ticket'
m slot.sh '[ $# = 1 ] ||' 'true ||' 'slot-needs-one-ticket'
m $S '< LOCK_SECS' '< 0' 'dead-fresh-lock-keeps'
m $S '< LOCK_SECS' '< 10**9' 'dead-old-lock-does-not-keep'
m $S 'if out.returncode:' 'if False:' 'orca-failure-stops'
m slot.sh '[ "$s" -ge 0 ]' 'true' 'slot-stops-over-cap'
m slot.sh '[ "$s" -ge 0 ]' '[ "$s" -gt 0 ]' 'slot-own-branch-counted'
[ $fail = 0 ] && echo "selftest_mutations ok"
exit $fail
