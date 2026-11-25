#!/bin/bash
# Worker slot check: `slot.sh <ticket>`. The sweep runs it after `gh issue develop` linked the ticket, right
# before start.sh. The ticket has no start lock yet, so slots.py counts it as held only when passed here.
# That ticket is in the taken count, so SLOTS 0 may start and SLOTS below 0 may not. Two sweeps that link
# at once can both start, so the sweep holds twenty-sweep/start-guard.sh around it. Exit 0: start. Exit 1: free
# the ticket, start nothing (also on a failed count, a CAP line, or an argument that is not one taken ticket).
[ $# = 1 ] || { echo "SLOT ERROR: usage: slot.sh <ticket you just linked>"; exit 1; }
out=$(python3 -I "$(dirname "$0")/slots.py" "$@" 2>&1) || { echo "SLOT ERROR: $(tail -c 500 <<<"$out")"; exit 1; }
s=$(sed -n 's/^SLOTS: //p' <<<"$out")
[ -n "$s" ] && [ "$s" -ge 0 ] && { echo "SLOTS: $s"; exit 0; }
echo "$(grep -E '^(CAP|WORKERS|LIVE):' <<<"$out" | tr '\n' ' ')no slot, start nothing"; exit 1
