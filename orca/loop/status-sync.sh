#!/usr/bin/env bash
# Set the Orca sidebar status (workspaceStatus) of each workspace under the
# project's ws_root from what is on record.
# Usage: status-sync.sh [--project <name> | --all-projects] [--apply] [workspace...]
# The ws_root, repo and labels.owner_wait come from projects.json (projects.py).
# --all-projects runs once per project, each run after a `PROJECT <name>` line,
# and takes no workspace names. Dry run by default: one line per change,
# `SET <ws> <old> -> <new> (<why>)`. --apply runs
# `orca worktree set --worktree path:<dir> --workspace-status <new>` for each
# SET line, 8 at a time, and ends with `DONE <n> set, <m> failed`.
# Names after the flags limit the run to those workspaces (cleanup.sh --apply
# passes the ones it closed).
# The rule, first match wins:
#   bot home, main worktree, grill-*      -> unchanged
#   an agent in a state not done or idle  -> in-progress
#   an open dispatch (outcome in_progress) -> in-progress (also from completed)
#   already completed                     -> unchanged (never downgraded)
#   branch with an OPEN PR                -> in-review
#   no dispatch on record (no worker):
#     detached HEAD or a MERGED PR        -> completed
#   a worker workspace (a dispatch on record) is Done only when the newest
#   worker message of the workspace (worker_done, question, escalation, status)
#   is a worker_done with outcome succeeded, and by the `kind:` its body starts with:
#     kind: pr      a MERGED PR           -> completed
#     kind: report  its dispatch settled as succeeded -> completed
#     kind: review  a review on the PR its worker_done names starts with the
#                   decision word (PASS, BLOCK n, REVIEW) -> completed (one gh call)
#                   no PR named (a review of a script): its dispatch settled
#                   as succeeded -> completed
#     no kind line: detached HEAD, a MERGED PR, or no PR and every agent done
#                                         -> completed
#   anything else                         -> unchanged
# Items (the owner reads items, so an item follows its workspaces): after the
# sets, an open item of the bot (BOT_HOME/bot.json names it) moves to done,
# `ITEM <n> done (<workspaces>)`, when all of these hold:
#   its status is In progress or Waiting (Needs you and Planned stay),
#   it links at least one dispatch, and every dispatch it links is in a
#   workspace of this root that is completed after this run,
#   its ticket (an issues URL of the repo, else a title `<project> #<n>`) is
#   CLOSED, with no labels.owner_wait label (e.g. needs-owner) and no open `- [ ]` box that
#   names the owner,
#   a Waiting item has a ticket: with none, its wait names something outside
#   the workspaces (a spend manifest, an owner's "not yet"), which no rule here sees.
# Any other item, or a ticket gh cannot read, gets `ITEM-KEEP <n> (<why>)`.
# --apply runs `orca bot item set <n> --status done --comment <why>` once per
# item, and appends one ledger line per item (CLEANUP_LEDGER, the cleanup.sh
# format, action item-done). `orca bot item list --link` matches only a PR, URL
# or file, never a dispatch, so the script reads the open items once and
# matches the dispatch links itself.
# Inputs: the pages of `orca bot item list`, one `gh issue view` per item with a
# ticket that may move, one `orca worktree ps` call, one `gh pr list` call, the pages of
# `orca orchestration worker-list` (dispatch -> workspace), one
# `orca orchestration inbox` call, and one `gh api .../pulls/<n>/reviews` call
# per kind: review candidate. No git call: the branch comes from ps.
set -euo pipefail
LOOP=$(cd "$(dirname "$0")" && pwd); . "$LOOP/project.sh" "$@"; set -- ${ARGS[@]+"${ARGS[@]}"}
apply=0
[ "${1:-}" = --apply ] && { apply=1; shift; }
case "${1:-}" in -*) echo "usage: $0 [--project <name> | --all-projects] [--apply] [workspace...]" >&2; exit 2 ;; esac
if [ "$ALL_PROJECTS" = 1 ]; then
  [ $# = 0 ] || { echo "--all-projects takes no workspace names" >&2; exit 2; }
  rc=0 flag= names=$(pall) || exit 2
  [ "$apply" = 1 ] && flag=--apply
  for p in $names; do echo "PROJECT $p"; bash "$0" --project "$p" $flag || rc=1; done
  exit $rc
fi
# The root is the project's ws_root: a script reads no other root (it replaced STATUS_SYNC_ROOTS, #244).
root=$(pget ws_root)
repo=$(pget repo)
ledger=${CLEANUP_LEDGER:-$BOT_HOME/logs/ledger.tsv}; mkdir -p "$(dirname "$ledger")"
kind=${CLEANUP_KIND:-manual}
project=$PROJECT
owner_label=$(pget labels.owner_wait)

ps_json=$(orca worktree ps --json --limit 100000)
[ "$(jq -r '.result.truncated' <<<"$ps_json")" = false ] || { echo "orca worktree ps output is truncated, so a working agent can hide. Stop." >&2; exit 1; }
workers='[]' cursor=
while :; do
  page=$(orca orchestration worker-list --json --full --limit 100 ${cursor:+--cursor="$cursor"})
  workers=$(jq -cs '.[0] + .[1].result.workers' <(printf '%s' "$workers") - <<<"$page")
  cursor=$(jq -r 'if .result.page.hasMore then .result.page.nextCursor else empty end' <<<"$page")
  [ -n "$cursor" ] || break
done
mail=$(orca orchestration inbox --json --full --limit 100000)
prs=$(gh pr list -R "$repo" --state all --limit 100000 --json number,headRefName,state)

# name TAB old TAB new TAB why, one line per workspace whose status changes.
rows=$(jq -nr --arg root "${root%/}" --arg only "$*" \
  --slurpfile ps <(printf '%s' "$ps_json") --slurpfile d <(printf '%s' "$workers") \
  --slurpfile mail <(printf '%s' "$mail") --slurpfile prs <(printf '%s' "$prs") '
  $mail[0].result.messages as $m | ($only | split(" ") | map(select(. != ""))) as $only
  | def dpath: (.resource.worktreeId // .projection.workspace.id // "") | split("::")[1] // "";
    def did: (.payload // "{}") | fromjson | .dispatchId // empty;
    def nostop: (.payload // "{}") | fromjson | has("stopReason") | not;
  $ps[0].result.worktrees[]
  | select(.path | startswith($root + "/")) | select(.path[($root | length) + 1:] | contains("/") | not)
  | (.path | split("/")[-1]) as $name
  | select(($only | length) == 0 or IN($only[]; $name))
  | .path as $p | (.workspaceStatus // "") as $old
  | [.agents[]? | recurse(.children[]?) | .state] as $states
  | ((.branch // "") | sub("^refs/heads/"; "")) as $branch
  | [$prs[0][] | select($branch != "" and .headRefName == $branch) | .state] as $pr
  | [$d[0][] | select(dpath == $p)] as $mine
  | [$mine[].agentTerminalHandle] as $handles | [$mine[].dispatchId] as $ids
  | ([$m[] | select(.type | IN("worker_done", "question", "escalation", "status"))
       | select(nostop) | select(IN(.from_handle; $handles[]) or IN(did; $ids[]))][0] // {}) as $last
  | ($last.type == "worker_done" and (($last.payload // "{}") | fromjson | .outcome) == "succeeded") as $fin
  | (($last.body // "") | capture("\\Akind: (?<k>pr|report|review)\\b").k // "") as $kind
  | ([$last | did][0] // $ids[0]) as $lastid
  | any($mine[]; .dispatchId == $lastid and .projection.outcome == "succeeded") as $settled
  | ([[$last.subject, $last.body][] // "" | capture("\\bPR #?(?<n>[0-9]+)").n][0] // "") as $prn
  | (if .botHome or .isMainWorktree then null
     elif ($name | startswith("grill")) then null
     elif any($states[]; IN("done", "idle") | not) then ["in-progress", "agent working or waiting"]
     elif any($mine[]; .projection.outcome == "in_progress") then ["in-progress", "open dispatch"]
     elif $old == "completed" then null
     elif IN($pr[]; "OPEN") then ["in-review", "OPEN PR"]
     elif ($mine | length) == 0 then (if $branch == "" then ["completed", "detached"] elif IN($pr[]; "MERGED") then ["completed", "MERGED PR"] else null end)
     elif $fin | not then null
     elif $kind == "pr" then (if IN($pr[]; "MERGED") then ["completed", "kind pr, MERGED PR"] else null end)
     elif $kind == "report" then (if $settled then ["completed", "kind report, settled"] else null end)
     elif $kind == "review" then (if $prn != "" then ["?review", $prn] elif $settled then ["completed", "kind review of no PR, settled"] else null end)
     elif $branch == "" then ["completed", "detached, worker_done"]
     elif IN($pr[]; "MERGED") then ["completed", "MERGED PR, worker_done"]
     elif ($pr | length) == 0 and all($states[]; . == "done") then ["completed", "no PR, worker_done"]
     else null end) as $new
  | select($new != null and $new[0] != $old)
  | [$name, ($old | if . == "" then "-" else . end), $new[0], $new[1]] | @tsv')
# A kind: review worker is Done when its verdict is on the PR: a review whose
# body starts with the decision word. A gh error (its JSON on stdout, exit 1)
# is no verdict, so the workspace stays as it is.
# ponytail: any verdict review on the PR counts, not only this worker's. Match
# the review's commit_id to the workspace HEAD if two reviewers share one PR.
review=$(awk -F'\t' '$3 == "?review"' <<<"$rows") rows=$(awk -F'\t' '$3 != "?review"' <<<"$rows")
while IFS=$'\t' read -r name old _ n; do
  [ -n "$name" ] || continue
  c=$(gh api "repos/$repo/pulls/$n/reviews" --paginate --jq '[.[] | select((.body // "") | test("\\A\\s*(PASS|BLOCK [0-9]+|REVIEW)\\b"))] | length' 2>/dev/null) || continue
  [ "$(awk '{s += $1} END {print s + 0}' <<<"$c")" -gt 0 ] && rows+=$'\n'"$name"$'\t'"$old"$'\tcompleted\tkind review, verdict on PR '"$n"
done <<<"$review"
rows=$(grep . <<<"$rows" || true)

[ -n "$rows" ] && awk -F'\t' '{print "SET " $1 " " $2 " -> " $3 " (" $4 ")"}' <<<"$rows"
for s in in-progress in-review completed; do
  echo "COUNT $s $(awk -F'\t' -v s="$s" '$3 == s' <<<"$rows" | grep -c . || true)"
done
items_sync() { # the names of the workspaces whose set failed -> ITEM lines; with --apply, the sets
  local bot items page cur done_paths irows n from names t iss why itemfail=0
  bot=$(jq -r '.name // empty' "$BOT_HOME/bot.json" 2>/dev/null) || true
  [ -n "$bot" ] || { echo "NOTE no bot name in $BOT_HOME/bot.json: items not synced"; return 0; }
  items='[]' cur=
  while :; do
    page=$(orca bot item list --bot "$bot" --json --limit 100 ${cur:+--cursor "$cur"})
    items=$(jq -cs '.[0] + .[1].result.items' <(printf '%s' "$items") - <<<"$page")
    cur=$(jq -r '.result.nextCursor // empty' <<<"$page")
    [ -n "$cur" ] || break
  done
  # The workspace names of the root that are completed after this run: completed in
  # ps and not set to another status, or set to completed now (and not failed).
  done_paths=$(jq -r --arg root "${root%/}" '.result.worktrees[] | select(.path | startswith($root + "/"))
    | [(.path | split("/")[-1]), (.workspaceStatus // "-")] | @tsv' <<<"$ps_json" \
    | awk -F'\t' -v fail=" $1 " 'NR == FNR {new[$1] = $3; next} {s = ($1 in new) ? new[$1] : $2}
        s == "completed" && index(fail, " " $1 " ") == 0 {print $1}' <(printf '%s\n' "$rows") -)
  # number TAB status TAB workspaces TAB ticket, one line per item that may move.
  irows=$(jq -nr --arg root "${root%/}" --arg repo "$repo" --arg project "$project" --arg done "$done_paths" \
    --slurpfile items <(printf '%s' "$items") --slurpfile d <(printf '%s' "$workers") '
    def dpath: (.resource.worktreeId // .projection.workspace.id // "") | split("::")[1] // "";
    ($done | split("\n") | map($root + "/" + .)) as $done
    | ([$d[0][] | {key: .dispatchId, value: dpath}] | from_entries) as $where
    | $items[0] | unique_by(.number)[]
    | select(.status | IN("in_progress", "waiting"))
    | [.links[]? | select(.kind == "dispatch") | $where[.ref] // ""] as $paths
    | select($paths | length > 0)
    | select(all($paths[]; IN($done[]; .)))
    | ([.links[]? | select(.kind == "url") | (.url // .ref // "") | capture("github\\.com/\($repo)/issues/(?<n>[0-9]+)").n][0]
       // ((.title // "") | capture("^\($project) #(?<n>[0-9]+)").n) // "") as $t
    | [.number, .status, ($paths | map(split("/")[-1]) | unique | join(",")), $t] | @tsv')
  while IFS=$'\t' read -r n from names t; do
    [ -n "$n" ] || continue
    why="every linked workspace is completed"
    [ -z "$t" ] && [ "$from" = waiting ] && { echo "ITEM-KEEP $n (Waiting, no ticket)"; continue; }
    if [ -n "$t" ]; then
      iss=$(gh issue view "$t" -R "$repo" --json state,labels,body 2>/dev/null) || { echo "ITEM-KEEP $n (ticket $t could not be read)"; continue; }
      [ "$(jq -r '.state' <<<"$iss")" = CLOSED ] || { echo "ITEM-KEEP $n (ticket $t is open)"; continue; }
      why="ticket $t closed, every linked workspace is completed"
      t=$(jq -r --arg l "$owner_label" 'if any(.labels[]?; .name == $l) then "label \($l)"
        elif (.body // "") | test("(\\A|\\n)[ \\t]*[-*] \\[ \\][^\\n]*\\bowner\\b"; "i") then "an open owner box" else "" end' <<<"$iss")
      [ -n "$t" ] && { echo "ITEM-KEEP $n (ticket: $t)"; continue; }
    fi
    echo "ITEM $n done ($names)"
    [ "$apply" = 1 ] || continue
    res=ok; orca bot item set "$n" --status done --comment "Done by rule (status-sync.sh): $why ($names)." >/dev/null 2>&1 || { res=failed; itemfail=1; }
    echo "item $n $res"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(TZ=America/New_York date +%Y-%m-%dT%H:%M:%S%z)" "$kind" "$names" item-done \
      "item $n" - "$res" "$project" "$from" done >> "$ledger"
  done <<<"$irows"
  return $itemfail
}
[ "$apply" = 1 ] || { items_sync ""; echo "TOTAL $(grep -c . <<<"$rows" || true) to set, dry run"; exit 0; }

set_one() { # name TAB new -> "set <name>" or "FAILED <name>"
  if orca worktree set --worktree "path:$root/$1" --workspace-status "$2" >/dev/null 2>&1; then echo "set $1"; else echo "FAILED $1"; fi
}
export -f set_one; export root
out=$([ -z "$rows" ] || cut -f1,3 <<<"$rows" | tr '\t' '\n' | xargs -n 2 -P 8 bash -c 'set_one "$1" "$2"' _)
[ -n "$out" ] && echo "$out"
n=$(grep -c '^set ' <<<"$out" || true) m=$(grep -c '^FAILED ' <<<"$out" || true)
items_sync "$(sed -n 's/^FAILED //p' <<<"$out" | tr '\n' ' ')" || m=$((m + 1))
echo "DONE $n set, $m failed"
[ "$m" = 0 ]
