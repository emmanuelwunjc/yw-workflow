#!/bin/bash
# Test start-guard.sh on a temp locks folder. No network. Usage: bash test-start-guard.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export START_LOCKS="$T/locks"
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
g() { bash "$HERE/start-guard.sh" "$@" >/dev/null 2>&1; echo $?; }

check "take with no locks folder yet: taken" "$(g take)" 0
check "a second take while held: refused" "$(g take)" 1
check "release" "$(g release)" 0
check "take after release: taken" "$(g take)" 0
touch -t "$(date -v-11M +%Y%m%d%H%M)" "$START_LOCKS/sweep-start"
check "a guard over 10 minutes old is dropped: taken" "$(g take)" 0
touch -t "$(date -v-9M +%Y%m%d%H%M)" "$START_LOCKS/sweep-start"
check "a guard under 10 minutes old holds: refused" "$(g take)" 1
g release >/dev/null
check "no or a wrong argument: exit 2" "$(g; g wait)" "$(printf '2\n2')"

# Review NIT 1 (2026-11-24): five sweeps ran at once and WORKERS read 9/8. Many takers race: one wins.
for r in 1 2 3 4 5; do
  for i in 1 2 3 4 5 6 7 8; do (g take > "$T/race$r-$i") & done; wait
  check "race $r: 8 takers at once, exactly one wins" "$(cat "$T"/race$r-* | grep -c '^0$')" 1
  g release >/dev/null
done
check "no BOT_HOME and no START_LOCKS: exit 2" "$(env -u START_LOCKS -u BOT_HOME bash "$HERE/start-guard.sh" take >/dev/null 2>&1; echo $?)" 2
[ $fail = 0 ] && echo "test-start-guard ok"
exit $fail
