#!/bin/bash
# usage: review-spec.sh [--fix <from-sha> [--finding "<text>"]] <pr> <issue> [outdir]
# Writes adversarial.txt and codereview.txt (reviewer specs) for a twenty PR. Fails when a placeholder stays empty.
# Line 1 names the PR ("Review of PR <n>." or "FIX ROUND of PR <n>. ..."): orca worktree ps cuts a prompt
# to 200 characters, and the sweep's pr_wait.sh finds a working reviewer by that line.
# --fix writes a fix-round spec: the reviewer reads only the fix since <from-sha> (the commit the last
# review read). When each merge in that range merges main (gh pr update-branch), the reviewer reads the
# fix commits only (git log -p --no-merges --first-parent, which leaves out main). A merge with any other
# parent (a branch such as ticket-650, also in an octopus merge of main and ticket-650) gets the full git diff.
# --finding names the earlier blocking finding.
# Test: bash test-review-spec.sh
set -e
USAGE='usage: review-spec.sh [--fix <from-sha> [--finding "<text>"]] <pr> <issue> [outdir]'
FROM=; FINDING=
while [ $# -gt 0 ]; do
  case "$1" in
    --fix) FROM=$2; shift 2 ;;
    --finding) FINDING=$2; shift 2 ;;
    *) break ;;
  esac
done
[ -z "$FINDING" ] || [ -n "$FROM" ] || { echo "--finding needs --fix"; exit 2; }
[ -z "$FROM" ] || [[ "$FROM" =~ ^[0-9a-f]{7,40}$ ]] || { echo "--fix needs a commit sha, got: $FROM"; exit 2; }
PR=$1; ISSUE=$2; OUT=${3:-$(mktemp -d)}
[ -n "$PR" ] && [ -n "$ISSUE" ] || { echo "$USAGE"; exit 2; }
R=georgetown-mdi-gates4/twenty; D=$(dirname "$0")
BRANCH=$(gh pr view "$PR" -R $R --json headRefName --jq .headRefName)
SHA=$(gh pr view "$PR" -R $R --json headRefOid --jq .headRefOid)
BODY=$(gh issue view "$ISSUE" -R $R --json body --jq .body)
[ -n "$BRANCH" ] && [ -n "$SHA" ] && [ -n "$BODY" ] || { echo "empty branch, commit or issue body: no spec written"; exit 1; }
FIRST="Review of PR $PR."
if [ -n "$FROM" ]; then
  # Every parent after the first of each merge after FROM (an octopus merge has more than 2 parents).
  # Only when each one is on main is it safe to leave the merges out. A merge of another branch
  # (e.g. ticket-650) brings new code: read the full diff.
  merged=$(gh api "repos/$R/compare/$FROM...$SHA" --jq '.commits[] | select(.parents | length >= 2) | .parents[1:][].sha') \
    || { echo "gh api compare $FROM...$SHA failed: no spec written"; exit 1; }
  DIFF="the fix diff: git diff $FROM..$SHA"
  if [ -n "$merged" ]; then
    DIFF="the fix commits only: git log -p --no-merges --first-parent $FROM..$SHA"
    for p in $merged; do
      st=$(gh api "repos/$R/compare/$p...main" --jq .status) \
        || { echo "gh api compare $p...main failed: no spec written"; exit 1; }
      case "$st" in ahead|identical) ;; *) DIFF="the fix diff: git diff $FROM..$SHA" ;; esac
    done
  fi
  FIRST="FIX ROUND of PR $PR. Review ONLY $DIFF. Check the fix, that each new case fails on the old code, and that the fix opened no new defect."
  [ -z "$FINDING" ] || FIRST="$FIRST
Earlier blocking finding: $FINDING"
fi
mkdir -p "$OUT"
for t in adversarial codereview; do
  F=$D/reviewer-$t.txt
  BRANCH="$BRANCH" SHA="$SHA" BODY="$BODY" PR="$PR" FIRST="$FIRST" python3 -I -c '
import os,sys
e=os.environ
s=open(sys.argv[1]).read()
s=s.replace("<branch>",e["BRANCH"]).replace("<commit>",e["SHA"]).replace("<the ticket or PR body, pasted in>",e["BODY"]).replace("<n>",e["PR"])
open(sys.argv[2],"w").write(e["FIRST"]+"\n"+s)' "$F" "$OUT/$t.txt"
  grep -n '<branch>\|<commit>\|<n>\|pasted in' "$OUT/$t.txt" && { echo "placeholder left in $t.txt"; exit 1; } || true
done
echo "$OUT"
echo "start each with: bash $D/start.sh - $OUT/<adversarial or codereview>.txt pr-$PR (no item link, one reviewer of each kind per PR)"
