#!/bin/bash
# Test merge.sh against a fake gh and orca. No network. Usage: bash test-merge.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
# Fake gh. FAKE_* env vars set the scenario. Each call is logged to $T/log.
# One clock ticks on every gh call. The head is "new" once the clock passes FAKE_HEAD_AFTER.
# The old head carries passing checks, so a script that does not wait for the new head
# reads them and merges the old head. The new head gets checks after FAKE_CHECKS_AFTER rollup reads.
# Two fake projects. The fake gh refuses any repo but $FAKE_REPO (default o/alpha).
cat > "$T/projects.json" <<J
{"projects": {"alpha": {"repo": "o/alpha"}, "beta": {"repo": "o/beta"}}}
J
jq '{projects: {alpha: .projects.alpha}}' "$T/projects.json" > "$T/alpha.json"
export PROJECTS_JSON=$T/alpha.json BOT_HOME=$T/home
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
echo "$*" >> "$T/log"
case "$*" in *"-R ${FAKE_REPO:-o/alpha}"*) ;; *) echo "fake gh: wrong repo: $*" >&2; exit 1 ;; esac
c() { local f="$T/$1"; local n=$(( $(cat "$f" 2>/dev/null || echo 0) + 1 )); echo $n > "$f"; echo $n; }
tick=$(c clock)
[ "$tick" -gt "$FAKE_HEAD_AFTER" ] && head=new || head=old
checks() { [ "$head" = old ] || [ "$(cat "$T/rollup" 2>/dev/null || echo 0)" -gt "$FAKE_CHECKS_AFTER" ]; }
case "$1 $2" in
  "pr update-branch") echo "$FAKE_UPDATE_OUT" >&2; exit 0 ;;
  "pr view")
    case "$*" in
      *headRefOid*) c head >/dev/null; echo $head ;;
      *statusCheckRollup*) [ $head = new ] && c rollup >/dev/null; checks && echo 1 || echo 0 ;;
    esac ;;
  "pr checks") checks || { echo "no checks reported" >&2; exit 1; }; [ "${FAKE_CI_FAIL:-0}" = 1 ] && exit 1; exit 0 ;;
  "pr merge") echo $head > "$T/merged"; exit 0 ;;
esac
GH
printf '#!/bin/bash\nexit ${FAKE_ORCA_RC:-0}\n' > "$T/bin/orca"
chmod +x "$T/bin/"*

fail=0
run() { # name expected-exit expected-output-substring [--project <name>]
  rm -f "$T/log" "$T/head" "$T/rollup" "$T/clock" "$T/merged"
  out=$(PATH="$T/bin:$PATH" T="$T" MERGE_POLL_SECS=0 MERGE_HEAD_SECS=0 bash "$HERE/merge.sh" "${@:4}" 622 1 2>&1); rc=$?
  if [ "$rc" = "$2" ] && grep -q "$3" <<<"$out"; then echo "ok   $1"; else echo "FAIL $1 (exit $rc): $out"; fail=1; fi
}
export FAKE_UPDATE_OUT="✓ PR branch updated"
# The bug on PRs 622 and 632: the head moves late and checks appear late.
FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=3 run "late head, late checks: merges" 0 "merged #622"
[ "$(cat "$T/merged" 2>/dev/null)" = new ] || { echo "FAIL merged before the new head had checks"; fail=1; }
# CI fails on the new head: stop, do not merge.
FAKE_CI_FAIL=1 FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=0 run "ci fails: stops" 1 "CI did not pass"
[ -e "$T/merged" ] && { echo "FAIL merge called after CI failed"; fail=1; }
# Checks never appear: stop, do not merge.
FAKE_HEAD_AFTER=0 FAKE_CHECKS_AFTER=999 run "no checks ever: stops" 1 "no checks on the head"
grep -q "pr merge" "$T/log" && { echo "FAIL merge called with no checks"; fail=1; }
# Branch already up to date: the head never moves, no wait for a new head.
FAKE_UPDATE_OUT="! PR branch already up-to-date" FAKE_HEAD_AFTER=999 FAKE_CHECKS_AFTER=0 run "already up to date: merges" 0 "merged #622"
[ "$(cat "$T/head")" = 1 ] || { echo "FAIL waited for a new head on an up-to-date branch"; fail=1; }

# Background mode: returns at once, the log ends with a FINAL: line.
bg() { # name expected-final-substring [--project <name>]
  rm -f "$T/log" "$T/head" "$T/rollup" "$T/clock" "$T/merged" "$T/logs/merge-622.log"
  out=$(PATH="$T/bin:$PATH" T="$T" MERGE_LOG_DIR="$T/logs" MERGE_POLL_SECS=0 MERGE_HEAD_SECS=0 bash "$HERE/merge.sh" "${@:3}" --bg 622 1 2>&1)
  grep -q "Log: $T/logs/merge-622.log" <<<"$out" || { echo "FAIL $1: no log path printed: $out"; fail=1; return; }
  for i in $(seq 1 100); do tail -1 "$T/logs/merge-622.log" 2>/dev/null | grep -q '^FINAL:' && break; sleep 0.1; done
  last=$(tail -1 "$T/logs/merge-622.log" 2>/dev/null)
  if grep -q "$2" <<<"$last"; then echo "ok   $1"; else echo "FAIL $1: last line: $last"; fail=1; fi
}
FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=3 bg "background merge: FINAL merged" "^FINAL: merged #622"
FAKE_CI_FAIL=1 FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=0 bg "background CI fail: FINAL not merged" "^FINAL: not merged #622 (exit 1)"
grep -q "CI did not pass" "$T/logs/merge-622.log" || { echo "FAIL background log lacks the reason"; fail=1; }
# The item comment fails after the merge: FINAL still says merged, and the log says the comment failed.
FAKE_ORCA_RC=1 FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=3 bg "background merge, comment fails: FINAL merged" "^FINAL: merged #622"
grep -q "item comment failed" "$T/logs/merge-622.log" || { echo "FAIL background log does not say the comment failed"; fail=1; }
# Projects (#243): merge.sh works on the named project's repo, in the foreground and in the background.
export PROJECTS_JSON=$T/projects.json
FAKE_REPO=o/beta FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=3 run "--project beta: merges beta's PR" 0 "merged #622" --project beta
FAKE_REPO=o/beta FAKE_HEAD_AFTER=6 FAKE_CHECKS_AFTER=3 bg "--project beta in the background: FINAL merged" "^FINAL: merged #622" --project beta
run "two projects and no --project: exit 2" 2 "name one with --project"
[ -e "$T/log" ] && { echo "FAIL gh called with two projects and no --project"; fail=1; }
exit $fail
