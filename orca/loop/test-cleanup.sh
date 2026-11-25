#!/usr/bin/env bash
# Self-test for cleanup.sh. Fake orca, gh and git on PATH read fixtures, so
# nothing real is read or closed. A workspace with a .git entry runs real git
# against a scratch remote. Then each `# guard:<name>` line of cleanup.sh is
# deleted in turn, and the cases must fail for each.
set -u
dir=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap '[ -n "${KEEP_WORK:-}" ] || rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/ws" "$work/beta" "$work/fix" "$work/setup/.venv"
export FIX="$work/fix" CLOSE_LOG="$work/closed" REAL_GIT GH_LOG="$work/gh.log"
# Two fake projects: alpha (root $work/ws, every case, alone in its own file) and beta (root $work/beta,
# no workspace, repo o/beta) in a two-project file.
cat > "$work/projects.json" <<J
{"live_terminal_max": 40, "projects": {
  "alpha": {"repo": "o/alpha", "ws_root": "$work/ws", "git_dir": "$work/clone", "setup_links": ["$work/setup/"],
            "retire_hold_days": 7, "labels": {"owner_wait": "needs-owner"}},
  "beta":  {"repo": "o/beta", "ws_root": "$work/beta", "git_dir": "$work/clone", "setup_links": [],
            "retire_hold_days": 7, "labels": {"owner_wait": "needs-owner"}}}}
J
jq '{live_terminal_max, projects: {alpha: .projects.alpha}}' "$work/projects.json" > "$work/alpha.json"
export PROJECTS_JSON=$work/alpha.json
# cleanup.sh --apply runs status-sync.sh beside it, also for a mutant in $work, which also reads
# project.sh and projects.py beside it.
export SET_LOG="$work/set" RM_LOG="$work/rm" CLEANUP_LEDGER="$work/ledger.tsv"
cp "$dir/status-sync.sh" "$dir/project.sh" "$dir/projects.py" "$work/"
# The bot name for `orca bot item list` comes from $BOT_HOME/bot.json.
mkdir -p "$work/home"; echo '{"name": "Test Bot"}' > "$work/home/bot.json"; export BOT_HOME="$work/home" ITEM_LOG="$work/items"
REAL_GIT=$(command -v git)

cat > "$work/bin/orca" <<'FAKE'
#!/usr/bin/env bash
case "$1 $2" in
  "worktree ps") cat "$FIX/${PS:-ps.json}" ;;
  "orchestration worker-list") # two pages; --cursor asks for page 2
    if [[ " $* " == *" --cursor="* ]]; then f=wl2.json; else f=wl1.json; fi
    jq --arg s "${WL_SCOPE:-all}" '.result.scope.source = $s' "$FIX/$f" ;;
  "orchestration inbox") cat "$FIX/inbox.json" ;;
  "terminal close") [ -n "${CLOSE_FAIL:-}" ] && exit 1; echo "$4" >> "$CLOSE_LOG" ;;
  "worktree set") echo "$4" >> "$SET_LOG" ;;
  "bot item") # list --status canceled: the canceled items of "Test Bot"; any other list: none
    [ "$3" = set ] && { echo "$*" >> "$ITEM_LOG"; exit; }
    [[ " $* " == *" --bot Test Bot "* ]] || exit 1
    if [[ " $* " == *" --status canceled "* ]]; then cat "$FIX/items-canceled.json"; else echo '{"result": {"items": []}}'; fi ;;
  "worktree rm") echo "$4" >> "$RM_LOG"; [ -n "${RM_MOVE:-}" ] && mv "${4#path:}" "${4#path:}.rm"; true ;;
  *) echo "fake orca: $*" >&2; exit 1 ;;
esac
FAKE
# `gh api repos/<r>/commits/<sha>/pulls --jq length`: 1 when <sha> is in
# $FIX/pr-commits (a commit GitHub links to a PR), else 0.
cat > "$work/bin/gh" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
[ "$1" = api ] || { cat "$FIX/prs.json"; exit; }
# A <sha> in $FIX/gh-error gets what real gh gives on HTTP 422: the error
# JSON on stdout (--jq is skipped) and exit 1.
sha=${2#*/commits/}; sha=${sha%/pulls}
grep -qx "$sha" "$FIX/gh-error" 2>/dev/null && { echo '{"message":"No commit found for SHA","status":"422"}'; exit 1; }
grep -qx "$sha" "$FIX/pr-commits" 2>/dev/null && echo 1 || echo 0
FAKE
cat > "$work/bin/git" <<'FAKE'
#!/usr/bin/env bash
[ -e "$2/.git" ] && exec "$REAL_GIT" "$@"
f="$FIX/$(basename "$2")"
case "$3" in
  rev-parse) [ "$4" = --abbrev-ref ] || exit 0; [ -f "$f/upstream" ] && cat "$f/upstream" || exit 1 ;;
  symbolic-ref) [ -f "$f/branch" ] && cat "$f/branch" || exit 1 ;;
  rev-list) cat "$f/unpushed" 2>/dev/null || echo 0 ;;
  status) cat "$f/status" 2>/dev/null || true ;;
esac
FAKE
# lsof exits 1 when nothing listens. The DONE line must still come.
printf '#!/bin/bash\nexit 1\n' > "$work/bin/lsof"
chmod +x "$work/bin/"*
export PATH="$work/bin:$PATH"

# name, branch (- for detached), unpushed, status line, expected verdict,
# expected verdict with --run-scoped and worker-list scoped to one Run.
# With --run-scoped, CLOSE needs every agent done and a MERGED PR or a
# detached HEAD, and a missing worker_done is not checked.
ws() {
  mkdir -p "$work/ws/$1" "$FIX/$1"
  [ "$2" != - ] && echo "$2" > "$FIX/$1/branch"
  echo "$3" > "$FIX/$1/unpushed"
  [ -n "$4" ] && printf '%s\n' "$4" > "$FIX/$1/status"
  echo "$1 $5 $6" >> "$work/expect"
}
ws merged    b-merged  0 ""                  CLOSE CLOSE
ws detached  -         0 ""                  CLOSE CLOSE
ws nopr      b-nopr    0 ""                  CLOSE KEEP
ws claude    b-merged2 0 "?? .claude/x.json" CLOSE CLOSE
ws setuplink b-merged3 0 "?? .venv"          CLOSE CLOSE
ln -s "$work/setup/.venv" "$work/ws/setuplink/.venv"
ws working   b-merged4 0 ""                  KEEP  KEEP
ws openpr    b-open    0 ""                  KEEP  KEEP
ws unpushed  b-merged5 2 ""                  KEEP  KEEP
ws tracked   b-merged6 0 " M scripts/a.py"   KEEP  KEEP
ws untracked b-merged7 0 "?? notes.txt"      KEEP  KEEP
ws closedpr  b-closed  0 ""                  KEEP  KEEP
ws bothome   -         0 ""                  KEEP  KEEP
ws mainwt    -         0 ""                  KEEP  KEEP
ws nops      b-merged9 0 ""                  KEEP  KEEP
ws nolive    -         0 ""                  KEEP  KEEP
ws grill-x   -         0 ""                  KEEP  KEEP
# Local branch b-local pushes as b-renamed, whose PR is open (lookdown, PR #583).
ws renamed   b-local   0 ""                  KEEP  KEEP
echo origin/b-renamed > "$FIX/renamed/upstream"
# Orchestration: an agent in state done or idle is finished only with a
# worker_done on record (a message, or its dispatch succeeded).
# donemerged: agent done, PR MERGED, no worker_done and no dispatch on record.
ws waitnodone -        0 ""                  KEEP  KEEP
ws donemerged b-merged8 0 ""                 KEEP  CLOSE
ws waitopen   -        0 ""                  KEEP  KEEP
ws blocked    -        0 ""                  KEEP  KEEP
ws idledone   -        0 ""                  CLOSE KEEP
# nopridle: a branch with no PR and a worker_done, but an idle agent. A branch
# with no PR closes only when every agent is done.
ws nopridle   b-nopr3  0 ""                  KEEP  KEEP
ws noagent    -        0 ""                  KEEP  KEEP
# askafter: a detached reviewer asks a question after its worker_done. It waits,
# also with --run-scoped (a detached HEAD is CLOSE there only with a worker_done
# after its last ask). Its dispatch ctx_aa succeeded: that counts only with no
# ask newer than its newest worker_done. waitnodone above has no worker_done.
ws askafter   -        0 ""                  KEEP  KEEP
# Last ask `ready for review: PR <n>`: PR 9 MERGED gives a NUDGE line, no
# WAITING line. PR 8 OPEN still waits. twowait has two open dispatches of one
# worker: one WAITING line, the newest.
ws nudge      -        0 ""                  KEEP  KEEP
ws waitpr     -        0 ""                  KEEP  KEEP
ws twowait    -        0 ""                  KEEP  KEEP
# donefailed: its only worker_done has outcome failed, so it is not finished.
ws donefailed -        0 ""                  KEEP  KEEP
# A worker_done body that starts with `kind: pr.`, `kind: report.` or
# `kind: review.`, the real shape (52 of 54 live bodies). report or review owes no PR:
# kindreport (a CLOSED PR only) and kindreview (an OPEN PR) close. kind pr
# needs a MERGED PR: kindprdet (detached, no PR) stays, kindprmerged closes.
ws kindreport   b-closed2  0 ""              CLOSE CLOSE
ws kindreview   b-open2    0 ""              CLOSE CLOSE
ws kindprdet    -          0 ""              KEEP  KEEP
ws kindprmerged b-merged10 0 ""              CLOSE CLOSE
# The lifecycle (Done -> Retired -> removed), read from the ledger seed below.
# held: retired 2 days ago (HOLD). backagain: retired, now a working agent.
# backdsp: retired, now an open dispatch. Both go BACK to in-progress.
# reback: retired 9 days ago, back 1 day ago, so its hold clock restarts (RETIRE).
# agedkeep: retired 8 days ago, now an untracked file: KEEP, no REMOVE.
# notdone: CLOSE, but its sidebar status is in-progress, so it is not Done yet.
ws held       -        0 ""                  CLOSE CLOSE
ws backagain  -        0 ""                  KEEP  KEEP
ws backdsp    -        0 ""                  KEEP  KEEP
ws reback     -        0 ""                  CLOSE CLOSE
ws agedkeep   -        0 "?? notes.txt"      KEEP  KEEP
ws notdone    -        0 ""                  CLOSE CLOSE
# canceled: status in-progress like notdone, but a canceled item links its
# dispatch, so it counts as Done and retires.
ws canceled   -        0 ""                  CLOSE CLOSE

# Real git. Each branch's commit lives only under one remote ref:
# stale:    branch local-only, commit only under origin/feat, deleted on the
#           remote with no prune. Old `--not --remotes` counted 0 and closed it.
# ownstale: branch gone, pushed, merged, then deleted on the remote. Its own
#           origin/gone ref holds the commit.
# livehead: branch alias at the tip of live branch kept, no PR. The local
#           branch kept is deleted, so only the sha matches the live tip.
# ownnopr:  branch orphan, pushed, then deleted on the remote, no PR. Its own
#           stale origin/orphan ref does not count, since no PR merged.
# detstale: detached HEAD at feat, which lives only under a stale ref.
# prhead:   a reviewer's detached HEAD at the head commit of a PR whose branch
#           is deleted on the remote. The PR head is on GitHub, so it is pushed.
# prold:    detached at the parent of that PR head: also on GitHub.
# prpast:   detached at an older head of a PR (a review round before the last).
#           The PR's newest head is not fetched here, but GitHub links the
#           commit to the PR (gh api .../commits/<sha>/pulls).
# squash:   trap: a squash-merged branch. Its commits are on no remote (the
#           branch and its origin/squash ref are both gone). Merged comes from
#           its MERGED PR, whose head is the branch tip.
# gherror:  detached at a commit that was never pushed, and gh api fails
#           (422, as for a sha GitHub does not have). A gh error means KEEP.
# ignored:  detached at a PR head, with an ignored run record under exports/
#           (as exports/name-backfill-*.json). `git worktree remove` deletes
#           ignored files, so it is KEEP. prold holds only ignored caches and
#           a .env setup link, which do not count.
g() { "$REAL_GIT" -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
g init -q --bare "$work/remote.git"
g clone -q "$work/remote.git" "$work/clone" 2>/dev/null
g -C "$work/clone" commit -q --allow-empty -m base
g -C "$work/clone" push -q origin main
for b in feat gone kept orphan prhead prpast squash; do
  g -C "$work/clone" checkout -q -b "$b" main
  g -C "$work/clone" commit -q --allow-empty -m "$b"
  g -C "$work/clone" push -q origin "$b"
done
g -C "$work/clone" checkout -q main
g --git-dir="$work/remote.git" update-ref -d refs/heads/feat
g --git-dir="$work/remote.git" update-ref -d refs/heads/gone
g --git-dir="$work/remote.git" update-ref -d refs/heads/orphan
g --git-dir="$work/remote.git" update-ref -d refs/heads/prhead
g --git-dir="$work/remote.git" update-ref -d refs/heads/prpast
g --git-dir="$work/remote.git" update-ref -d refs/heads/squash
g -C "$work/clone" update-ref -d refs/remotes/origin/squash
g -C "$work/clone" rev-parse prpast > "$FIX/pr-commits"
g -C "$work/clone" checkout -q -b never main
g -C "$work/clone" commit -q --allow-empty -m never
g -C "$work/clone" rev-parse never > "$FIX/gh-error"
g -C "$work/clone" checkout -q main
g -C "$work/clone" checkout -q prhead
g -C "$work/clone" commit -q --allow-empty -m prhead2
g -C "$work/clone" checkout -q main
g -C "$work/clone" worktree add -q -b local-only "$work/ws/stale" feat
g -C "$work/clone" worktree add -q "$work/ws/ownstale" gone
g -C "$work/clone" worktree add -q -b alias "$work/ws/livehead" kept
g -C "$work/clone" branch -q -D kept
g -C "$work/clone" worktree add -q "$work/ws/ownnopr" orphan
g -C "$work/clone" worktree add -q --detach "$work/ws/detstale" feat
g -C "$work/clone" worktree add -q --detach "$work/ws/prhead" prhead
g -C "$work/clone" worktree add -q --detach "$work/ws/prold" prhead~1
g -C "$work/clone" worktree add -q --detach "$work/ws/prpast" prpast
g -C "$work/clone" worktree add -q --detach "$work/ws/gherror" never
g -C "$work/clone" worktree add -q "$work/ws/squash" squash
g -C "$work/clone" worktree add -q --detach "$work/ws/ignored" prhead~1
printf '%s\n' exports/ .env __pycache__/ .ruff_cache/ >> "$work/clone/.git/info/exclude"
mkdir -p "$work/ws/ignored/exports" "$work/ws/prold/scripts/__pycache__" "$work/ws/prold/.ruff_cache"
echo '{}' > "$work/ws/ignored/exports/name-backfill-1.json"
touch "$work/ws/prold/scripts/__pycache__/a.pyc" "$work/ws/prold/.ruff_cache/x"
touch "$work/setup/.env"; ln -s "$work/setup/.env" "$work/ws/prold/.env"
printf '%s\n' "stale KEEP KEEP" "ownstale CLOSE CLOSE" "livehead CLOSE KEEP" "ownnopr KEEP KEEP" "detstale KEEP KEEP" "prhead CLOSE CLOSE" "prold CLOSE CLOSE" "prpast CLOSE CLOSE" "gherror KEEP KEEP" "squash CLOSE CLOSE" "ignored KEEP KEEP" >> "$work/expect"

# One ps row per workspace except nops. Only working has a working agent.
# working has 2 live terminals, nolive none, the others 1. One extra row
# outside the root has 3, so the LIVE line counts all of ps.
ps_fixture() { # truncated -> ps json
  awk '$1 != "nops" {print $1}' "$work/expect" | jq -R . | jq -s --arg r "$work/ws" --argjson t "$1" \
    '{result: {truncated: $t, worktrees: ([.[] | {path: "\($r)/\(.)", botHome: (. == "bothome"), isMainWorktree: (. == "mainwt"),
      workspaceStatus: (if . == "notdone" or . == "canceled" then "in-progress" else "completed" end),
      liveTerminalCount: (if . == "nolive" then 0 elif . == "working" then 2 else 1 end),
      agents: (if . == "noagent" then [] else [{address: "term_\(.)", state: (if . == "blocked" then "blocked" elif . == "idledone" or . == "nopridle" then "idle" else "done" end),
        children: (if . == "working" or . == "backagain" then [{state: "working"}] else [] end)}] end)}]
      + [{path: "/elsewhere/other", liveTerminalCount: 3, agents: []}])}}'
}
ps_fixture false > "$FIX/ps.json"
ps_fixture true > "$FIX/ps-truncated.json"
cat > "$FIX/prs.json" <<'JSON'
[{"number":9,"headRefName":"b-nine","state":"MERGED"},{"number":8,"headRefName":"b-eight","state":"OPEN"},
 {"headRefName":"b-merged","state":"MERGED"},{"headRefName":"b-merged2","state":"MERGED"},
 {"headRefName":"b-merged3","state":"MERGED"},{"headRefName":"b-merged4","state":"MERGED"},
 {"headRefName":"b-merged5","state":"MERGED"},{"headRefName":"b-merged6","state":"MERGED"},
 {"headRefName":"b-merged7","state":"MERGED"},{"headRefName":"b-open","state":"MERGED"},
 {"headRefName":"b-open","state":"OPEN"},{"headRefName":"b-closed","state":"CLOSED"},
 {"headRefName":"b-merged8","state":"MERGED"},{"headRefName":"b-merged9","state":"MERGED"},{"headRefName":"b-closed2","state":"CLOSED"},{"headRefName":"b-open2","state":"OPEN"},{"headRefName":"b-merged10","state":"MERGED"},
 {"headRefName":"gone","state":"MERGED"},{"headRefName":"b-renamed","state":"OPEN"}]
JSON
# An OPEN PR whose head is the prhead commit. gh gives headRefOid.
jq --arg o "$(g -C "$work/clone" rev-parse prhead)" --arg q "$(g -C "$work/clone" rev-parse squash)" \
  '. + [{number: 7, headRefName: "prhead", state: "OPEN", headRefOid: $o}, {number: 6, headRefName: "squash", state: "MERGED", headRefOid: $q}]' \
  "$FIX/prs.json" > "$FIX/prs.tmp" && mv "$FIX/prs.tmp" "$FIX/prs.json"

# Every agent sent worker_done except waitnodone, donemerged and idledone.
# donefailed's has outcome failed. Bodies are the real shape. Newest first.
long="Should I take lane 280 now, or wait for the reviewer of PR 700 to finish first? It holds the same file."
awk '$1 !~ /^(waitnodone|donemerged|idledone)$/ {print $1}' "$work/expect" | jq -R . | jq -s --arg long "$long" '{result: {messages: (
  [{type: "question", from_handle: "term_askafter", subject: "q", body: "Did you see my review?", payload: null},
   {type: "question", from_handle: "term_waitnodone", subject: "q", body: $long, payload: null},
   {type: "escalation", from_handle: "term_waitopen", subject: "Worker stopped without reporting", body: "x",
    payload: "{\"dispatchId\":\"ctx_open\",\"stopReason\":\"finished\"}"},
   {type: "status", from_handle: "term_waitopen", subject: "ready for review: PR 661", body: "x", payload: null},
   {type: "status", from_handle: "term_nudge", subject: "ready for review: PR 9", body: "x", payload: null},
   {type: "status", from_handle: "term_waitpr", subject: "ready for review: PR 8", body: "x", payload: null},
   {type: "question", from_handle: "term_twowait", subject: "q", body: "Which lane?", payload: null},
   {type: "question", from_handle: "term_waitnodone", subject: "q", body: "old ask", payload: null}]
  + [.[] | {type: "worker_done", from_handle: "term_\(.)", subject: "done",
    payload: (if . == "donefailed" then "{\"dispatchId\":\"ctx_df\",\"outcome\":\"failed\"}" else null end),
    body: ({kindreport: "kind: report. I read the bot transcripts and the Orca code (read only), and wrote a report.",
      kindreview: "kind: review. I reviewed PR 825 at 2365483 and posted a comment review.",
      kindprdet: "kind: pr. I opened PR 900: scripts/peer_ties.py counts each peer'"'"'s partner ties.",
      kindprmerged: "kind: pr. I opened PR 5 and it merged."}[.] // "done")}])}}' > "$FIX/inbox.json"
# Newest first: waitopen holds an open dispatch over an older finished one.
cat > "$FIX/wl1.json" <<'JSON'
{"result": {"scope": {"source": "all"}, "page": {"hasMore": true, "nextCursor": "c2"}, "workers": [
 {"dispatchId": "ctx_nudge", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_nudge",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/nudge"}}},
 {"dispatchId": "ctx_waitpr", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_waitpr",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/waitpr"}}},
 {"dispatchId": "ctx_two1", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_twowait",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/twowait"}}},
 {"dispatchId": "ctx_two2", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_twowait",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/twowait"}}},
 {"dispatchId": "ctx_open", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_waitopen",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/waitopen"}}},
 {"dispatchId": "ctx_backdsp", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_backdsp",
  "projection": {"outcome": "in_progress", "workspace": {"id": "repo::WS/backdsp"}}},
 {"dispatchId": "ctx_cancel", "dispatchStatus": "completed", "workerState": "succeeded", "agentTerminalHandle": "term_canceled",
  "projection": {"outcome": "succeeded", "workspace": {"id": "repo::WS/canceled"}}},
 {"dispatchId": "ctx_noagent", "dispatchStatus": "dispatched", "workerState": "ready", "agentTerminalHandle": "term_gone",
  "resource": {"worktreeId": "repo::WS/noagent"}, "projection": {"outcome": "in_progress"}},
 {"dispatchId": "ctx_old", "dispatchStatus": "completed", "workerState": "succeeded", "agentTerminalHandle": "term_waitopen",
  "projection": {"outcome": "succeeded", "workspace": {"id": "repo::WS/waitopen"}}},
 {"dispatchId": "ctx_fail", "dispatchStatus": "failed", "workerState": "failed", "agentTerminalHandle": "term_waitnodone",
  "projection": {"outcome": "failed"}}]}}
JSON
cat > "$FIX/wl2.json" <<'JSON'
{"result": {"scope": {"source": "all"}, "page": {"hasMore": false, "nextCursor": null}, "workers": [
 {"dispatchId": "ctx_idle", "dispatchStatus": "completed", "workerState": "succeeded", "agentTerminalHandle": "term_idledone",
  "projection": {"outcome": "succeeded"}},
 {"dispatchId": "ctx_aa", "dispatchStatus": "completed", "workerState": "succeeded", "agentTerminalHandle": "term_askafter",
  "projection": {"outcome": "succeeded"}}]}}
JSON
sed -i.bak "s|WS/|$work/ws/|" "$FIX/wl1.json"
printf '%s\n' "WAITING askafter ctx_aa Did you see my review?" "WAITING backdsp ctx_backdsp -" "WAITING blocked - -" "WAITING donefailed - -" "WAITING donemerged - -" "WAITING noagent ctx_noagent -" "WAITING twowait ctx_two1 Which lane?" "WAITING waitnodone ctx_fail ${long:0:80}" "WAITING waitopen ctx_open ready for review: PR 661" "WAITING waitpr ctx_waitpr ready for review: PR 8" > "$work/expect-waiting"
echo "NUDGE: nudge ctx_nudge PR 9 merged" > "$work/expect-nudge"
# RETIRE with an empty ledger: every Done workspace where every guard holds.
# grill-x (a grill), kindreport (a CLOSED PR only) and kindreview (an OPEN PR)
# never retire, though their terminals close.
jq -n '{result: {items: [{number: 90, status: "canceled", links: [{kind: "dispatch", ref: "ctx_cancel"}]},
  {number: 91, status: "canceled", links: [{kind: "dispatch", ref: "ctx_gone"}]}]}}' > "$FIX/items-canceled.json"
printf '%s\n' canceled claude detached held kindprmerged livehead merged nolive nopr ownstale prhead prold prpast reback setuplink squash > "$work/expect-retire0"
# The ledger seed: 10 fields, time in Eastern with its offset. Only an `ok` line
# of this project (ws, the root folder name) counts. prhead: retired 8 days ago,
# so REMOVE. merged has an old 7-field line, nopr a dry-run retire and squash a
# retire of another project: none of them counts.
ago() { python3 -c 'import sys, datetime as d; print((d.datetime.now(d.timezone.utc) - d.timedelta(days=float(sys.argv[1]))).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"))' "$1"; }
lg() { printf '%s\tdaily\t%s\t%s\tx\t-\t%s\t%s\t%s\t%s\n' "$(ago "$1")" "$2" "$3" "$4" "${5:-alpha}" "$6" "$7"; }
{ lg 8 prhead retire ok alpha done retired; lg 2 held retire ok alpha done retired; lg 9 backagain retire ok alpha done retired
  lg 3 backdsp retire ok alpha done retired; lg 9 reback retire ok alpha done retired; lg 1 reback back ok alpha retired in-progress
  lg 8 agedkeep retire ok alpha done retired; lg 10 nopr retire dry-run alpha done retired; lg 9 squash retire ok other done retired
  printf '%s\tmanual\tmerged\tremove\tdetached\t-\tok\n' "$(ago 9)"; } > "$work/ledger-seed"
grep -vxE 'prhead|held' "$work/expect-retire0" > "$work/expect-retire"
echo held > "$work/expect-hold"; echo prhead > "$work/expect-remove"; printf '%s\n' backagain backdsp > "$work/expect-back"

cases() { # script -> prints FAIL lines, returns 1 on any failure
  local script=$1 fail=0 name want got l
  # Each run starts from the ledger seed, so an --apply run does not move the next.
  cl() { cp "$work/ledger-seed" "$CLEANUP_LEDGER"; bash "$script" "$@"; }
  rm -f "$CLOSE_LOG"
  out=$(cl 2>&1)
  [ -e "$CLOSE_LOG" ] && { echo "FAIL dry run closed a workspace"; fail=1; }
  while read -r name want _; do
    got=$(awk -v n="$name" '$2 == n && $1 ~ /^(CLOSE|KEEP)$/ {print $1}' <<<"$out")
    [ "$got" = "$want" ] || { echo "FAIL $name: $got, want $want"; fail=1; }
  done < "$work/expect"
  grep -q '^NOTE' <<<"$out" && { echo "FAIL NOTE line without --run-scoped"; fail=1; }
  for l in retire hold remove back; do
    got=$(awk -v v="$(tr a-z A-Z <<<"$l")" '$1 == v {print $2}' <<<"$out" | sort)
    [ "$got" = "$(sort "$work/expect-$l")" ] || { echo "FAIL $l lines:" $got; fail=1; }
  done
  # The owner-asked path: worker-list scoped to one Run, with --run-scoped.
  sout=$(WL_SCOPE=bound cl --run-scoped 2>&1)
  [ -e "$CLOSE_LOG" ] && { echo "FAIL run-scoped dry run closed a workspace"; fail=1; }
  grep -q '^NOTE worker-list is scoped to one Run (--run-scoped): the waits guard was not checked' <<<"$sout" || { echo "FAIL run-scoped NOTE line missing"; fail=1; }
  # A Run-scoped worker list cannot prove a worker finished: nothing retires or goes.
  grep -Eq '^(RETIRE|REMOVE) ' <<<"$sout" && { echo "FAIL run-scoped run retires or removes"; fail=1; }
  while read -r name _ want; do
    got=$(awk -v n="$name" '$2 == n && $1 ~ /^(CLOSE|KEEP)$/ {print $1}' <<<"$sout")
    [ "$got" = "$want" ] || { echo "FAIL run-scoped $name: $got, want $want"; fail=1; }
  done < "$work/expect"
  WL_SCOPE=bound cl --apply --run-scoped > /dev/null 2>&1
  want=$(awk '$3 == "CLOSE" {print "path:'"$work/ws/"'" $1}' "$work/expect" | sort)
  got=$(sort "$CLOSE_LOG" 2>/dev/null)
  [ "$got" = "$want" ] || { echo "FAIL run-scoped --apply closed the wrong set"; fail=1; }
  rm -f "$CLOSE_LOG" "$SET_LOG"
  [ "$(grep '^WAITING' <<<"$out")" = "$(cat "$work/expect-waiting")" ] || { echo "FAIL WAITING lines:"; grep '^WAITING' <<<"$out"; fail=1; }
  [ "$(grep '^NUDGE:' <<<"$out")" = "$(cat "$work/expect-nudge")" ] || { echo "FAIL NUDGE lines:"; grep '^NUDGE:' <<<"$out"; fail=1; }
  cl --apply > /dev/null 2>&1
  want=$(awk '$2 == "CLOSE" {print "path:'"$work/ws/"'" $1}' "$work/expect" | sort)
  got=$(sort "$CLOSE_LOG" 2>/dev/null)
  [ "$got" = "$want" ] || { echo "FAIL --apply closed the wrong set"; fail=1; }
  # status-sync.sh gets each closed and each BACK workspace. Of those, notdone
  # becomes completed and the BACK ones in-progress; the others are completed already.
  [ "$(sort -u "$SET_LOG" 2>/dev/null)" = "$(printf 'path:%s\n' "$work/ws/backagain" "$work/ws/backdsp" "$work/ws/notdone")" ] && [ ! -e "$ITEM_LOG" ] || { echo "FAIL --apply set the status of the wrong set:" $(cat "$SET_LOG" 2>/dev/null); fail=1; }
  # One ledger line per move: done -> retired, retired -> in-progress.
  got=$(awk -F'\t' 'NR > 10 && $7 == "ok" && $4 != "close-terminal" && $4 != "set-status" {print $3, $4, $9, $10}' "$CLEANUP_LEDGER" | sort)
  want=$( { sed 's/$/ retire done retired/' "$work/expect-retire"; sed 's/$/ back retired in-progress/' "$work/expect-back"; } | sort)
  [ "$got" = "$want" ] || { echo "FAIL --apply ledger moves:"; diff <(echo "$want") <(echo "$got"); fail=1; }
  rm -f "$CLOSE_LOG" "$SET_LOG" "$RM_LOG"
  # REMOVE: only a workspace Retired for RETIRE_HOLD_DAYS (7) or more, with
  # every guard true now. Its terminals close first, then it is removed.
  cl --apply --remove > /dev/null 2>&1
  [ "$(sort "$RM_LOG" 2>/dev/null)" = "$(sed "s|^|path:$work/ws/|" "$work/expect-remove" | sort)" ] || { echo "FAIL --remove removed the wrong set:"; cat "$RM_LOG" 2>/dev/null; fail=1; }
  grep -q $'\tprhead\tremove\t.*\tok\talpha\tretired\tremoved$' "$CLEANUP_LEDGER" || { echo "FAIL ledger retired -> removed line"; fail=1; }
  rm -f "$RM_LOG"
  # A hold of 1 day: held (2 days) goes too.
  RETIRE_HOLD_DAYS=1 cl --apply --remove > /dev/null 2>&1
  [ "$(sort "$RM_LOG" 2>/dev/null)" = "$(printf 'path:%s\n' "$work/ws/held" "$work/ws/prhead")" ] || { echo "FAIL RETIRE_HOLD_DAYS=1 removed:"; cat "$RM_LOG" 2>/dev/null; fail=1; }
  rm -f "$RM_LOG"
  cl --remove > /dev/null 2>&1 && { echo "FAIL --remove ran without --apply"; fail=1; }
  [ -e "$RM_LOG" ] && { echo "FAIL a dry run removed a workspace"; fail=1; }
  rm -f "$CLOSE_LOG" "$SET_LOG"
  # Every close fails: only the BACK names go to status-sync.sh, and only
  # nolive (no live terminal, so no close) retires.
  CLOSE_FAIL=1 cl --apply > /dev/null 2>&1
  [ "$(sort -u "$SET_LOG" 2>/dev/null)" = "$(printf 'path:%s\n' "$work/ws/backagain" "$work/ws/backdsp")" ] || { echo "FAIL --apply with no close set:" $(cat "$SET_LOG" 2>/dev/null); fail=1; }
  [ "$(awk -F'\t' 'NR > 10 && $4 == "retire" && $7 == "ok" {print $3}' "$CLEANUP_LEDGER")" = nolive ] || { echo "FAIL a failed close retired"; fail=1; }
  rm -f "$SET_LOG"
  # A failed terminal close: that workspace is not removed.
  CLOSE_FAIL=1 cl --apply --remove > /dev/null 2>&1
  [ -e "$RM_LOG" ] && { echo "FAIL --remove ran after a failed close:"; cat "$RM_LOG"; fail=1; }
  rm -f "$RM_LOG" "$SET_LOG"
  if out=$(PS=ps-truncated.json cl --apply 2>&1) || [ -e "$CLOSE_LOG" ] || grep -q '^CLOSE' <<<"$out"; then
    echo "FAIL truncated ps output did not stop the run"; fail=1
  fi
  rm -f "$CLOSE_LOG"
  if out=$(WL_SCOPE=bound cl --apply 2>&1) || [ -e "$CLOSE_LOG" ] || grep -q '^CLOSE' <<<"$out"; then
    echo "FAIL a worker list scoped to one Run did not stop the run"; fail=1
  fi
  # Projects (#244): two projects need a name, --project beta reads only beta, --all-projects runs both.
  PROJECTS_JSON=$work/projects.json cl > /dev/null 2>&1 && { echo "FAIL ran with two projects and no --project"; fail=1; }
  : > "$GH_LOG"; sout=$(PROJECTS_JSON=$work/projects.json cl --project beta 2>&1)
  grep -qx 'TOTAL 0 CLOSE, 0 KEEP, dry run' <<<"$sout" || { echo "FAIL --project beta TOTAL: $(grep '^TOTAL' <<<"$sout")"; fail=1; }
  grep -q 'o/alpha' "$GH_LOG" && { echo "FAIL --project beta read alpha's repo"; fail=1; }
  grep -q -- '-R o/beta' "$GH_LOG" || { echo "FAIL --project beta did not read beta's repo"; fail=1; }
  sout=$(PROJECTS_JSON=$work/projects.json cl --all-projects 2>&1)
  [ "$(grep '^PROJECT ' <<<"$sout" | tr '\n' ' ')" = "PROJECT alpha PROJECT beta " ] || { echo "FAIL --all-projects PROJECT lines"; fail=1; }
  [ "$(grep -c '^TOTAL ' <<<"$sout")" = 2 ] && grep -q '^CLOSE ' <<<"$sout" || { echo "FAIL --all-projects did not run alpha and beta"; fail=1; }
  PROJECTS_JSON=$work/projects.json cl --all-projects --project beta > /dev/null 2>&1 && { echo "FAIL --all-projects with --project ran"; fail=1; }
  # The daily run may act by rule, but --run-scoped needs the owner in chat.
  if CLEANUP_KIND=daily WL_SCOPE=bound cl --run-scoped > /dev/null 2>&1; then
    echo "FAIL CLEANUP_KIND=daily did not refuse --run-scoped"; fail=1
  fi
  rm -f "$CLOSE_LOG"
  return $fail
}

fail=0
if cases "$dir/cleanup.sh"; then echo "ok cases pass"; else fail=1; fi
total="TOTAL $(awk '$2 == "CLOSE"' "$work/expect" | wc -l | tr -d ' ') CLOSE, $(awk '$2 == "KEEP"' "$work/expect" | wc -l | tr -d ' ') KEEP, dry run"
out=$(bash "$dir/cleanup.sh")
grep -qx "$total" <<<"$out" || { echo "FAIL total line, want $total"; fail=1; }
# Live terminals over every ps row: 1 per workspace row, 2 for working,
# 0 for nolive, 3 outside the root.
rows=$(awk '$1 != "nops"' "$work/expect" | wc -l | tr -d ' ')
live="LIVE $((rows - 1 + 1 + 3)) live terminals in $rows workspaces (all of orca worktree ps)"
grep -qx "$live" <<<"$out" && echo "ok $live" || { echo "FAIL live line, want $live"; fail=1; }
# The ledger: one line per workspace verdict and per REMOVE line, 7 fields,
# appended, never rewritten. A bad CLEANUP_KIND stops the run.
rm -f "$CLEANUP_LEDGER"; bash "$dir/cleanup.sh" > /dev/null 2>&1; cp "$CLEANUP_LEDGER" "$work/ledger1"
CLEANUP_KIND=load bash "$dir/cleanup.sh" > /dev/null 2>&1
want=$(( $(wc -l < "$work/expect") + $(wc -l < "$work/expect-retire0") ))
if [ "$(wc -l < "$work/ledger1" | tr -d ' ')" = "$want" ] && [ "$(head -n "$want" "$CLEANUP_LEDGER")" = "$(cat "$work/ledger1")" ] \
  && [ "$(wc -l < "$CLEANUP_LEDGER" | tr -d ' ')" = $((want * 2)) ] && awk -F'\t' 'NF != 10 {exit 1}' "$CLEANUP_LEDGER" \
  && grep -q $'\tmanual\ttracked\tkeep\t1 tracked-file changes\t-\t-\talpha\t-\t-$' "$work/ledger1" \
  && grep -q $'\tload\tnolive\tretire\tdetached\t-\tdry-run\talpha\tdone\tretired$' "$CLEANUP_LEDGER" \
  && ! CLEANUP_KIND=x bash "$dir/cleanup.sh" > /dev/null 2>&1; then
  echo "ok ledger: $want lines per dry run, appended"
else echo "FAIL ledger"; fail=1; fi
# A remove line in the ledger has the HEAD sha of the workspace, read before
# the rm (the fake rm moves the folder away, as the real one deletes it).
cp "$work/ledger-seed" "$CLEANUP_LEDGER"; RM_MOVE=1 bash "$dir/cleanup.sh" --apply --remove > /dev/null 2>&1
for d in "$work/ws/"*.rm; do mv "$d" "${d%.rm}"; done; rm -f "$RM_LOG" "$CLOSE_LOG" "$SET_LOG"
grep -q $'\tprhead\tremove\tdetached, held 8d\t'"$(g -C "$work/ws/prhead" rev-parse --short HEAD)"$'\tok\talpha\tretired\tremoved$' "$CLEANUP_LEDGER" \
  && echo "ok ledger remove line has the HEAD sha" || { echo "FAIL ledger remove line sha:"; grep $'\tremove\t' "$CLEANUP_LEDGER" | head -3; fail=1; }
rm -f "$CLEANUP_LEDGER"
# REASON lines count the KEEP lines by reason, with the leading number dropped.
keep=$(awk '$2 == "KEEP"' "$work/expect" | wc -l | tr -d ' ')
if [ "$(awk '/^REASON/ {s += $2} END {print s + 0}' <<<"$out")" = "$keep" ] && grep -qx 'REASON 1 tracked-file changes' <<<"$out"; then
  echo "ok REASON lines add up to $keep KEEP"
else echo "FAIL REASON lines:"; grep '^REASON' <<<"$out"; fail=1; fi
# --apply in the background, as the skill runs it: the log ends with DONE.
rm -f "$CLEANUP_LEDGER"
bash "$dir/cleanup.sh" --apply > "$work/apply.log" 2>&1 &
wait $!
done_line="DONE $(awk '$2 == "CLOSE"' "$work/expect" | wc -l | tr -d ' ') closed, 0 failed, $(wc -l < "$work/expect-retire0" | tr -d ' ') retired"
[ "$(grep -c $'\tclose-terminal\t[^\t]*\t[^\t]*\tok\t' "$CLEANUP_LEDGER")" = "$(awk '$2 == "CLOSE"' "$work/expect" | wc -l | tr -d ' ')" ] || { echo "FAIL ledger close-terminal lines after --apply"; fail=1; }
[ "$(tail -1 "$work/apply.log")" = "$done_line" ] && echo "ok background apply log ends: $done_line" || { echo "FAIL apply log last line: $(tail -1 "$work/apply.log")"; fail=1; }
rm -f "$CLOSE_LOG"
# load.sh: live terminals under the project roots. alpha's root holds 20, beta's 19, a row outside
# both 5. --all-projects sums 39, --project alpha 20. live_terminal_max (40) is the default limit.
jq -n --arg w "$work" '{result: {truncated: false, worktrees: [{path: "\($w)/ws/a", liveTerminalCount: 20},
  {path: "\($w)/beta/b", liveTerminalCount: 19}, {path: "\($w)/other/c", liveTerminalCount: 5}]}}' > "$FIX/load.json"
jq '.result.truncated = true' "$FIX/load.json" > "$FIX/load-truncated.json"
load() { PROJECTS_JSON=$work/projects.json PS=$1 LIVE_MAX=$2 bash "$dir/load.sh" "${@:3}" 2>/dev/null; }
out=$(load load.json 40 --all-projects) && { echo "FAIL load.sh below LIVE_MAX exits 0"; fail=1; } || echo "ok load.sh 39 below 40 exits 1"
[ "$(load load.json 39 --all-projects)" = 39 ] && echo "ok load.sh 39 at 39 prints 39" || { echo "FAIL load.sh at LIVE_MAX"; fail=1; }
[ "$(load load.json 38 --all-projects)" = 39 ] && echo "ok load.sh 39 above 38 prints 39" || { echo "FAIL load.sh above LIVE_MAX"; fail=1; }
[ "$(load load.json 1 --project alpha)" = 20 ] && echo "ok load.sh --project alpha counts only alpha's root" || { echo "FAIL load.sh --project alpha"; fail=1; }
[ "$(load load.json 1 --project beta)" = 19 ] && echo "ok load.sh --project beta counts only beta's root" || { echo "FAIL load.sh --project beta"; fail=1; }
load load.json 1 > /dev/null && { echo "FAIL load.sh with two projects and no --project exits 0"; fail=1; } || echo "ok load.sh needs a project"
load load-truncated.json 1 --all-projects > /dev/null && { echo "FAIL load.sh truncated exits 0"; fail=1; } || echo "ok load.sh truncated exits 1"
sed 's/^ *"live_terminal_max": 40,/"live_terminal_max": 39,/; s/{"live_terminal_max": 40,/{"live_terminal_max": 39,/' "$work/projects.json" > "$work/max39.json"
[ "$(PROJECTS_JSON=$work/max39.json PS=load.json bash "$dir/load.sh" --all-projects 2>/dev/null)" = 39 ] \
  && ! PS=load.json PROJECTS_JSON=$work/projects.json bash "$dir/load.sh" --all-projects > /dev/null 2>&1 \
  && echo "ok load.sh reads live_terminal_max when LIVE_MAX is unset" || { echo "FAIL load.sh live_terminal_max"; fail=1; }
tags=$(grep -o '# guard:[a-z]*$' "$dir/cleanup.sh" | sed 's/# guard://')
[ "$(wc -w <<<"$tags")" -ge 8 ] || { echo "FAIL fewer than 8 guard tags"; fail=1; }
for tag in $tags; do
  sed "/# guard:$tag\$/d" "$dir/cleanup.sh" > "$work/mutant.sh"
  if cases "$work/mutant.sh" > /dev/null; then echo "FAIL guard $tag removed, cases still pass"; fail=1
  else echo "ok guard $tag removed, cases fail"; fi
done
exit $fail
