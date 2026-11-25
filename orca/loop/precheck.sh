#!/bin/bash
# Precheck of a free work check automation: passes when slots.py prints a FREE line and SLOTS > 0
# (owner decisions 2026-11-24: the SLOTS definition is in the head comment of slots.py).
# Usage: precheck.sh [--project <name>]
D=$(dirname "$0")
# A failed slots.py passes the precheck with a PRECHECK ERROR line: a skipped run shows only as
# skipped_precheck in run history, so the sweep runs and its chat output shows the failure.
out=$(python3 -I "$D/slots.py" "$@" 2>&1) || { echo "PRECHECK ERROR: slots.py failed: $(tail -c 1500 <<<"$out")"; exit 0; }
grep -q '^FREE: #' <<<"$out" && grep -q '^SLOTS: [1-9]' <<<"$out"
