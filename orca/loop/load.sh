#!/usr/bin/env bash
# Load check for the space cleanup: should a cleanup run now?
# Sums liveTerminalCount over the workspaces under ~/orca/workspaces (one
# `orca worktree ps` call). Exit 0 and print the sum when it is at or above
# LIVE_MAX (default 40). Else exit 1, also on an orca error or truncated ps output.
set -euo pipefail
max=${LIVE_MAX:-40}
ps_json=$(orca worktree ps --json --limit 100000) || { echo "orca worktree ps failed (an orca error). Stop." >&2; exit 1; }
[ "$(jq -r '.result.truncated' <<<"$ps_json")" = false ] || { echo "orca worktree ps output is truncated. Stop." >&2; exit 1; }
n=$(jq --arg b "$HOME/orca/workspaces/" '[.result.worktrees[] | select(.path | startswith($b)) | .liveTerminalCount // 0] | add // 0' <<<"$ps_json")
[ "$n" -ge "$max" ] || exit 1
echo "$n"
