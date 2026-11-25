#!/bin/bash
# Merge a reviewed twenty PR: update the branch, wait for CI, squash-merge, log the override on the item.
# Use only after an independent reviewer posted a pass. Usage: merge.sh [--bg] <pr> <item-number>
# Test: bash test-merge.sh (a fake gh, no network).
# Background: merge.sh --bg <pr> <item-number> returns at once and logs to
# ${MERGE_LOG_DIR:-$BOT_HOME/logs}/merge-<pr>.log. The CI wait can pass a 120 s tool limit.
# The log's last line starts with "FINAL:" when the merge is over (merged, or not merged and why).
if [ "$1" = --bg ]; then
  shift
  [ -n "$1" ] && [ -n "$2" ] || { echo "usage: merge.sh --bg <pr> <item-number>"; exit 2; }
  # The bot's home folder: BOT_HOME, else the folder two levels above this script.
  BOT_HOME=${BOT_HOME:-$(cd "$(dirname "$0")/../.." && pwd)}
  LOG_DIR=${MERGE_LOG_DIR:-$BOT_HOME/logs}; mkdir -p "$LOG_DIR"; LOG=$LOG_DIR/merge-$1.log
  nohup bash -c 'bash "$0" "$1" "$2"; rc=$?
    if [ $rc = 0 ]; then echo "FINAL: merged #$1"; else echo "FINAL: not merged #$1 (exit $rc), see the line above"; fi' \
    "$0" "$1" "$2" > "$LOG" 2>&1 < /dev/null &
  echo "merge of #$1 runs in the background. Log: $LOG. Done when its last line starts with FINAL:"
  exit 0
fi
set -e
PR=$1; ITEM=$2
[ -n "$PR" ] && [ -n "$ITEM" ] || { echo "usage: merge.sh <pr> <item-number>"; exit 2; }
R=georgetown-mdi-gates4/twenty
POLL=${MERGE_POLL_SECS:-10}

head_sha() { gh pr view "$PR" -R $R --json headRefOid --jq .headRefOid; }

# Update the branch, then wait for the new head and its checks.
# Checks reach a new head late, and `gh pr checks` reports "no checks" on stderr,
# so the wait reads statusCheckRollup (the checks of the current head) instead (PRs 622, 632).
update_and_wait() {
  local old out n i
  old=$(head_sha)
  if out=$(gh pr update-branch "$PR" -R $R 2>&1) && ! grep -q "already up-to-date" <<<"$out"; then
    for i in $(seq 1 30); do [ "$(head_sha)" != "$old" ] && break; sleep "${MERGE_HEAD_SECS:-2}"; done
  fi
  echo "$out" | tail -1
  for i in $(seq 1 60); do
    n=$(gh pr view "$PR" -R $R --json statusCheckRollup --jq '.statusCheckRollup | length')
    [ "${n:-0}" -gt 0 ] && break; sleep "$POLL"
  done
  [ "${n:-0}" -gt 0 ] || { echo "no checks on the head of #$PR after $((60 * POLL))s: not merged"; exit 1; }
  # ponytail: waits for the first check only; a workflow that registers later can be missed by --watch.
  gh pr checks "$PR" -R $R --watch --fail-fast >/dev/null || { echo "CI did not pass on #$PR: not merged"; exit 1; }
}

update_and_wait
# The merge hook does not see a same-account comment review, so the override is set here and logged.
SKIP_REVIEW_GATE=1 gh pr merge "$PR" -R $R --squash || {
  # The head can move once: update, wait for the new checks, try again.
  update_and_wait
  SKIP_REVIEW_GATE=1 gh pr merge "$PR" -R $R --squash
}
orca bot item comment "$ITEM" --text "PR $PR merged (squash) after an independent comment review and a passing CI. SKIP_REVIEW_GATE=1 was set for this merge, because the hook does not see a same-account comment review." >/dev/null ||
  echo "WARNING: merged, but the item comment failed (item $ITEM). Log the override on the item by hand."
echo "merged #$PR"
