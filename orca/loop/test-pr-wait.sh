#!/bin/bash
# Test pr_wait.sh against a fake gh and orca. No network. Usage: bash test-pr-wait.sh
# The fake data uses the real formats: a worktree branch is "refs/heads/<name>", and
# orca worktree ps cuts each prompt to 200 characters.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"; cd "$T"
# NOW = 2026-11-24T20:00:00Z. O is 4 hours before, N 1 hour before.
OK='[{"status":"COMPLETED","conclusion":"SUCCESS"}]'; RUN='[{"status":"IN_PROGRESS","conclusion":""}]'
BAD='[{"status":"COMPLETED","conclusion":"FAILURE"}]'
rev() { echo '[{"commit":{"oid":"'$1'"},"submittedAt":"2026-11-24T19:00:00Z"}]'; }
pr() { # number branch head mergeable updatedAt checks reviews [isDraft]
  echo '{"number":'$1',"headRefName":"'$2'","headRefOid":"'$3'","mergeable":"'$4'","updatedAt":"'$5'","statusCheckRollup":'$6',"reviews":'$7',"isDraft":'${8:-false}'}'; }
O=2026-11-24T16:00:00Z; N=2026-11-24T19:00:00Z
cat > prs.json <<J
[$(pr 1 b1 h1 MERGEABLE $N "$OK" '[]'),
 $(pr 2 b2 h2 CONFLICTING $N "$OK" "$(rev h2)"),
 $(pr 3 b3 h3 MERGEABLE $N "$OK" "$(rev h0)"),
 $(pr 4 b4 h4 MERGEABLE $O "$BAD" "$(rev h4)"),
 $(pr 5 b5 h5 MERGEABLE $O "$BAD" "$(rev h5)"),
 $(pr 6 b6 h6 MERGEABLE $N "$RUN" '[]'),
 $(pr 7 b7 h7 MERGEABLE $N "$OK" "$(rev h7)"),
 $(pr 8 b8 h8 MERGEABLE $O "$OK" '[]'),
 $(pr 9 b9 h9 MERGEABLE $N '[]' '[]'),
 $(pr 10 b10 h10 MERGEABLE $N "$RUN" "$(rev h0)"),
 $(pr 11 b11 h11 MERGEABLE $N "$OK" '[]'),
 $(pr 12 b12 h12 MERGEABLE $N "$OK" "$(rev h0)"),
 $(pr 13 b13 h13 MERGEABLE $N "$OK" '[{"commit":{"oid":"hA"},"submittedAt":"2026-11-24T17:00:00Z"},{"commit":{"oid":"hB"},"submittedAt":"2026-11-24T18:00:00Z"}]'),
 $(pr 14 b14 h14 MERGEABLE $N "$OK" '[]' true),
 $(pr 15 b15 h15 MERGEABLE $N "$OK" "$(rev h0)" true),
 $(pr 16 b16 h16 MERGEABLE $N "$OK" "$(rev hM)"),
 $(pr 17 b17 h17 MERGEABLE $N "$OK" "$(rev hX)"),
 $(pr 19 b19 h19 MERGEABLE $N "$OK" '[]'),
 $(pr 20 b20 h20 MERGEABLE $O "$BAD" "$(rev h20)"),
 $(pr 21 b21 h21 MERGEABLE $N "$OK" "$(rev hP)"),
 $(pr 22 b22 h22 MERGEABLE $N "$OK" '[]'),
 $(pr 23 b23 h23 MERGEABLE $N "$OK" "$(rev hF)"),
 $(pr 24 b24 h31 MERGEABLE $N "$OK" "$(rev b31x)"),
 $(pr 25 b25 h25 MERGEABLE $N "$OK" '[{"commit":{"oid":"h25"},"submittedAt":"2026-11-24T19:00:00Z"},{"commit":null,"submittedAt":null,"state":"PENDING"}]'),
 $(pr 26 b26 h26 MERGEABLE $N "$OK" '[{"commit":{"oid":"h0"},"submittedAt":null,"state":"PENDING"}]'),
 $(pr 27 b27 h27 MERGEABLE $N "$OK" "$(rev hO)")]
J
# A real reviewer prompt: the spec cut to 200 characters. "review done: PR <n>" is far past the cut.
long() { python3 -c 'import sys, json; print(json.dumps((sys.argv[1] + " x" * 200)[:200]))' "$1"; }   # a JSON string
P11=$(long "Review of PR 11. Repo: twenty (~/code/twenty). You are an independent adversarial reviewer (skill yw-workflow:fresh-eye). You did not write this change. Try to break it.")
P12=$(long "Review of PR 12. Repo: twenty (~/code/twenty). You are an independent adversarial reviewer.")
cat > ps.json <<J
{"result":{"worktrees":[
 {"branch":"refs/heads/b5","displayName":"B5","agents":[{"state":"working","prompt":"x","taskTitle":"x"}]},
 {"branch":"refs/heads/b4","displayName":"B4","agents":[{"state":"done","prompt":"fix PR 4","taskTitle":"x"}]},
 {"branch":"","displayName":"Review fresh eye adversarial 51","agents":[{"state":"working","prompt":$P11,"taskTitle":"x"}]},
 {"branch":"","displayName":"Review fresh eye adversarial 52","agents":[{"state":"done","prompt":$P12,"taskTitle":"x"}]},
 {"branch":"","displayName":"Review pr 20","agents":[{"state":"working","prompt":"y","taskTitle":"y"}]},
 {"branch":"","displayName":"Review pr 19 fix","agents":[{"state":"working","prompt":"y","taskTitle":"y"}]},
 {"branch":"","displayName":"x","agents":[{"state":"working","prompt":"y","taskTitle":"FIX ROUND of PR 22. Review ONLY..."}]}]}}
J
# Fake gh: "pr list" prints prs.json. "api .../compare/<base>...<head>" prints each commit after <base>
# with its parents, in the real shape: the main commits a merge brought in are listed too, with 1 parent.
#   hM..h16: main m1, m2, then h16 merges main (parents hM, m2). Only a merge on the PR's own line.
#   hX..h17: main m1, a fix f1, then h17 merges main (parents f1, m1).
#   hP..h21: the live PR 774 shape: main m1..m3, merge d1 (hP, m2), main m4 (m3), merge h21 (d1, m4).
#   hF..h23: a force push: h23 is a merge whose first parent zz does not lead back to hF.
#   b31x..h31: a merge of branch ticket-650 (g1, parent m0) into the PR: head h31 has parents (b31x, g1).
#   hO..h27: an octopus `git merge origin/main origin/ticket-650`: head h27 has parents (hO, m1, g1).
# "compare/<sha>...main" says if <sha> is on main: the m commits are ("ahead"), g1 is not ("diverged").
#   any other: one fix commit <head> on <base>.
# Two fake projects: the fake gh answers only for o/alpha, so a run that reads another repo fails.
echo '{"projects": {"alpha": {"repo": "o/alpha"}, "beta": {"repo": "o/beta"}}}' > "$T/projects.json"
export PROJECTS_JSON=$T/projects.json BOT_HOME=$T/home
cat > bin/gh <<'GH'
#!/bin/bash
case "$*" in *o/alpha*) ;; *) exit 1 ;; esac
c() { echo '{"sha":"'$1'","parents":['$2']}'; }
case "$*" in
  "pr list"*) cat prs.json ;;
  *compare/hM...h16*) echo "[$(c m1 '"m0"'),$(c m2 '"m1"'),$(c h16 '"hM","m2"')]" ;;
  *compare/hX...h17*) echo "[$(c m1 '"m0"'),$(c f1 '"hX"'),$(c h17 '"f1","m1"')]" ;;
  *compare/m*...main*) echo ahead ;;
  *compare/*...main*) echo diverged ;;
  *compare/hO...h27*) echo "[$(c m1 '"m0"'),$(c g1 '"m0"'),$(c h27 '"hO","m1","g1"')]" ;;
  *compare/b31x...h31*) echo "[$(c g1 '"m0"'),$(c h31 '"b31x","g1"')]" ;;
  *compare/hF...h23*) echo "[$(c h23 '"zz","m1"')]" ;;
  *compare/hP...h21*) echo "[$(c m1 '"m0"'),$(c m2 '"m1"'),$(c m3 '"m2"'),$(c d1 '"hP","m2"'),$(c m4 '"m3"'),$(c h21 '"d1","m4"')]" ;;
  *compare/*) r=${2##*/}; echo "[$(c "${r#*...}" "\"${r%%...*}\"")]" ;;
  *) exit 1 ;;
esac
GH
printf '#!/bin/bash\ncat ps.json\n' > bin/orca
chmod +x bin/*
export PATH="$T/bin:$PATH" PR_WAIT_NOW=2026-11-24T20:00:00Z
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
out=$(bash "$HERE/pr_wait.sh" --project alpha); rc=$?
line() { echo "$out" | grep "^WAIT $1 " | cut -d' ' -f3; }
field4() { echo "$out" | grep "^WAIT $1 " | cut -d' ' -f4; }
check "runs" $rc 0
check "CI passes, no review: no-reviewer" "$(line 1)" no-reviewer
check "merge conflict: conflict" "$(line 2)" conflict
check "a push after the last review: fix-review" "$(line 3)" fix-review
check "fix-review names the last reviewed commit" "$(field4 3)" h0
check "4 hours quiet, only a done agent: idle" "$(line 4)" idle
check "4 hours quiet, a working agent on refs/heads/<branch>: no line" "$(line 5)" ""
check "CI still runs, no review: no line" "$(line 6)" ""
check "reviewed at head, CI passes: no line" "$(line 7)" ""
check "no review and quiet: one line" "$(echo "$out" | grep -c '^WAIT 8 ')" 1
check "no review and quiet: no-reviewer first" "$(line 8)" no-reviewer
check "no checks yet, no review: no line" "$(line 9)" ""
check "a push after review, CI still runs: no line" "$(line 10)" ""
check "a working reviewer, 200-char prompt: no line" "$(line 11)" ""
check "its reviewer is done: fix-review" "$(line 12)" fix-review
check "two reviews: the newest commit" "$(field4 13)" hB
check "a draft with no review: no line" "$(line 14)" ""
check "a draft with an old review: no line" "$(line 15)" ""
check "only a merge of main after the review: no line" "$(line 16)" ""
check "a fix commit and a merge after the review: fix-review" "$(line 17)" fix-review
check "a working reviewer named in its workspace (real form \"Review pr 19 fix\"): no line" "$(line 19)" ""
check "4 hours quiet, a working reviewer: no idle line" "$(line 20)" ""
check "two merges of main after the review, live PR 774 shape: no line" "$(line 21)" ""
check "a working reviewer named in its task title: no line" "$(line 22)" ""
check "a force push that ends in a merge: fix-review" "$(line 23)" fix-review
check "a merge of another branch after the review: fix-review" "$(line 24)" fix-review
check "a merge of another branch: names the reviewed commit" "$(field4 24)" b31x
check "a PENDING review (null submittedAt) beside a review at head: no line" "$(line 25)" ""
check "only a PENDING review: no-reviewer" "$(line 26)" no-reviewer
check "an octopus merge of main and another branch after the review: fix-review" "$(line 27)" fix-review
check "two projects and no --project: exit 2" "$(bash "$HERE/pr_wait.sh" >/dev/null 2>&1; echo $?)" 2
o=$(bash "$HERE/pr_wait.sh" --project beta 2>/dev/null); rc=$?
check "--project beta reads beta's repo (the fake gh knows only alpha): exit 1, no WAIT line" "$rc:$(echo "$o" | grep -c WAIT)" "1:0"
# A failure prints no WAIT line at all, so the sweep acts on nothing.
sed -i '' 's/^  \*compare\/\*) r=.*/  *compare\/*) exit 1 ;;/' bin/gh
o=$(bash "$HERE/pr_wait.sh" --project alpha 2>"$T/err"); rc=$?
check "compare fails: exit 1" "$rc" 1
check "compare fails: no WAIT line" "$(echo "$o" | grep -c WAIT)" 0
check "compare fails: says so" "$(grep -c '^pr_wait: gh api compare' "$T/err")" 1
printf '#!/bin/bash\nexit 1\n' > bin/orca
err=$(bash "$HERE/pr_wait.sh" --project alpha 2>&1 >/dev/null); check "orca fails: exit 1 and says so" "$?:$err" "1:pr_wait: orca worktree ps failed"
printf '#!/bin/bash\nexit 1\n' > bin/gh
err=$(bash "$HERE/pr_wait.sh" --project alpha 2>&1 >/dev/null); check "gh fails: exit 1 and says so" "$?:$err" "1:pr_wait: gh pr list failed"
exit $fail
