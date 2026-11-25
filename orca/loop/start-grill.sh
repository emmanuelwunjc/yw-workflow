#!/bin/bash
# Open a grill on a twenty ticket as its own chat workspace that the owner answers in.
# Usage: start-grill.sh [--dry-run] <ticket> [extra topic text]
# Refuses (exit 1) when a workspace named grill-<ticket> or grill-<ticket>-* already exists.
# Stops (exit 1) when `orca worktree ps` is truncated, because a hidden row can hide that grill.
# Prints the new workspace path. --dry-run prints the orca command and runs nothing.
set -euo pipefail
R=georgetown-mdi-gates4/twenty
dry=0; [ "${1:-}" = "--dry-run" ] && { dry=1; shift; }
t=${1:?usage: start-grill.sh [--dry-run] <ticket> [extra topic text]}; shift
topics=${*:-}
case "$t" in *[!0-9]*) echo "ticket must be a number: $t" >&2; exit 1 ;; esac

ps_json=$(orca worktree ps --json --limit 100000)
[ "$(jq -r '.result.truncated' <<<"$ps_json")" = false ] || { echo "orca worktree ps output is truncated, so an open grill can hide. Stop." >&2; exit 1; }
grills=$(python3 -c '
import json, os, sys
for w in json.load(sys.stdin)["result"]["worktrees"]:
    if os.path.basename(w.get("path") or "").startswith("grill-"):
        print(w["path"])' <<<"$ps_json")
existing=$(printf '%s\n' "$grills" | grep -E "/grill-$t(-|\$)" || true)
[ -n "$existing" ] && { echo "refused: a grill workspace for #$t exists: $existing" >&2; exit 1; }

title=$(gh issue view "$t" -R $R --json title -q .title)
slug=$(printf '%s' "$title" | tr 'A-Z' 'a-z' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//' | cut -d- -f1-5)
name="grill-$t-$slug"
prompt="Repo: twenty. Run the mattpocock-skills:grill-with-docs skill (or yw-workflow:grill) on ticket #$t ($title). Read NORTH-STAR.md and the ticket (gh issue view $t -R $R) first. You interview the owner Yiming live in this chat, one decision at a time, with the AskUserQuestion tool (2 to 4 options, recommended first).${topics:+ Topics: $topics.} Answer facts yourself from the repo, never ask what the repo answers. At the end write the decisions as ONE English comment on #$t and tell the owner. Chat with the owner may be in the owner's language. Do not change code."
cmd=(orca worktree create --name "$name" --repo name:twenty --agent claude --surface chat --no-parent --activate --prompt "$prompt" --json)

if [ $dry = 1 ]; then printf '%q ' "${cmd[@]}"; echo; exit 0; fi
"${cmd[@]}" | python3 -c '
import json, sys
w = json.load(sys.stdin)["result"]["worktree"]
print(w.get("path") or w["id"].split("::", 1)[1])'
