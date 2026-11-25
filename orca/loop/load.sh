#!/usr/bin/env bash
# Load check for the space cleanup: should a cleanup run now?
# Usage: load.sh [--project <name> | --all-projects]
# Sums liveTerminalCount over the workspaces under the ws_root of the project,
# or of every project with --all-projects (one `orca worktree ps` call). Exit 0
# and print the sum when it is at or above live_terminal_max of projects.json
# (LIVE_MAX overrides it). Else exit 1, also on an orca error or truncated ps output.
set -euo pipefail
LOOP=$(cd "$(dirname "$0")" && pwd); . "$LOOP/project.sh" "$@"; set -- ${ARGS[@]+"${ARGS[@]}"}
[ $# = 0 ] || { echo "usage: load.sh [--project <name> | --all-projects]" >&2; exit 2; }
max=${LIVE_MAX:-$(python3 -I "$LOOP/projects.py" top live_terminal_max)} || exit 2
if [ "$ALL_PROJECTS" = 1 ]; then names=$(pall) || exit 2; else names=$PROJECT; fi
roots=$(for p in $names; do python3 -I "$LOOP/projects.py" get "$p" ws_root || exit 2; done) || exit 2
ps_json=$(orca worktree ps --json --limit 100000) || { echo "orca worktree ps failed (an orca error). Stop." >&2; exit 1; }
[ "$(jq -r '.result.truncated' <<<"$ps_json")" = false ] || { echo "orca worktree ps output is truncated. Stop." >&2; exit 1; }
n=$(jq --arg roots "$roots" '($roots | split("\n") | map(select(. != "") | rtrimstr("/") + "/")) as $r
  | [.result.worktrees[] | select(.path as $p | any($r[]; . as $b | $p | startswith($b))) | .liveTerminalCount // 0] | add // 0' <<<"$ps_json")
[ "$n" -ge "$max" ] || exit 1
echo "$n"
