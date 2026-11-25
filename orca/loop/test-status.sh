#!/usr/bin/env bash
# Self-test for status-sync.sh. Fake orca and gh read fixtures, so nothing
# real is read or set. Each case is one workspace with its expected new status
# (- for no change).
set -u
dir=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/fix"
root="$work/ws"
export FIX="$work/fix" SET_LOG="$work/set"
# Two fake projects: alpha (root $work/ws, every case, alone in its own file) and beta (root $work/beta,
# repo o/beta) in a two-project file.
cat > "$work/projects.json" <<J
{"projects": {
  "alpha": {"repo": "o/alpha", "ws_root": "$root", "labels": {"owner_wait": "needs-owner"}},
  "beta":  {"repo": "o/beta", "ws_root": "$work/beta", "labels": {"owner_wait": "needs-owner"}}}}
J
jq '{projects: {alpha: .projects.alpha}}' "$work/projects.json" > "$work/alpha.json"
export PROJECTS_JSON=$work/alpha.json GH_LOG=$work/gh.log
# Items: the bot name comes from $BOT_HOME/bot.json. A set goes to ITEM_LOG, and
# each item move to the ledger.
mkdir -p "$work/home"; echo '{"name": "Test Bot"}' > "$work/home/bot.json"
export BOT_HOME="$work/home" ITEM_LOG="$work/items" CLEANUP_LEDGER="$work/ledger.tsv"

cat > "$work/bin/orca" <<'FAKE'
#!/usr/bin/env bash
case "$1 $2" in
  "worktree ps") jq --argjson t "${TRUNC:-false}" '.result.truncated = $t' "$FIX/ps.json" ;;
  "orchestration worker-list") # two pages; --cursor asks for page 2
    if [[ " $* " == *" --cursor="* ]]; then cat "$FIX/wl2.json"; else cat "$FIX/wl1.json"; fi ;;
  "orchestration inbox") cat "$FIX/inbox.json" ;;
  "worktree set") [[ "$4" == *fail-set ]] && exit 1; echo "$4 $6" >> "$SET_LOG" ;;
  "bot item") # list: open items of --bot "Test Bot", two pages; set: logged
    if [ "$3" = set ]; then echo "$*" >> "$ITEM_LOG"; exit; fi
    [[ " $* " == *" --bot Test Bot "* ]] || { echo '{"ok": false}'; exit 1; }
    if [[ " $* " == *" --cursor "* ]]; then cat "$FIX/items2.json"; else cat "$FIX/items1.json"; fi ;;
  *) echo "fake orca: $*" >&2; exit 1 ;;
esac
FAKE
# `gh api repos/<r>/pulls/<n>/reviews --paginate --jq <expr>` runs <expr> on
# $FIX/reviews-<n>.json. No such file: the error JSON on stdout and exit 1, as
# real gh does on an HTTP error. Any other call prints the PR list.
cat > "$work/bin/gh" <<'FAKE'
#!/bin/bash
echo "$*" >> "$GH_LOG"
# `gh issue view <n> -R <repo> --json labels,body` prints $FIX/issue-<n>.json, or
# fails as on an HTTP error when there is none.
[ "$1 $2" = "issue view" ] && { [ -f "$FIX/issue-$3.json" ] && cat "$FIX/issue-$3.json" && exit; echo "GraphQL: Could not resolve" >&2; exit 1; }
[ "$1" = api ] || { cat "$FIX/prs.json"; exit; }
n=${2%/reviews}; n=${n##*/}; q=; while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done
[ -f "$FIX/reviews-$n.json" ] || { echo '{"message":"Not Found","status":"404"}'; exit 1; }
jq "$q" "$FIX/reviews-$n.json"
FAKE
chmod +x "$work/bin/"*
export PATH="$work/bin:$PATH"

# name, old status, branch (- detached), agent states (comma list, - none),
# expected new status (- unchanged), extra jq for the ps row.
# orca worktree ps cuts each agent prompt to 200 characters.
prompt=$(printf 'You work on ticket 245 of the Orca loop. %.0s' 1 2 3 4 5 6); prompt=${prompt:0:200}
rows='[]' expect=
ws() {
  local b=$3 a=$4
  [ "$b" = - ] && b= || b="refs/heads/$b"
  [ "$a" = - ] && a=
  rows=$(jq -c --arg p "$root/$1" --arg o "$2" --arg b "$b" --arg a "$a" --arg prompt "$prompt" \
    ". + [{path: \$p, workspaceStatus: \$o, branch: (if \$b == \"\" then null else \$b end), liveTerminalCount: 1,
      agents: [\$a | split(\",\")[] | select(. != \"\") | {address: \"term_\\(\$p | split(\"/\")[-1])\", state: ., prompt: \$prompt, children: []}]} | ${6:-.}]" <<<"$rows")
  expect+="$1 $5"$'\n'
}
ws merged     in-progress b-merged  done        completed
ws detached   in-progress -         done        completed
ws openpr     in-progress b-open    done        in-review
ws openmerged in-progress b-both    done        in-review
ws working    in-progress b-merged2 done,working -
ws reopened   completed   b-merged3 working     in-progress
ws waiting    in-review   b-open2   waiting     in-progress
ws child      in-progress b-merged4 done        -           '.agents[0].children = [{state: "working", children: []}]'
ws keepdone   completed   b-open3   done        -
ws nopr-done  in-progress b-nopr    done        completed
ws nopr-idle  in-progress b-nopr2   idle        -
ws nopr-ask   in-progress b-nopr3   done        -
ws nopr-none  in-progress b-nopr4   done        -
ws nopr-dsp   in-progress b-nopr5   -           completed
ws closedpr   in-progress b-closed  done        -
ws grill-x    in-progress -         done        -
ws bothome    in-progress -         done        -           '.botHome = true'
ws mainwt     in-progress -         done        -           '.isMainWorktree = true'
ws same       completed   b-merged5 done        -
ws idlemerged in-review   b-merged6 idle        completed
# Done by kind (rule 2): a worker workspace (a dispatch on record) is completed
# only when its newest message is a worker_done with outcome succeeded, and:
# kind pr: a MERGED PR. kind report: its dispatch settled as succeeded.
# kind review: a verdict review (PASS, BLOCK n or REVIEW) on the PR its
# worker_done names. A gh error is no verdict.
ws k-prmerged  in-progress b-kpm    done        completed
ws k-prnone    in-progress b-kpn    done        -
ws k-report    in-progress b-krp    done        completed
ws k-reportfail in-progress b-krf   done        -
ws k-review    in-progress -        done        completed
ws k-reviewnone in-progress -       done        -
ws k-reviewerr in-progress -        done        -
# A review of no PR (a script or a hook): its dispatch settled as succeeded.
ws k-reviewnopr in-progress -       done        completed
# A failed worker_done, or none yet, stays as it is, even with a MERGED PR.
ws k-failed    in-progress b-kf     done        -
ws k-nodone    in-progress b-knd    done        -
# An open dispatch brings a completed workspace back to in-progress.
ws k-reopen    completed   b-kro    done        in-progress
# Outside the root, or one folder deeper: never touched.
rows=$(jq -c --arg r "$root" '. + [{path: ($r + "-other/x"), workspaceStatus: "in-progress", branch: null, agents: []},
  {path: ($r + "/a/b"), workspaceStatus: "in-progress", branch: null, agents: []}]' <<<"$rows")
jq -n --argjson w "$rows" '{result: {truncated: false, worktrees: $w}}' > "$FIX/ps.json"
jq -n '[{number: 1, headRefName: "b-merged", state: "MERGED"}, {number: 2, headRefName: "b-open", state: "OPEN"},
  {number: 3, headRefName: "b-both", state: "MERGED"}, {number: 4, headRefName: "b-both", state: "OPEN"},
  {number: 5, headRefName: "b-merged2", state: "MERGED"}, {number: 6, headRefName: "b-merged3", state: "MERGED"},
  {number: 7, headRefName: "b-open2", state: "OPEN"}, {number: 8, headRefName: "b-merged4", state: "MERGED"},
  {number: 9, headRefName: "b-open3", state: "OPEN"}, {number: 10, headRefName: "b-closed", state: "CLOSED"},
  {number: 11, headRefName: "b-merged5", state: "MERGED"}, {number: 12, headRefName: "b-merged6", state: "MERGED"},
  {number: 13, headRefName: "b-kpm", state: "MERGED"}, {number: 14, headRefName: "b-kf", state: "MERGED"},
  {number: 15, headRefName: "b-knd", state: "MERGED"}, {number: 16, headRefName: "b-kro", state: "MERGED"}]' > "$FIX/prs.json"
# Review verdicts as gh gives them: a review body starts with the decision word.
jq -n '[{body: "PASS\n## Executive TL;DR\nThe change does what the ticket asks."}]' > "$FIX/reviews-41.json"
jq -n '[{body: "Looks fine to me, PASS later."}, {body: ""}]' > "$FIX/reviews-42.json"
# Dispatches: nopr-done and nopr-idle finished by their terminal; nopr-ask asked
# after its worker_done; nopr-dsp finished by dispatch id (page 2).
# The real shape: the workspace in resource.worktreeId and projection.workspace.id,
# the settled outcome in projection.outcome (default succeeded).
wl() { jq -n --arg p "$root/$1" --arg d "$2" --arg t "$3" --arg o "${4:-succeeded}" \
  '{dispatchId: $d, agentTerminalHandle: $t, resource: {worktreeId: ("repo::" + $p)},
    projection: {outcome: $o, workspace: {id: ("repo::" + $p)}}}'; }
jq -n --argjson a "$(wl nopr-done d1 t1)" --argjson b "$(wl nopr-idle d2 t2)" --argjson c "$(wl nopr-ask d3 t3)" \
  --argjson k "$(for x in k-prmerged:11 k-prnone:12 k-report:13 k-reportfail:14:failed k-review:16 k-reviewnone:17 k-reviewerr:18 k-reviewnopr:22 \
    k-failed:21 k-nodone:19 k-reopen:20:in_progress; do IFS=: read -r w n o <<<"$x"; wl "$w" "d$n" "t$n" "$o"; done | jq -s .)" \
  '{result: {workers: ([$a, $b, $c] + $k), page: {hasMore: true, nextCursor: "p2"}}}' > "$FIX/wl1.json"
jq -n --argjson a "$(wl nopr-dsp d5 t5)" '{result: {workers: [$a], page: {hasMore: false}}}' > "$FIX/wl2.json"
# worker_done in the real shape: payload {taskId, dispatchId, outcome}, newest first.
wd() { jq -n --arg t "$1" --arg d "$2" --arg o "$3" --arg s "$4" --arg b "$5" \
  '{type: "worker_done", from_handle: $t, subject: $s, body: $b, payload: ({taskId: "task_x", dispatchId: $d, outcome: $o} | tojson)}'; }
jq -n --argjson w "$({
  wd t1 d1 succeeded done "I finished."; wd t2 d2 succeeded done "I finished."; wd t3 d3 succeeded done "I finished."
  wd tx d5 succeeded done "I finished."
  wd t11 d11 succeeded "PR 13 merged" "kind: pr. I opened PR 13 and it merged."
  wd t12 d12 succeeded "PR open soon" "kind: pr. I pushed the branch, the PR comes next."
  wd t13 d13 succeeded "report: stale workspaces" "kind: report. I read the ledger (read only) and wrote a report."
  wd t14 d14 succeeded "report: ports" "kind: report. I listed the ports."
  wd t16 d16 succeeded "review done: PR 41 adversarial PASS" "kind: review. I reviewed PR 41 at 2365483 and posted a comment review."
  wd t17 d17 succeeded "review done: PR 42 adversarial PASS" "kind: review. I reviewed PR 42 at 1a2b3c4."
  wd t18 d18 succeeded "review done: PR 43 adversarial PASS" "kind: review. I reviewed PR 43 at 5d6e7f8."
  wd t22 d22 succeeded "cleanup review: PASS" "kind: review. I reviewed cleanup.sh and load.sh in the bot home."
  wd t21 d21 failed "could not finish" "I could not rebase the branch."
} | jq -s .)" '{result: {messages: ([
  {type: "status", from_handle: "t1", payload: "{\"stopReason\":\"exited\"}"},
  {type: "question", from_handle: "t3", subject: "q", body: "Which lane?", payload: null}] + $w)}}' > "$FIX/inbox.json"

ncompleted=$(awk '$2 == "completed"' <<<"$expect" | wc -l | tr -d ' ') nset=$(awk 'NF && $2 != "-"' <<<"$expect" | wc -l | tr -d ' ')
# Items, in the real shape of `orca bot item list --json` (open items, newest
# change first, 100 a page). An item moves to done when it is In progress or
# Waiting, links at least one dispatch, and every dispatch it links is in a
# workspace that is completed after this run. Its ticket (an issues URL of the
# repo, else a title `<project> #<n>`) must be CLOSED, with no needs-owner label
# and no open box that names the owner. A gh error keeps the item. A Waiting
# item with no ticket stays: its wait names something outside the workspaces.
#   71: d11 (k-prmerged, completed now), ticket 501 closed      -> done
#   79: d11, ticket 506 still OPEN                              -> stays
#   81: d5 (nopr-dsp), Waiting, no ticket                       -> stays
#   72: d13 (k-report) and d12 (k-prnone, unchanged)            -> stays
#   73: d16 (k-review), title "alpha #502", label needs-owner   -> stays
#   74: d1 (nopr-done), ticket 503 with an open owner box       -> stays
#   75: d99, a dispatch no worker-list row names                -> stays
#   76: d11, but Needs you                                      -> stays
#   78: d13, ticket 504 that gh cannot read                     -> stays
#   80: no dispatch link                                        -> stays
#   77: d5 (nopr-dsp, completed now), In progress, no ticket, page 2 -> done
it() { jq -n --argjson n "$1" --arg s "$2" --arg t "$3" --arg u "$4" --arg r "$5" '{number: $n, status: $s, title: $t,
  links: ([$r | split(" ")[] | select(. != "") | {kind: "dispatch", ref: ., state: "completed"}]
    + [$u | select(. != "") | {kind: "url", url: ., state: null}])}'; }
gh_issue="https://github.com/o/alpha/issues"
jq -s '{result: {botName: "Test Bot", items: ., nextCursor: "c2"}}' <(
  it 71 in_progress "PR 13 work" "$gh_issue/501" d11; it 72 waiting "two workers" "" "d13 d12"
  it 73 in_progress "alpha #502 (review)" "" d16; it 74 waiting "alpha #503 (upload)" "" d1
  it 75 in_progress "lost" "" d99; it 76 needs_you "ask" "" d11; it 78 in_progress "alpha #504" "" d13
  it 80 in_progress "no worker" "$gh_issue/505" "" ; it 79 in_progress "alpha #506 (open)" "" d11) > "$FIX/items1.json"
jq -s '{result: {botName: "Test Bot", items: .}}' <(it 77 in_progress "report" "https://example.org/x" d5; it 81 waiting "spend" "" d5) > "$FIX/items2.json"
jq -n '{state: "CLOSED", labels: [{name: "slice:3"}], body: "## Acceptance\n- [x] The owner read it.\n- [ ] The code passes."}' > "$FIX/issue-501.json"
jq -n '{state: "CLOSED", labels: [{name: "needs-owner"}], body: "- [x] done"}' > "$FIX/issue-502.json"
jq -n '{state: "CLOSED", labels: [], body: "## Acceptance\n- [x] code\n- [ ] After the owner'"'"'s yes, the rule goes in."}' > "$FIX/issue-503.json"
jq -n '{state: "OPEN", labels: [], body: "- [x] code"}' > "$FIX/issue-506.json"
for n in 505; do jq -n '{state: "CLOSED", labels: [], body: ""}' > "$FIX/issue-$n.json"; done
# Fails when any case gives the wrong status, or an apply misses its line.
cases() {
  local out got name want bad=0
  out=$(bash "$1" 2>&1) || { echo "dry run exit $?: $out"; return 1; }
  while read -r name want; do
    [ -z "$name" ] && continue
    got=$(awk -v n="$name" '$1 == "SET" && $2 == n {print $5}' <<<"$out")
    [ "${got:--}" = "$want" ] || { echo "case $name: want $want, got ${got:--}"; bad=1; }
  done <<<"$expect"
  grep -q -- "-other\|SET b " <<<"$out" && { echo "touched a workspace outside the root"; bad=1; }
  grep -qx 'SET reopened completed -> in-progress (agent working or waiting)' <<<"$out" || { echo "SET line format"; bad=1; }
  grep -qx "COUNT completed $ncompleted" <<<"$out" || { echo "COUNT completed: $(grep '^COUNT completed' <<<"$out")"; bad=1; }
  rm -f "$SET_LOG"
  out=$(bash "$1" --apply 2>&1) || { echo "apply exit $?: $out"; return 1; }
  [ "$(wc -l < "$SET_LOG")" -eq "$(grep -c '^SET ' <<<"$out")" ] || { echo "apply set count"; bad=1; }
  grep -qx "path:$root/reopened in-progress" "$SET_LOG" || { echo "apply missed reopened"; bad=1; }
  tail -1 <<<"$out" | grep -qx "DONE $nset set, 0 failed" || { echo "DONE line: $(tail -1 <<<"$out")"; bad=1; }
  # Items: one ITEM line per item that moves, one ITEM-KEEP line per owner hold.
  rm -f "$ITEM_LOG"; out=$(bash "$1" 2>&1)
  [ "$(grep '^ITEM ' <<<"$out" | sort)" = "$(printf '%s\n' 'ITEM 71 done (k-prmerged)' 'ITEM 77 done (nopr-dsp)')" ] || { echo "ITEM lines:"; grep '^ITEM' <<<"$out"; bad=1; }
  [ "$(grep '^ITEM-KEEP ' <<<"$out" | cut -d' ' -f2 | sort | tr '\n' ' ')" = "73 74 78 79 81 " ] || { echo "ITEM-KEEP lines:"; grep '^ITEM-KEEP' <<<"$out"; bad=1; }
  [ -e "$ITEM_LOG" ] && { echo "a dry run set an item"; bad=1; }
  rm -f "$SET_LOG" "$CLEANUP_LEDGER"
  out=$(bash "$1" --apply 2>&1)
  [ "$(sort "$ITEM_LOG" 2>/dev/null | cut -d' ' -f3-5 | tr '\n' ' ')" = "set 71 --status set 77 --status " ] && [ "$(grep -c -- '--status done' "$ITEM_LOG")" = 2 ] || { echo "item sets:"; cat "$ITEM_LOG" 2>/dev/null; bad=1; }
  [ "$(awk -F'\t' '$4 == "item-done" && $7 == "ok" && $10 == "done" {print $5}' "$CLEANUP_LEDGER" 2>/dev/null | sort | tr '\n' ' ')" = "item 71 item 77 " ] || { echo "item ledger lines:"; cat "$CLEANUP_LEDGER" 2>/dev/null; bad=1; }
  rm -f "$SET_LOG" "$ITEM_LOG"
  out=$(bash "$1" --apply merged openpr 2>&1)
  [ "$(sort "$SET_LOG" | tr '\n' ' ')" = "path:$root/merged completed path:$root/openpr in-review " ] || { echo "names limit"; bad=1; }
  out=$(TRUNC=true bash "$1" 2>&1) && { echo "ran on truncated ps"; bad=1; }
  # Projects (#244): the root is the named project's ws_root, and two projects need a name.
  out=$(PROJECTS_JSON=$work/projects.json bash "$1" 2>&1) && { echo "ran with two projects and no --project"; bad=1; }
  : > "$GH_LOG"; out=$(PROJECTS_JSON=$work/projects.json bash "$1" --project beta 2>&1) || { echo "--project beta exit $?: $out"; bad=1; }
  grep -q '^SET ' <<<"$out" && { echo "--project beta set a workspace of alpha's root"; bad=1; }
  grep -q 'o/alpha' "$GH_LOG" && { echo "--project beta read alpha's repo"; bad=1; }
  grep -q -- '-R o/beta' "$GH_LOG" || { echo "--project beta did not read beta's repo"; bad=1; }
  out=$(PROJECTS_JSON=$work/projects.json bash "$1" --all-projects 2>&1) || { echo "--all-projects exit $?: $out"; bad=1; }
  [ "$(grep '^PROJECT ' <<<"$out" | tr '\n' ' ')" = "PROJECT alpha PROJECT beta " ] || { echo "--all-projects PROJECT lines: $(grep '^PROJECT' <<<"$out")"; bad=1; }
  grep -qx 'SET reopened completed -> in-progress (agent working or waiting)' <<<"$out" || { echo "--all-projects missed alpha's sets"; bad=1; }
  PROJECTS_JSON=$work/projects.json bash "$1" --all-projects merged >/dev/null 2>&1 && { echo "--all-projects took a workspace name"; bad=1; }
  rm -f "$SET_LOG"; PROJECTS_JSON=$work/projects.json bash "$1" --all-projects --apply >/dev/null 2>&1
  grep -qx "path:$root/reopened in-progress" "$SET_LOG" 2>/dev/null || { echo "--all-projects --apply set nothing"; bad=1; }
  return $bad
}

if ! cases "$dir/status-sync.sh"; then echo "FAIL"; exit 1; fi
# A failed set is reported and exits 1.
ws fail-set in-progress b-merged done completed
jq --argjson w "$rows" '.result.worktrees = $w' "$FIX/ps.json" > "$FIX/ps2" && mv "$FIX/ps2" "$FIX/ps.json"
out=$(bash "$dir/status-sync.sh" --apply 2>&1) && { echo "FAIL: a failed set exits 0"; exit 1; }
grep -qx 'FAILED fail-set' <<<"$out" && tail -1 <<<"$out" | grep -qx "DONE $nset set, 1 failed" || { echo "FAIL: failed set lines: $out"; exit 1; }
jq --arg p "$root/fail-set" '.result.worktrees |= map(select(.path != $p))' "$FIX/ps.json" > "$FIX/ps2" && mv "$FIX/ps2" "$FIX/ps.json"

echo "PASS: $(grep -c . <<<"$expect") cases"
