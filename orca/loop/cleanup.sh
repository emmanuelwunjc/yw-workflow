#!/usr/bin/env bash
# Close the terminals of finished worker workspaces of one project. Files stay on disk.
# Usage: cleanup.sh [--project <name> | --all-projects] [--apply [--remove]] [--run-scoped]
# The project's ws_root, repo, git_dir, setup_links and retire_hold_days come from
# projects.json (projects.py). --all-projects runs once per project, each run
# after a `PROJECT <name>` line, and exits 1 when any run fails.
# Default is a dry run: one line per workspace, CLOSE or KEEP with the reason.
# --apply runs `orca terminal close --worktree path:<dir> --all` for each CLOSE.
# Inputs come from one `orca worktree ps` call, one `gh pr list` call, the
# pages of `orca orchestration worker-list` and one `orca orchestration inbox`.
# A worker that waits (no worker_done on record, or an open dispatch) is KEEP
# and gets a `WAITING <workspace> <dispatch> <last ask>` line, one per worker.
# A worker whose last ask is `ready for review: PR <n>` with PR <n> MERGED
# owes only a worker_done: it gets `NUDGE: <workspace> <dispatch> PR <n> merged`.
# --run-scoped (only when the owner asks in chat): when worker-list is scoped
# to one Run, go on instead of stopping. Then CLOSE needs every agent `done`
# and a MERGED PR or a detached HEAD, and the worker_done check is skipped,
# because dispatches of other Runs are not visible, except for a detached HEAD.
# A NOTE line says so, and nothing retires or is removed in such a run.
# CLEANUP_KIND=daily (the daily automation) refuses --run-scoped.
# The lifecycle (Done -> Retired -> removed), by rule, with no yes per run.
# Orca has no Sleep command a script can run, so Retired is: the terminals are
# closed, the status stays completed, and the ledger holds `done -> retired`.
# A workspace is eligible when its sidebar status is completed (Done) or a
# canceled item of the bot (BOT_HOME/bot.json) links one of its dispatches, its
# verdict is CLOSE (or KEEP only for no live terminal), every guard holds
# again with the kind shortcut off (so an OPEN or CLOSED-only PR stays), and its
# terminal is closed or every agent is done. A grill never retires.
#   RETIRE <ws>: eligible, not Retired. --apply logs `done -> retired` after
#                its close (a failed close: no retire).
#   HOLD <ws>:   eligible, Retired fewer than retire_hold_days (RETIRE_HOLD_DAYS
#                overrides it) days ago.
#   REMOVE <ws>: eligible, Retired that many days or more. --apply --remove
#                runs `orca terminal close --worktree path:<dir> --all`, then
#                `orca worktree rm --worktree path:<dir>` (no --force, no
#                --delete-branch), and logs `retired -> removed`.
#   BACK <ws>:   Retired, and now an agent works or waits or a dispatch is
#                open. --apply logs `retired -> in-progress` and runs
#                status-sync.sh for it. The hold clock restarts at the next RETIRE.
# The state of a workspace is the to state of its newest `ok` ledger line of
# this project with one (retired, removed or in-progress).
# Every run appends one TSV line per action to $BOT_HOME/logs/ledger.tsv
# (CLEANUP_LEDGER moves it): time, run kind (CLEANUP_KIND: daily|load|manual),
# workspace, action (close-terminal|retire|back|remove|set-status|keep),
# reason, HEAD sha, result, project (the --project name), from state, to state
# (`-` when the line is no move). Lines before 2026-11-24 have 7 fields.
# Each guard line carries a `# guard:<name>` tag. test-cleanup.sh deletes each
# tagged line in turn and requires the test cases to fail.
set -euo pipefail
LOOP=$(cd "$(dirname "$0")" && pwd); . "$LOOP/project.sh" "$@"; set -- ${ARGS[@]+"${ARGS[@]}"}
if [ "$ALL_PROJECTS" = 1 ]; then
  rc=0 names=$(pall) || exit 2
  for p in $names; do echo "PROJECT $p"; bash "$0" --project "$p" "$@" || rc=1; done # guard:allprojects
  exit $rc
fi
root=$(pget ws_root)
repo=$(pget repo)
# Untracked symlinks into the primary checkout come from the session setup
# (e.g. .venv), so they are not worker output. One target per line.
setup_target=$(python3 -I "$LOOP/projects.py" get "$PROJECT" setup_links 2>/dev/null || true)
# Any checkout of the repo. Every workspace shares its `origin`.
git_dir=$(pget git_dir)
apply=0 run_scoped=0 remove=0 scoped=false
for arg in "$@"; do
  case "$arg" in
    --apply) apply=1 ;;
    --run-scoped) run_scoped=1 ;;
    --remove) remove=1 ;;
    *) echo "usage: $0 [--project <name> | --all-projects] [--apply [--remove]] [--run-scoped]" >&2; exit 2 ;;
  esac
done
[ "$remove$apply" = 10 ] && { echo "--remove needs --apply: the terminals close first." >&2; exit 2; }
ledger=${CLEANUP_LEDGER:-$BOT_HOME/logs/ledger.tsv}; mkdir -p "$(dirname "$ledger")"
kind=${CLEANUP_KIND:-manual}
case "$kind" in daily | load | manual) ;; *) echo "CLEANUP_KIND is daily, load or manual" >&2; exit 2 ;; esac
# The owner allowed the daily run to close and remove by rule (2026-11-24, #246).
# A Run-scoped worker list still needs the owner in chat.
[ "$kind" = daily ] && [ "$run_scoped" = 1 ] && { echo "CLEANUP_KIND=daily: --run-scoped needs the owner in chat. Stop." >&2; exit 2; } # guard:dailyscoped
project=$PROJECT
hold=${RETIRE_HOLD_DAYS:-$(pget retire_hold_days)}
case "$hold" in "" | *[!0-9]*) echo "RETIRE_HOLD_DAYS is a whole number of days" >&2; exit 2 ;; esac

ps_json=$(orca worktree ps --json --limit 100000)
[ "$(jq -r '.result.truncated' <<<"$ps_json")" = false ] || { echo "orca worktree ps output is truncated, so a working agent can hide. Stop." >&2; exit 1; } # guard:truncated
# path TAB working(0/1) TAB botHome or main worktree(0/1) TAB live terminals
# TAB every agent and child agent done(0/1) TAB sidebar status, one line per workspace.
ps_rows=$(jq -r '.result.worktrees[] | [.path,
  (if [.agents[]? | .. | objects | .state? ] | any(. == "working") then 1 else 0 end),
  (if .botHome or .isMainWorktree then 1 else 0 end),
  (.liveTerminalCount // 0),
  (if [.agents[]? | recurse(.children[]?) | .state] | length > 0 and all(. == "done") then 1 else 0 end),
  (.workspaceStatus // "-")] | @tsv' <<<"$ps_json")
# workspace TAB state (retired, removed, in-progress) TAB whole days since,
# from the newest `ok` move line of this project in the ledger.
life_rows=$(python3 - "$ledger" "$project" <<'PY'
import sys, datetime as d
last = {}
try:
    lines = open(sys.argv[1]).read().splitlines()
except FileNotFoundError:
    lines = []
for line in lines:
    f = line.split("\t")
    if len(f) == 10 and f[6] == "ok" and f[7] == sys.argv[2] and f[9] in ("retired", "removed", "in-progress"):
        last[f[2]] = (f[9], f[0])
now = d.datetime.now(d.timezone.utc)
for ws, (state, t) in sorted(last.items()):
    print(f"{ws}\t{state}\t{(now - d.datetime.strptime(t, '%Y-%m-%dT%H:%M:%S%z')).days}")
PY
)
# Every supervised dispatch, newest first, over all pages.
workers='[]' cursor=
while :; do
  page=$(orca orchestration worker-list --json --full --limit 100 ${cursor:+--cursor="$cursor"})
  src=$(jq -r '.result.scope.source' <<<"$page")
  [ "$src" = all ] || [ "$run_scoped" = 1 ] || { echo "orca orchestration worker-list is scoped to one Run, so an open dispatch can hide. Stop. The owner may ask for --run-scoped." >&2; exit 1; } # guard:scope
  [ "$src" = all ] || scoped=true
  workers=$(jq -cs '.[0] + .[1].result.workers' <(printf '%s' "$workers") - <<<"$page")
  cursor=$(jq -r 'if .result.page.hasMore then .result.page.nextCursor else empty end' <<<"$page")
  [ -n "$cursor" ] || break
done
mail=$(orca orchestration inbox --json --full --limit 100000)
# The workspaces a canceled item links, by its dispatch links. They count as Done.
canceled='[]' cursor= bot=$(jq -r '.name // empty' "$BOT_HOME/bot.json" 2>/dev/null || true)
while [ -n "$bot" ]; do
  page=$(orca bot item list --bot "$bot" --status canceled --json --limit 100 ${cursor:+--cursor "$cursor"})
  canceled=$(jq -cs '.[0] + .[1].result.items' <(printf '%s' "$canceled") - <<<"$page")
  cursor=$(jq -r '.result.nextCursor // empty' <<<"$page")
  [ -n "$cursor" ] || break
done
canceled_paths=$(jq -nr --slurpfile c <(printf '%s' "$canceled") --slurpfile d <(printf '%s' "$workers") '
  [$c[0][].links[]? | select(.kind == "dispatch") | .ref] as $refs
  | $d[0][] | select(IN(.dispatchId; $refs[])) | (.resource.worktreeId // .projection.workspace.id // "") | split("::")[1] // empty')
prs=$(gh pr list -R "$repo" --state all --limit 100000 --json number,headRefName,state,headRefOid)
# path TAB dispatch TAB why TAB last ask TAB merged PR (or empty), one line
# per worker that waits:
# each open dispatch (outcome in_progress) of a workspace, and each agent not
# working with no open dispatch and no worker_done on record. Finished means a
# worker_done from its terminal or for one of its dispatches, or a dispatch
# that succeeded. Mail and dispatches are newest first.
# A worker_done counts only when it is newer than the worker's last ask. A
# succeeded dispatch counts only when the worker sent no ask: an ask after a
# worker_done means it waits again, and the dispatch still says succeeded.
# The inputs go through files: as arguments they pass the size limit.
wait_rows=$(jq -nr --slurpfile ps <(printf '%s' "$ps_json") --slurpfile d <(printf '%s' "$workers") \
  --slurpfile mail <(printf '%s' "$mail") --slurpfile prs <(printf '%s' "$prs") '
  $ps[0] as $ps | $d[0] as $d | $mail[0].result.messages as $m
  | [$prs[0][] | select(.state == "MERGED") | .number | tostring] as $merged
  | def did: (.payload // "{}") | fromjson | .dispatchId // empty;
    # The last ask: the newest question, escalation or status the worker sent.
    # The "stopped without reporting" mail from Orca (payload stopReason) is skipped.
    def asks($t): $m | to_entries[] | select(.value.from_handle == $t and (.value.type | IN("question", "escalation", "status")))
      | select((.value.payload // "{}") | fromjson | has("stopReason") | not);
    def ask($t): [asks($t).value][0]
      | (if .type == "question" then .body else .subject // .body end) // "-" | gsub("\\s+"; " ") | .[0:80];
    def path: (.resource.worktreeId // .projection.workspace.id // "") | split("::")[1] // "";
  [$m | to_entries[] | select(.value.type == "worker_done" and ((.value.payload // "{}") | fromjson | .outcome) != "failed") | {i: .key, h: .value.from_handle, d: (.value | did // null)}] as $done
  | [$d[] | select(.projection.outcome == "in_progress")] as $open
  | [$ps.result.worktrees[] | .path as $p
    | ($open[] | select(path == $p) | [$p, .dispatchId, "open dispatch", (ask(.agentTerminalHandle) // "-"), .agentTerminalHandle]), # guard:opendispatch
      (.agents[]? | select(.state != "working") | .address as $a
       | [$d[] | select(.agentTerminalHandle == $a)] as $mine
       | select(any($open[]; .agentTerminalHandle == $a or path == $p) | not)
       | ([asks($a).key][0] // infinite) as $asked
       | ([$mine[].dispatchId] as $ids | any($done[]; (.h == $a or IN(.d; $ids[])) and .i < $asked) or ($asked == infinite and any($mine[]; .workerState == "succeeded"))) as $fin
       | [ (if .state | IN("done", "idle") | not then "state \(.state)" else empty end), # guard:state
           (if $fin | not then "no worker_done" else empty end),                         # guard:workerdone
           empty ] | select(length > 0)
       | [$p, ($mine[0].dispatchId // "-"), .[0], (ask($a) // "-"), $a])]
  | unique_by([.[0], .[4]]) # guard:oneworker
  | .[]
  | (.[3] | capture("^ready for review: PR (?<n>[0-9]+)\\b").n // "") as $n
  | .[4] = (if IN($merged[]; $n) then $n else "" end) # guard:merged
  | @tsv')
# branch TAB state, one line per PR.
pr_rows=$(jq -r '.[] | [.headRefName, .state] | @tsv' <<<"$prs")
# path TAB kind, from the newest worker_done of an agent in the workspace whose
# body starts with `kind: pr`, `kind: report` or `kind: review` as a word, e.g.
# `kind: review. I reviewed PR 825`. A report or review worker owes no PR.
kind_rows=$(jq -nr --slurpfile ps <(printf '%s' "$ps_json") --slurpfile mail <(printf '%s' "$mail") '
  $mail[0].result.messages as $m | $ps[0].result.worktrees[] | .path as $p
  | [.agents[]?.address as $a | $m[] | select(.type == "worker_done" and .from_handle == $a)
     | (.body // "") | capture("\\Akind: (?<k>pr|report|review)\\b").k][0] // empty # guard:kindstart
  | [$p, .] | @tsv')
# Tips of the branches on the live remote, one call per run, and the head
# commit of every PR, as `^sha` lines. A PR head stays on GitHub after its
# branch is deleted, so a reviewer's checkout of it holds no local work.
# A local origin/<name> ref stays after its branch is deleted on GitHub (no
# prune), so `--remotes` alone can hide commits that exist only here.
live_heads=$({ git -C "$git_dir" ls-remote --heads origin | cut -f1; jq -r '.[].headRefOid // empty' <<<"$prs"; } | sed 's/^/^/')

setup_link() { # link target -> exit 0 when it starts with one of the setup_links
  local t; while IFS= read -r t; do [ -n "$t" ] && [[ "$1" == "$t"* ]] && return 0; done <<<"$setup_target"; return 1
}
decide() { # dir -> prints "CLOSE|KEEP <reason>"
  local dir=$1 row waits branch up states own unpushed status line tracked=0 untracked=0 ignored=0 p kind n
  row=$(awk -F'\t' -v p="$dir" '$1 == p' <<<"$ps_rows")
  [ -z "$row" ] && { echo "KEEP no orca worktree ps row"; return; }                      # guard:psrow
  [ "$(cut -f3 <<<"$row")" = 1 ] && { echo "KEEP bot home or main worktree"; return; }   # guard:bothome
  # skip_live (the lifecycle check): a closed terminal is no reason to stay.
  [ -z "${skip_live:-}" ] && [ "$(cut -f4 <<<"$row")" = 0 ] && { echo "KEEP no live terminal"; return; } # guard:live
  case "${dir##*/}" in grill*) echo "KEEP grill chat"; return ;; esac # guard:grill
  [ "$(cut -f2 <<<"$row")" = 1 ] && { echo "KEEP agent working"; return; }               # guard:working
  [ "$scoped" = true ] && [ "$(cut -f5 <<<"$row")" != 1 ] && { echo "KEEP not every agent done, run-scoped"; return; } # guard:alldone
  waits=$(awk -F'\t' -v p="$dir" '$1 == p' <<<"$wait_rows")
  # Run-scoped: a dispatch that succeeded in another Run is not visible, so a
  # missing worker_done is no wait there, except for a detached HEAD (below).
  nodone=; if [ "$scoped" = true ]; then
    nodone=$(awk -F'\t' '$3 == "no worker_done"' <<<"$waits"); waits=$(awk -F'\t' '$3 != "no worker_done"' <<<"$waits")
  fi
  [ -n "$waits" ] && { echo "KEEP waits: $(head -1 <<<"$waits" | cut -f3)"; awk -F'\t' -v n="${dir##*/}" '{print ($5 == "" ? "WAITING " n " " $2 " " $4 : "NUDGE: " n " " $2 " PR " $5 " merged")}' <<<"$waits"; return; } # guard:waits
  git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "KEEP not a git worktree"; return; }
  branch=$(git -C "$dir" symbolic-ref --short -q HEAD || true)
  # A branch may push under another name (local r3/x, upstream origin/feat/x): its PR has the upstream name.
  up=$([ -n "$branch" ] && git -C "$dir" rev-parse --abbrev-ref '@{u}' 2>/dev/null | sed 's|^origin/||') # guard:upstream
  states=$([ -n "$branch" ] && awk -F'\t' -v b="$branch" -v u="${up:-}" '$1 == b || (u != "" && $1 == u) {print $2}' <<<"$pr_rows" | sort -u | tr '\n' ' ')
  # Pushed: on origin/main or on a live remote branch. The branch's own origin
  # ref counts only after its PR merged (squash-merged, then deleted on GitHub).
  # Other stale origin refs never count, for a branch or a detached HEAD.
  own=; case " $states" in *" MERGED "*) own="^refs/remotes/origin/${up:-$branch}" ;; esac
  unpushed=$(git -C "$dir" rev-list --count --ignore-missing HEAD ^origin/main ${own:+"$own"} --stdin <<<"$live_heads")
  # A reviewer's detached HEAD can be an older head of a PR, whose newest head
  # is not fetched here. GitHub still links the commit to the PR: one call.
  # On an HTTP error gh prints the error JSON to stdout and exits 1: any gh
  # error, a 422 or a rate limit, means KEEP.
  if [ "$unpushed" != 0 ] && [ -z "$branch" ]; then
    n=$(gh api "repos/$repo/commits/$(git -C "$dir" rev-parse HEAD)/pulls" --jq length 2>/dev/null || echo error)
    case "$n" in "" | *[!0-9]*) n=0 ;; esac # guard:gherror
    [ "$n" != 0 ] && unpushed=0
  fi
  [ "$unpushed" != 0 ] && { echo "KEEP $unpushed unpushed commits"; return; }            # guard:unpushed
  # --ignored: `git worktree remove` deletes ignored files, e.g. a run record
  # in exports/. Caches and the session-setup links do not count.
  status=$(git -C "$dir" status --porcelain --untracked-files=all --ignored)
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "${line:0:2}" in "??" | "!!") ;; *) tracked=$((tracked + 1)); continue ;; esac
    p=${line:3}
    case "$p" in .claude/* | *__pycache__/* | .ruff_cache/* | */.ruff_cache/*) continue ;; esac
    if [ -L "$dir/$p" ] && setup_link "$(readlink "$dir/$p")"; then continue; fi
    if [ "${line:0:2}" = "!!" ]; then ignored=$((ignored + 1)); else untracked=$((untracked + 1)); fi
  done <<<"$status"
  [ "$tracked" != 0 ] && { echo "KEEP $tracked tracked-file changes"; return; }          # guard:tracked
  [ "$untracked" != 0 ] && { echo "KEEP $untracked untracked files"; return; }           # guard:untracked
  [ "$ignored" != 0 ] && { echo "KEEP $ignored ignored files"; return; }                 # guard:ignored
  [ -z "$branch" ] && [ -n "$nodone" ] && { echo "KEEP detached, no worker_done after its last ask, run-scoped"; return; } # guard:scopeddetached
  kind=$(awk -F'\t' -v p="$dir" '$1 == p {print $2}' <<<"$kind_rows")
  # A report or review closes its terminal with no MERGED PR. The lifecycle
  # check (skip_live) skips this, so an OPEN or CLOSED-only PR never retires.
  case "$kind" in report | review) [ -z "${skip_live:-}" ] && { echo "CLOSE kind $kind"; return; } ;; esac # guard:kindretire
  [ "$kind" = pr ] && [[ " $states" != *" MERGED "* ]] && { echo "KEEP kind pr, no MERGED PR"; return; } # guard:kindpr
  [ -z "$branch" ] && { echo "CLOSE detached"; return; }
  case " $states" in *" OPEN "*) echo "KEEP OPEN PR"; return ;; esac                     # guard:openpr
  case " $states" in *" MERGED "*) echo "CLOSE MERGED"; return ;; esac
  [ "$scoped" = true ] && { echo "KEEP no MERGED PR, run-scoped"; return; }               # guard:scopedpr
  [ -z "$states" ] && [ "$(cut -f5 <<<"$row")" != 1 ] && { echo "KEEP no PR, not every agent done"; return; } # guard:noprdone
  [ -z "$states" ] && { echo "CLOSE no PR"; return; }
  echo "KEEP PR ${states% } only"
}

report() { # the verdict line, any WAITING lines as they are, then one RETIRE, HOLD, REMOVE or BACK line
  local v first r row name st age; v=$(decide "$1"); first=${v%%$'\n'*}; name=$(basename "$1")
  echo "${first%% *} $name (${first#* })"
  [ "$v" = "$first" ] || echo "${v#*$'\n'}"
  read -r st age <<<"$(awk -F'\t' -v n="$name" '$1 == n {print $2, $3}' <<<"$life_rows")"
  case "$first" in "KEEP agent working" | "KEEP waits: open dispatch" | "KEEP waits: state "*) [ "$st" = retired ] && echo "BACK $name (${first#KEEP })"; return 0 ;; esac # guard:back
  [ "$scoped" = true ] && return 0 # guard:scopedretire
  case "$first" in "KEEP no live terminal" | CLOSE*) r=$(skip_live=1 decide "$1" | head -1) ;; *) return 0 ;; esac
  row=$(awk -F'\t' -v p="$1" '$1 == p' <<<"$ps_rows")
  [ "$(cut -f4 <<<"$row")" = 0 ] || [ "$(cut -f5 <<<"$row")" = 1 ] || return 0 # guard:removedone
  [ "$(cut -f6 <<<"$row")" = completed ] || grep -qxF -- "$1" <<<"$canceled_paths" || return 0 # guard:isdone
  case "$r" in CLOSE*) ;; *) return 0 ;; esac
  if [ "$st" != retired ]; then echo "RETIRE $name (${r#* })"
  elif [ "$age" -lt "$hold" ]; then echo "HOLD $name (retired ${age}d ago, hold ${hold}d)" # guard:hold
  else echo "REMOVE $name (${r#* }, held ${age}d)"; fi
}
export -f decide report setup_link
export ps_rows pr_rows setup_target live_heads wait_rows scoped repo kind_rows life_rows hold canceled_paths
[ "$scoped" = true ] && echo "NOTE worker-list is scoped to one Run (--run-scoped): the waits guard was not checked for dispatches outside it. CLOSE needs every agent done and a MERGED PR or a detached HEAD."
# Each workspace costs several git calls, so 8 run at a time.
lines=$(for dir in "$root"/*/; do [ -d "$dir" ] || continue; printf '%s\0' "${dir%/}"; done \
  | xargs -0 -P 8 -I{} bash -c 'report "$1"' _ {} | sort -k2)
grep -Ev '^(WAITING|NUDGE:|RETIRE|HOLD|REMOVE|BACK) ' <<<"$lines"
for l in WAITING NUDGE: RETIRE HOLD REMOVE BACK; do grep "^$l " <<<"$lines" || true; done
log() { # workspace action reason result sha from to -> one ledger line. Append only.
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(TZ=America/New_York date +%Y-%m-%dT%H:%M:%S%z)" "$kind" "$1" "$2" "$3" \
    "${5:-$(git -C "$root/$1" rev-parse --short HEAD 2>/dev/null | grep . || echo -)}" "$4" "$project" "${6:--}" "${7:--}" >> "$ledger"
}
# Each KEEP, and in a dry run each planned close, move and remove.
while read -r v name reason; do
  reason=${reason#(}; reason=${reason%)}
  case "$v" in
    KEEP) log "$name" keep "$reason" - ;;
    CLOSE) [ "$apply" = 1 ] || log "$name" close-terminal "$reason" dry-run ;;
    RETIRE) [ "$apply" = 1 ] || log "$name" retire "$reason" dry-run "" done retired ;;
    BACK) [ "$apply" = 1 ] || log "$name" back "$reason" dry-run "" retired in-progress ;;
    REMOVE) [ "$remove" = 1 ] || log "$name" remove "$reason" dry-run "" retired removed ;;
  esac
done < <(grep -E '^(KEEP|CLOSE|RETIRE|BACK|REMOVE) ' <<<"$lines")
closed=0 failed=0 removed=0 retired=0 closed_names= failed_names=
if [ "$apply" = 1 ]; then
  # About 3 seconds per close, so a long list runs in the background.
  while IFS= read -r name; do
    if orca terminal close --worktree "path:$root/$name" --all >/dev/null; then
      echo "closed $name"; closed=$((closed + 1)); closed_names+=" $name"; log "$name" close-terminal "" ok
    else
      echo "FAILED $name"; failed=$((failed + 1)); failed_names+=" $name"; log "$name" close-terminal "" failed
    fi
  done < <(awk '$1 == "CLOSE" {print $2}' <<<"$lines")
  back_names=$(awk '$1 == "BACK" {printf " %s", $2}' <<<"$lines")
  # The sidebar label of each closed and each BACK workspace, by the status-sync.sh rule.
  # With no name, status-sync.sh would set every workspace, so none skips it.
  if [ -n "$closed_names$back_names" ]; then
    res=ok; bash "$LOOP/status-sync.sh" --project "$PROJECT" --apply $closed_names $back_names || { failed=$((failed + 1)); res=failed; } # guard:statussync
    for name in $closed_names $back_names; do log "$name" set-status "" "$res"; done
  fi
  # Done -> Retired. A workspace whose close failed keeps its terminal: no retire.
  while read -r name reason; do
    case "$failed_names " in *" $name "*) continue ;; esac # guard:retirefailed
    echo "retired $name"; retired=$((retired + 1)); log "$name" retire "${reason:1:${#reason}-2}" ok "" done retired
  done < <(awk '$1 == "RETIRE" {$1 = ""; print substr($0, 2)}' <<<"$lines")
  while read -r name reason; do
    [ -n "$name" ] && log "$name" back "${reason:1:${#reason}-2}" ok "" retired in-progress
  done < <(awk '$1 == "BACK" {$1 = ""; print substr($0, 2)}' <<<"$lines")
fi
if [ "$remove" = 1 ]; then
  # Retired -> removed. The terminals close first: a failed close stops the rm.
  # No --force: git refuses a worktree with changes. No --delete-branch.
  while read -r name reason; do
    sha=$(git -C "$root/$name" rev-parse --short HEAD 2>/dev/null | grep . || echo -) # read before the rm
    orca terminal close --worktree "path:$root/$name" --all >/dev/null || { echo "FAILED remove $name (terminal close)"; failed=$((failed + 1)); log "$name" remove "${reason:1:${#reason}-2}" failed "$sha" retired removed; continue; } # guard:rmclose
    if orca worktree rm --worktree "path:$root/$name" >/dev/null; then
      echo "removed $name"; removed=$((removed + 1)); log "$name" remove "${reason:1:${#reason}-2}" ok "$sha" retired removed
    else
      echo "FAILED remove $name"; failed=$((failed + 1)); log "$name" remove "${reason:1:${#reason}-2}" failed "$sha" retired removed
    fi
  done < <(awk '$1 == "REMOVE" {$1 = ""; print substr($0, 2)}' <<<"$lines")
fi
echo "TOTAL $(grep -c '^CLOSE' <<<"$lines") CLOSE, $(grep -c '^KEEP' <<<"$lines") KEEP$([ "$apply" = 1 ] && echo ", closed" || echo ", dry run")$([ "$scoped" = true ] && echo ", run-scoped" || true)"
# KEEP lines by reason, the leading count dropped, e.g. `REASON 21 unpushed commits`.
sed -n 's/^KEEP [^ ]* (\(.*\))$/\1/p' <<<"$lines" | sed -E 's/^[0-9]+ //' | sort | uniq -c | sort -rn \
  | awk '{n = $1; sub(/^ *[0-9]+ /, ""); print "REASON " n " " $0}'
# All of `orca worktree ps`, every root, to compare with Orca's own counts.
jq -r '.result.worktrees | "LIVE \(map(.liveTerminalCount // 0) | add // 0) live terminals in \(map(select((.liveTerminalCount // 0) > 0)) | length) workspaces (all of orca worktree ps)"' <<<"$ps_json"

echo "PORTS listening processes by command (none are stopped):"
lsof -nP -iTCP -sTCP:LISTEN -Fpc 2>/dev/null \
  | awk '/^p/ {pid = substr($0, 2)} /^c/ {print pid "\t" substr($0, 2)}' \
  | sort -u | cut -f2 | sort | uniq -c | sort -rn || true # lsof exits 1 when nothing listens
if [ "$apply" = 1 ]; then
  echo "DONE $closed closed, $failed failed, $retired retired$([ "$remove" = 1 ] && echo ", $removed removed" || true)"
  [ "$failed" = 0 ]
fi
