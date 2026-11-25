#!/bin/bash
# usage: stall.sh <free> <started> <room> <explained>   (STARTS_LOG=<path> moves the log, for tests)
# The sweep's stall tripwire (retro of 2026-11-24: the sweep said "started no worker" for hours).
#   <free>       the count of FREE: lines of the free work check
#   <started>    the workers this run started
#   <room>       the most workers this run may start: the number on the SLOTS: line of the free work
#                check (slots.py computes it, and its head comment defines it). A room below 0 counts as 0.
#   <explained>  the FREE tickets it dropped as "waits on the owner", "has a worker" or "clash with"
# A run is stalled when started = 0, room >= 1, and explained < free (so free >= 1).
# It appends one line to starts.log beside this script. It reads only its own "free=" lines,
# because the sweep also logs PR actions there. The "alarm=1" field marks a stall already named.
# Exit 1 and a "STALL:" line when this run and the run before it are both stalled, once per stall:
# the alarm stays set while the stall goes on, and clears on the first run that is not stalled.
# Exit 2: bad input. Test: bash test-stall.sh
set -u
[ $# -eq 4 ] || { sed -n '2p' "$0" >&2; exit 2; }
for n in "$1" "$2" "$4" "${3#-}"; do case "$n" in ''|*[!0-9]*) echo "not a count: $n" >&2; exit 2 ;; esac; done
room=$3; [ "$room" -ge 0 ] || room=0
LOG=${STARTS_LOG:-$(cd "$(dirname "$0")" && pwd)/starts.log}
stalled=0; [ "$2" -eq 0 ] && [ "$room" -ge 1 ] && [ "$4" -lt "$1" ] && stalled=1
# The last run: was it stalled, and was its stall already named?
prev=$(grep ' free=' "$LOG" 2>/dev/null | tail -1 | grep -o 'stalled=[01] alarm=[01]')
alarm=0; fire=0
if [ $stalled = 1 ] && [ "${prev%% *}" = stalled=1 ]; then
  alarm=1; [ "${prev##* }" = alarm=1 ] || fire=1
fi
echo "$(TZ=America/New_York date '+%F %T %Z') free=$1 started=$2 room=$room explained=$4 stalled=$stalled alarm=$alarm" >> "$LOG"
[ $fire = 1 ] || exit 0
echo "STALL: two sweeps in a row had $1 FREE tickets and room for $room workers, and started none"
exit 1
