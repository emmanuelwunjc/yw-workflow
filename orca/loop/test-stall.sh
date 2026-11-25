#!/bin/bash
# Test stall.sh on a temp log. No network. Usage: bash test-stall.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cd "$T"
export STARTS_LOG="$T/starts.log" BOT_HOME=$T/home
# Two fake projects: alpha runs by default (run), beta (runb) keeps its own stall track.
echo '{"projects": {"alpha": {"repo": "o/alpha"}, "beta": {"repo": "o/beta"}}}' > "$T/projects.json"
export PROJECTS_JSON=$T/projects.json
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
run() { bash "$HERE/stall.sh" --project alpha "$@" >/dev/null 2>&1; echo $?; }   # exit 1 = STALL
runb() { bash "$HERE/stall.sh" --project beta "$@" >/dev/null 2>&1; echo $?; }
fresh() { rm -f "$STARTS_LOG"; }

fresh; check "one stalled run: no alarm" "$(run 5 0 6 0)" 0
check "two stalled runs in a row: STALL" "$(run 5 0 6 0)" 1
check "the log has one line per run" "$(wc -l < "$STARTS_LOG" | tr -d ' ')" 2
check "a log line holds free and started" "$(tail -1 "$STARTS_LOG" | grep -c 'free=5 started=0')" 1
check "a third stalled run: no second STALL" "$(run 5 0 6 0)" 0
check "a fourth stalled run: no second STALL" "$(run 5 0 6 0)" 0
run 5 1 6 0 >/dev/null; run 5 0 6 0 >/dev/null
check "a new stall after a start: STALL again" "$(run 5 0 6 0)" 1
fresh; run 5 1 6 0 >/dev/null; check "a run that started a worker breaks the pair" "$(run 5 0 6 0)" 0
fresh; run 0 0 6 0 >/dev/null; check "no FREE ticket: no stall" "$(run 0 0 6 0)" 0
fresh; run 3 0 0 0 >/dev/null; check "at the worker cap: no stall" "$(run 3 0 0 0)" 0
fresh; run 3 0 -2 0 >/dev/null; check "room below 0 counts as 0: no stall" "$(run 3 0 -1 0)" 0
check "room below 0 is logged as 0" "$(tail -1 "$STARTS_LOG" | grep -c ' room=0 ')" 1
fresh; run 2 0 6 2 >/dev/null; check "every FREE ticket explained (owner wait, worker, clash): no stall" "$(run 2 0 6 2)" 0
fresh; run 3 0 6 1 >/dev/null; check "one explained of three FREE: STALL" "$(run 3 0 6 1)" 1
fresh; run 5 0 6 0 >/dev/null; echo "2026-11-24 15:00:00 EST pr=793 conflict sent to its worker" >> "$STARTS_LOG"
check "a PR action line between two stalled runs: STALL" "$(run 5 0 6 0)" 1
fresh; check "bad input: exit 2" "$(run 5 x 6 0)" 2
check "bad input writes no log line" "$([ -f "$STARTS_LOG" ] && echo written || echo none)" none
check "minus sign only on room: exit 2" "$(run -5 0 6 0)" 2
fresh; run 5 0 6 0 >/dev/null; check "a stalled alpha run, then a stalled beta run: no STALL for beta" "$(runb 5 0 6 0)" 0
check "alpha's second stalled run with a beta line between: STALL" "$(run 5 0 6 0)" 1
check "a log line names its project" "$(grep -c ' project=beta free=5 ' "$STARTS_LOG")" 1
check "two projects and no --project: exit 2" "$(bash "$HERE/stall.sh" 5 0 6 0 >/dev/null 2>&1; echo $?)" 2
check "no BOT_HOME: exit 2" "$(env -u BOT_HOME bash "$HERE/stall.sh" --project alpha 5 0 6 0 >/dev/null 2>&1; echo $?)" 2
fresh; unset STARTS_LOG; run 5 0 6 0 >/dev/null
check "the default log is BOT_HOME/logs/starts.log" "$(grep -c ' project=alpha free=5 ' "$BOT_HOME/logs/starts.log")" 1
exit $fail
