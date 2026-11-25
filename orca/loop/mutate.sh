#!/bin/bash
# Prove a skill's self-test can fail: break one line in a temp copy of the skill, run its test there.
# The live skill folder is never written, and nothing is removed outside the mktemp dir,
# so a worker runs this with no permission prompt.
# Usage: bash mutate.sh <skill-dir> <file> <test-script> <old-text> <new-text> [label]
# e.g.   bash mutate.sh . free_tickets.py test-free.sh 'print(f"NO SLICE: #{n}")' 'pass' no-slice-line
# <file> and <test-script> are paths inside <skill-dir>. A .py test runs with python3, any other with bash.
# Exit 0: the test caught the break. 1: the break survived. 2: bad input, or <old-text> is not in <file>.
set -u
[ $# -ge 5 ] || { sed -n '5,6p' "$0" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
case "$1" in /*) src=$1 ;; *) src=$HERE/$1 ;; esac
# <file> and <test> stay inside the skill copy: no "..".
case "/$2/$3/" in */../*) echo "no .. in <file> or <test>" >&2; exit 2 ;; esac
[ -f "$src/$2" ] && [ -f "$src/$3" ] || { echo "no $src/$2 or $src/$3" >&2; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cp -R "$src/." "$T/"
python3 - "$T/$2" "$4" "$5" <<'PY' || exit 2
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
if old not in s:
    sys.exit(f"not found in {p}: {old}")
open(p, "w").write(s.replace(old, new, 1))
PY
label=${6:-$4}
case "$3" in *.py) run=python3 ;; *) run=bash ;; esac
if "$run" "$T/$3" >/dev/null 2>&1; then echo "SURVIVED: $label"; exit 1; fi
echo "caught: $label"
