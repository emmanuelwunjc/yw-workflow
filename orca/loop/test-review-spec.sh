#!/bin/bash
# Test review-spec.sh against a fake gh. No network. Usage: bash test-review-spec.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
# Fake gh, real shape: it prints the second parent of each merge after <from>. After abc1234 there is
# no merge. After dead123 the PR merged main (m2). After beef123 it merged branch ticket-650 (g1).
# "compare/<sha>...main" says if <sha> is on main: m2 is ("ahead"), g1 is not ("diverged").
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
case "$*" in
  *headRefName*) echo ticket-700 ;;
  *headRefOid*) echo headsha123 ;;
  *compare/abc1234...headsha123*) ;;
  *compare/dead123...headsha123*) echo m2 ;;
  *compare/beef123...headsha123*) echo g1 ;;
  *compare/m2...main*) echo ahead ;;
  *compare/g1...main*) echo diverged ;;
  *compare/*) exit 1 ;;
  *body*) echo "Fix the sweep stall" ;;
esac
GH
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"
cd "$T"   # a broken run writes its stray folders here, never in the skill folder
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
FIX="FIX ROUND of PR 701. Review ONLY the fix diff: git diff abc1234..headsha123. Check the fix, that each new case fails on the old code, and that the fix opened no new defect."

bash "$HERE/review-spec.sh" 701 700 "$T/plain" >/dev/null; check "plain spec: written" $? 0
for t in adversarial codereview; do
  check "plain $t: line 1 names the PR (orca cuts a prompt to 200 characters)" "$(head -1 "$T/plain/$t.txt")" "Review of PR 701."
  check "plain $t: no FIX ROUND" "$(grep -c 'FIX ROUND' "$T/plain/$t.txt")" 0
  check "plain $t: head commit filled in" "$(grep -c 'ticket-700 at headsha123' "$T/plain/$t.txt")" 1
  check "plain $t: the review posts at the head commit" "$(grep -c 'commit_id=headsha123' "$T/plain/$t.txt")" 1
done
bash "$HERE/review-spec.sh" --fix abc1234 --finding "the log drops a row" 701 700 "$T/fix" >/dev/null; check "fix spec: written" $? 0
for t in adversarial codereview; do
  check "fix $t: the FIX ROUND line comes first" "$(head -1 "$T/fix/$t.txt")" "$FIX"
  check "fix $t: the earlier finding" "$(grep -c 'Earlier blocking finding: the log drops a row' "$T/fix/$t.txt")" 1
done
bash "$HERE/review-spec.sh" --fix abc1234 701 700 "$T/nofind" >/dev/null; check "fix with no finding: written" $? 0
check "fix with no finding: FIX ROUND line first" "$(head -1 "$T/nofind/adversarial.txt")" "$FIX"
check "fix with no finding: no finding line" "$(grep -c 'Earlier blocking finding' "$T/nofind/adversarial.txt")" 0
bash "$HERE/review-spec.sh" --fix dead123 701 700 "$T/merge" >/dev/null; check "fix over a merge of main: written" $? 0
check "fix over a merge of main: the fix commits only" "$(head -1 "$T/merge/adversarial.txt" | grep -c 'git log -p --no-merges --first-parent dead123..headsha123')" 1
check "fix over a merge of main: no plain diff" "$(head -1 "$T/merge/adversarial.txt" | grep -c 'git diff')" 0
bash "$HERE/review-spec.sh" --fix beef123 701 700 "$T/branch" >/dev/null; check "fix over a merge of another branch: written" $? 0
check "fix over a merge of another branch: the full diff" "$(head -1 "$T/branch/adversarial.txt" | grep -c 'git diff beef123..headsha123')" 1
o=$(bash "$HERE/review-spec.sh" --fix fff9999 701 700 "$T/nocmp" 2>&1); check "compare fails: exit 1 and says so" "$?:$(echo "$o" | grep -c 'gh api compare fff9999')" "1:1"
check "compare fails: no spec" "$(ls "$T/nocmp" 2>/dev/null | wc -l | tr -d ' ')" 0
bash "$HERE/review-spec.sh" --fix main 701 700 >/dev/null 2>&1; check "--fix with no sha: exit 2" $? 2
bash "$HERE/review-spec.sh" --fix 701 700 >/dev/null 2>&1; check "--fix with no sha, PR next: exit 2" $? 2
bash "$HERE/review-spec.sh" --finding x 701 700 >/dev/null 2>&1; check "--finding with no --fix: exit 2" $? 2

# Octopus merge, with a real git repo (review of 2026-11-24, round 3). After the reviewed commit B the PR
# merges main (gh pr update-branch), then runs `git merge main t650`: one merge, 3 parents.
# This fake gh answers compare from the real repo and runs the real --jq on it.
G="git -C $T/repo -c user.name=t -c user.email=t@t"
git init -q -b main "$T/repo"
c() { echo "$2" > "$T/repo/$1"; $G add "$1"; $G commit -qm "$1"; }
c base base; $G checkout -qb pr; c fix0 fix0; B=$($G rev-parse HEAD)
$G checkout -q main; c m1 m1; $G checkout -q -b t650 main; c t650 evil_ticket_code
$G checkout -q main; c m2 m2; $G checkout -q pr; $G merge -q --no-edit main
MAINONLY=$($G rev-parse HEAD); $G checkout -q main; c m3 m3; $G checkout -q pr
$G merge -q --no-edit main t650 >/dev/null; OCTO=$($G rev-parse HEAD)
check "octopus probe: the merge has 3 parents" "$($G rev-list --parents -n1 HEAD | wc -w | tr -d ' ')" 4
mkdir "$T/bin2"
cat > "$T/bin2/gh" <<'GH'
#!/bin/bash
G="git -C $REPO"
case "$*" in
  *headRefName*) echo pr ;;
  *headRefOid*) echo "$HEAD_SHA" ;;
  *body*) echo "Fix the sweep stall" ;;
  "api "*compare/*)
    r=${2##*/compare/}; a=${r%%...*}; b=${r#*...}
    if [ "$b" = main ]; then
      if [ "$($G rev-parse "$a")" = "$($G rev-parse main)" ]; then s=identical
      elif $G merge-base --is-ancestor "$a" main; then s=ahead; else s=diverged; fi
      echo "{\"status\":\"$s\"}" | jq -r "$4"
    else
      $G rev-list --reverse --parents "$a..$b" | jq -R -s -r '{commits: [split("\n")[] | select(length > 0)
        | split(" ") | {sha: .[0], parents: [.[1:][] | {sha: .}]}]}' | jq -r "$4"
    fi ;;
  *) exit 1 ;;
esac
GH
chmod +x "$T/bin2/gh"
spec() { REPO=$T/repo HEAD_SHA=$1 PATH="$T/bin2:$PATH" bash "$HERE/review-spec.sh" --fix "$B" 701 700 "$T/$2" >/dev/null; }
spec "$MAINONLY" mainonly; check "real git, a merge of main only: written" $? 0
check "real git, a merge of main only: the fix commits only" "$(head -1 "$T/mainonly/adversarial.txt" | grep -c "git log -p --no-merges --first-parent $B..$MAINONLY")" 1
spec "$OCTO" octo; check "real git, octopus of main and t650: written" $? 0
check "real git, octopus of main and t650: the full diff" "$(head -1 "$T/octo/adversarial.txt" | grep -c "git diff $B..$OCTO")" 1
cmd=$(head -1 "$T/octo/adversarial.txt" | sed -n 's/.*Review ONLY the fix[^:]*: \(git [^.]*\.\.[0-9a-f]*\).*/\1/p')
check "real git, octopus: the named command shows the t650 code" "$($G ${cmd#git } | grep -c evil_ticket_code)" 1
exit $fail
