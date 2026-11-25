#!/bin/bash
# usage: start.sh <item-number|-> <spec-file> [<ticket> <lane> | pr-<n>]   (DRY=1 prints the command only)
# "pr-<n>" (reviewer starts) takes locks/pr-<n>-<spec file name>, so two sweeps start one reviewer of
#   each kind per PR. The lock stays after the start. It drops when the PR has a review newer than the
#   lock, or the lock is 3 hours old.
# "-" starts the worker with no item link (reviewers), so the item gets no link mail.
# Starts a twenty worker, moves its workspace into the project list, prints dispatch id and workspace.
# With <ticket> <lane> (the sweep always passes them), a start lock stops two sweeps from
# starting two workers on one ticket (merge runs 36 and 37 both started #652):
#   locks/<ticket> is taken with mkdir (atomic). It is dropped when the lane has a
#   "Ticket #<n> done" comment newer than the lock, or the lock is 3 hours old.
#   Right before the start it re-reads the lane's "worked by" comments and `orca worktree ps`
#   (the rule is in the comment above the held check. Sweep step 5 calls start.sh with it).
# After the start it checks the brief left the worker's input box, and sends Enter again
# (3 tries) if not. Exit 3 means the worker started but its brief is still unsent.
# Test: bash test-start.sh (a fake gh and orca, no network).
[ -n "$2" ] || { echo "usage: start.sh <item> <spec-file> [<ticket> <lane>]"; exit 2; }
[ -s "$2" ] || { echo "spec file is missing or empty: $2 (no worker started)"; exit 2; }
[ -z "$3" ] || [ -n "$4" ] || [[ "$3" =~ ^pr-[0-9]+$ ]] || { echo "a ticket needs its lane: start.sh <item> <spec> <ticket> <lane>"; exit 2; }
REPO=id:64ed486f-0085-477a-9d9f-a4552aef276f
R=georgetown-mdi-gates4/twenty
# The bot's home folder: BOT_HOME, else the folder two levels above this script.
BOT_HOME=${BOT_HOME:-$(cd "$(dirname "$0")/../.." && pwd)}
LOCKS=${START_LOCKS:-$BOT_HOME/locks}
LOCK_MIN=180
# boilerplate.txt names paths as ~/.orca/bots/<bot>/...: the worker gets this bot's real home.
SPEC="$(cat "$2"; sed "s#~/.orca/bots/<bot>#$BOT_HOME#g" "$BOT_HOME/skills/twenty-worker-spec/boilerplate.txt")"
ITEM=(--item "$1"); [ "$1" = - ] && ITEM=()
if [ -n "$DRY" ]; then echo "worker-start ${ITEM[*]} (spec $(echo "$SPEC" | wc -l) lines)"; exit 0; fi

if [[ "${3:-}" =~ ^pr-[0-9]+$ ]]; then
  PRN=${3#pr-}; K=$(basename "$2" .txt); L="$LOCKS/pr-$PRN-$K"
  mkdir -p "$LOCKS"
  if [ -d "$L" ]; then
    m=$(date -r "$L" +%s)
    newest=$(gh pr view "$PRN" -R $R --json reviews --jq '[.reviews[].submittedAt] | max // ""') \
      || { echo "PR $PRN: could not read its reviews (no worker started)"; exit 1; }
    newer=$(python3 -c 'import sys, datetime as d; print(1 if sys.argv[1] and d.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")).timestamp() > int(sys.argv[2]) else "")' "$newest" "$m") \
      || { echo "PR $PRN: the lock check failed (no worker started)"; exit 1; }
    if [ -n "$newer" ] || [ $(( $(date +%s) - m )) -gt $(( LOCK_MIN * 60 )) ]; then
      # ponytail: a 1-second window between the mtime read and rm remains, so two sweeps that both
      # see a stale lock can both start (2 starts in 2 of 30 forced races). Sweeps are minutes apart.
      [ "$(date -r "$L" +%s 2>/dev/null)" = "$m" ] && rm -rf "$L"
    fi
  fi
  mkdir "$L" 2>/dev/null || { echo "PR $PRN $K: locked by $(cat "$L/owner" 2>/dev/null) (no worker started)"; exit 1; }
  echo "$2 $(date -u +%FT%TZ) pid $$" > "$L/owner"
elif [ -n "$3" ]; then
  TK=${3#\#}; L="$LOCKS/$TK"
  mkdir -p "$LOCKS"
  comments=$(gh issue view "$4" -R $R --json comments --jq '.comments[] | "\(.createdAt) \(.body | split("\n")[0])"') \
    || { echo "#$TK: could not read lane $4 comments (no worker started)"; exit 1; }
  # Drop a lock that is old or whose worker posted "done" after it was taken.
  # Remove it only if its mtime is unchanged, so a lock another sweep just took survives.
  if [ -d "$L" ]; then
    m=$(date -r "$L" +%s)
    done_after=$(python3 -c '
import sys, re, datetime
t, m = sys.argv[1], int(sys.argv[2])
for line in sys.stdin:
    ts, _, body = line.partition(" ")
    if re.match(rf"Ticket #{t}\b.*\bdone\b", body) and datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() > m:
        print(1); break' "$TK" "$m" <<<"$comments")
    if [ -n "$done_after" ] || [ $(( $(date +%s) - m )) -gt $(( LOCK_MIN * 60 )) ]; then
      # ponytail: a 1-second window between the mtime read and rm remains; locks are minutes apart in practice.
      [ "$(date -r "$L" +%s 2>/dev/null)" = "$m" ] && rm -rf "$L"
    fi
  fi
  mkdir "$L" 2>/dev/null || { echo "#$TK: locked by $(cat "$L/owner" 2>/dev/null) (no worker started)"; exit 1; }
  echo "$2 $(date -u +%FT%TZ) pid $$" > "$L/owner"
  refuse() { rm -rf "$L"; echo "#$TK: $1 (no worker started)"; exit 1; }
  # Re-read the lane and orca worktree ps. The ticket is held when:
  #   - a "worked by" comment with no later "done" is under 3 hours old, or
  #   - such a comment is older, but an agent (working or done) still names #<ticket>, or
  #   - a working agent names #<ticket>.
  # Sweep step 7 states the same rule. A python3 failure stops the start (fail closed).
  ps=$(orca worktree ps --since 1d --json) || refuse "could not read orca worktree ps"
  held=$(COMMENTS="$comments" python3 -c '
import sys, json, re, os, datetime, time
t, mins, home = sys.argv[1], int(sys.argv[2]), os.path.expanduser(sys.argv[3])
by = None
for line in os.environ["COMMENTS"].splitlines():
    ts, _, body = line.partition(" ")
    if re.match(rf"Ticket #{t}\b.*\bworked by\b", body): by = (ts, body.strip())
    elif re.match(rf"Ticket #{t}\b.*\bdone\b", body): by = None
agents = {}
for w in json.load(sys.stdin)["result"]["worktrees"]:
    if w.get("isArchived") or w.get("path") == home: continue
    for a in w.get("agents", []):
        if re.search(rf"#{t}\b", a.get("prompt") or ""): agents.setdefault(a.get("state"), w["path"])
if by and time.time() - datetime.datetime.fromisoformat(by[0].replace("Z", "+00:00")).timestamp() < mins * 60:
    print(f"lane says: {by[1]}")
elif by and (agents.get("working") or agents.get("done")):
    where = agents.get("working") or agents["done"]
    print(f"lane says: {by[1]}, and an agent in {where} names #{t}")
elif agents.get("working"):
    where = agents["working"]
    print(f"a working agent in {where} names #{t}")
else:
    print("free")' "$TK" "$LOCK_MIN" "$BOT_HOME" <<<"$ps") || refuse "the held check failed"
  [ "$held" = free ] || refuse "${held:-the held check printed nothing}"
fi

out=$(orca orchestration worker-start "${ITEM[@]}" --worktree new-child --repo "$REPO" --agent claude --spec "$SPEC" 2>&1)
ws=$(echo "$out" | grep -o 'workspace=[^ ]*' | sed 's/.*:://')
if [ -z "$ws" ] && [ -n "$L" ]; then rm -rf "$L"; echo "worker-start failed, lock dropped: $out"; exit 1; fi
orca worktree set --worktree "path:$ws" --no-parent >/dev/null 2>&1
echo "$out" | grep -o 'dispatchId=[^ ]*'; echo "workspace=$ws"

# A brief can sit unsent in the worker's input box (3 times on 2026-11-23).
# Read the rendered screen: the last "❯" line is the input box. Text after it = unsent.
# A read with no rendered screen is "unknown": wait, send nothing.
brief() { orca terminal read --terminal "$1" --screen --json 2>/dev/null | python3 -c '
import sys, json, re
try: t = json.load(sys.stdin)["result"]["terminal"]
except Exception: print("unknown"); sys.exit()
p = [l for l in t.get("tail") or [] if l.startswith("\u276f")]
# A menu line ("❯ 1. Yes") is no input box: Enter would pick that option.
print("unknown" if t.get("source") != "screen" or not p or re.match(r"\s*\d+\.", p[-1][1:]) else "unsent" if p[-1][1:].strip() else "sent")'; }
term=$(echo "$out" | grep -o 'terminal=term_[^ ]*' | head -1 | cut -d= -f2)
[ -n "$term" ] || term=$(orca orchestration worker-show --dispatch "$(echo "$out" | grep -o 'dispatchId=[^ ]*' | cut -d= -f2)" 2>/dev/null | grep -o 'terminal=term_[^ ]*' | head -1 | cut -d= -f2)
[ -n "$term" ] || { echo "brief: no terminal handle found, could not check that it was sent"; exit 0; }
TRIES=${SUBMIT_TRIES:-3}
for i in $(seq 0 "$TRIES"); do
  sleep "${SUBMIT_WAIT_SECS:-5}"
  st=$(brief "$term")
  [ "$st" = sent ] && { echo "brief: sent"; exit 0; }
  [ "$i" = "$TRIES" ] && break
  [ "$st" = unsent ] && orca terminal send --terminal "$term" --text $'\r' >/dev/null 2>&1 && echo "brief: unsent in $term, sent Enter again ($((i + 1)))"
done
echo "brief: still $st in $term after $TRIES retries. Check the terminal."; exit 3
