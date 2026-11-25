#!/bin/bash
# Worker slot check: `slot.sh [--project <name>] <ticket>`. The sweep runs it after `gh issue develop` linked
# the ticket, right before start.sh. The ticket has no start lock yet, so slots.py counts it as held only when
# passed here. That ticket is in the taken count, so SLOTS 0 may start and SLOTS below 0 may not. Two sweeps
# that link at once can both start, so the sweep holds start-guard.sh around it. Exit 0: start. Exit 1: free
# the ticket, start nothing (also on a failed count, a CAP line, or an argument that is not one taken ticket).
proj=() args=()
while [ $# -gt 0 ]; do
  case "$1" in --project) proj=(--project "${2:-}"); shift; shift ;; *) args+=("$1"); shift ;; esac
done
[ ${#args[@]} = 1 ] || { echo "SLOT ERROR: usage: slot.sh [--project <name>] <ticket you just linked>"; exit 1; }
out=$(python3 -I "$(dirname "$0")/slots.py" "${proj[@]}" "${args[@]}" 2>&1) || { echo "SLOT ERROR: $(tail -c 500 <<<"$out")"; exit 1; }
s=$(sed -n 's/^SLOTS: //p' <<<"$out")
[ -n "$s" ] && [ "$s" -ge 0 ] && { echo "SLOTS: $s"; exit 0; }
echo "$(grep -E '^(CAP|WORKERS|LIVE):' <<<"$out" | tr '\n' ' ')no slot, start nothing"; exit 1
