#!/bin/bash
# Test projects.py with two fake projects. No network. Usage: bash test-projects.sh
set -u
D=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
P() { python3 -I "$D/projects.py" "$@" 2>&1; echo "exit $?"; }
cat > "$T/two.json" <<J
{"live_terminal_max": 9, "projects": {
  "alpha": {"repo": "o/alpha", "worker_cap": 8, "ws_root": "~/ws/alpha", "labels": {"work": "a:", "skip": ["x", "y"]}},
  "beta":  {"repo": "o/beta",  "worker_cap": 3, "ws_root": "/abs/beta", "labels": {"work": "b:", "skip": []}}}}
J
jq '{projects: {alpha: .projects.alpha}}' "$T/two.json" > "$T/one.json"
export PROJECTS_JSON=$T/two.json
check "get reads the named project, not the other" "$(P get beta repo)" "$(printf 'o/beta\nexit 0')"
check "get reads alpha's own value" "$(P get alpha worker_cap)" "$(printf '8\nexit 0')"
check "a dotted key reads inside an object" "$(P get beta labels.work)" "$(printf 'b:\nexit 0')"
check "a list prints one item per line" "$(P get alpha labels.skip)" "$(printf 'x\ny\nexit 0')"
check "~/ becomes the home folder" "$(P get alpha ws_root)" "$(printf '%s\nexit 0' "$HOME/ws/alpha")"
check "an absolute path stays" "$(P get beta ws_root)" "$(printf '/abs/beta\nexit 0')"
check "top reads a shared value" "$(P top live_terminal_max)" "$(printf '9\nexit 0')"
check "list names every project" "$(P list)" "$(printf 'alpha\nbeta\nexit 0')"
check "name: a known project" "$(P name beta)" "$(printf 'beta\nexit 0')"
check "unknown project: exit 2" "$(P get gamma repo | tail -1)" "exit 2"
check "unknown key: exit 2" "$(P get alpha nope | tail -1)" "exit 2"
check "unknown dotted key: exit 2" "$(P get alpha labels.nope | tail -1)" "exit 2"
check "two projects and none named: refuse to guess" "$(P name | tail -1)" "exit 2"
check "get with an empty name and two projects: exit 2" "$(P get '' repo | tail -1)" "exit 2"
check "no usage: exit 2" "$(P | tail -1)" "exit 2"
check "one project and none named: that one" "$(PROJECTS_JSON=$T/one.json P name)" "$(printf 'alpha\nexit 0')"
check "one project, empty name in get: that one" "$(PROJECTS_JSON=$T/one.json P get '' repo)" "$(printf 'o/alpha\nexit 0')"
check "a missing file: exit 2" "$(PROJECTS_JSON=$T/none.json P list | tail -1)" "exit 2"
# Which file: PROJECTS_JSON, else $BOT_HOME/projects.json, else the sample beside the script.
mkdir "$T/home" && cp "$T/one.json" "$T/home/projects.json"
check "BOT_HOME/projects.json when PROJECTS_JSON is unset" "$(unset PROJECTS_JSON; BOT_HOME=$T/home P list)" "$(printf 'alpha\nexit 0')"
check "the sample beside the script when neither is set" "$(unset PROJECTS_JSON; BOT_HOME=$T/nohome P list)" "$(printf 'twenty\nexit 0')"
[ $fail = 0 ] && echo "test-projects ok"
exit $fail
