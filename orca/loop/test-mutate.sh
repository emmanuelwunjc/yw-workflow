#!/bin/bash
# Test mutate.sh on a fake skill in a mktemp dir. Usage: bash test-mutate.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/skill"
printf 'add() { echo $(( $1 + $2 )); }\n# a comment\n' > "$T/skill/f.sh"
printf 'HERE=$(dirname "$0"); . "$HERE/f.sh"; [ "$(add 2 3)" = 5 ]\n' > "$T/skill/test.sh"
cp "$T/skill/f.sh" "$T/orig"
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
M="$HERE/mutate.sh"
out=$(bash "$M" "$T/skill" f.sh test.sh '$1 + $2' '$1 - $2' minus); check "a real break is caught" "$?:$out" "0:caught: minus"
out=$(bash "$M" "$T/skill" f.sh test.sh 'a comment' 'b comment' cmt); check "a harmless edit survives" "$?:$out" "1:SURVIVED: cmt"
bash "$M" "$T/skill" f.sh test.sh 'no such text' x 2>/dev/null; check "old text not found: exit 2" $? 2
bash "$M" "$T/skill" f.sh 2>/dev/null; check "too few args: exit 2" $? 2
# The allow rule names a skill folder, so <file> and <test> must stay inside the temp copy.
printf 'exit 1\n' > "$T/out.sh"
# Other guards and checks also exit 2, so each case needs the .. guard's own message.
err=$(bash "$M" "$T/skill" f.sh ../out.sh 'a comment' x 2>&1 >/dev/null); check "test path with ..: exit 2, refused by the .. guard" "$?:$err" "2:no .. in <file> or <test>"
err=$(bash "$M" "$T/skill" ../skill/f.sh test.sh 'a comment' x 2>&1 >/dev/null); check "file path with ..: exit 2, refused by the .. guard" "$?:$err" "2:no .. in <file> or <test>"
# A Python test runs with python3, so a no-op survives and a real break is caught.
printf 'def add(a, b):\n    return a + b\n' > "$T/skill/f.py"
printf 'import f\nassert f.add(2, 3) == 5\n' > "$T/skill/test.py"
out=$(bash "$M" "$T/skill" f.py test.py 'a + b' 'a + b' noop); check "a no-op on a Python test survives" "$?:$out" "1:SURVIVED: noop"
out=$(bash "$M" "$T/skill" f.py test.py 'a + b' 'a - b' minus); check "a real break in a Python test is caught" "$?:$out" "0:caught: minus"
# A test in a subfolder of the copy (e.g. hooks/ under the bot folder) runs too.
mkdir "$T/skill/t"
printf '. "$(dirname "$0")/../f.sh"; [ "$(add 2 3)" = 5 ]\n' > "$T/skill/t/test.sh"
out=$(bash "$M" "$T/skill" f.sh t/test.sh '$1 + $2' '$1 - $2' sub); check "a test in a subfolder is caught" "$?:$out" "0:caught: sub"
cmp -s "$T/orig" "$T/skill/f.sh"; check "the source file is unchanged" $? 0
exit $fail
