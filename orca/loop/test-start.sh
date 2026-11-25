#!/bin/bash
# Test the start lock of start.sh against a fake gh and orca. No network. Usage: bash test-start.sh
# Two sweeps start ticket #652 at the same time: exactly one may start a worker.
# Then the same race with the lock line cut out must start two, which proves the test can fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
# Fake gh: lane comments come from $T/comments. Fake orca: an empty ps; worker-start
# waits a moment (both racers pass the re-reads first) and counts each start.
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
cat "$T/comments" 2>/dev/null; exit 0
GH
cat > "$T/bin/orca" <<'ORCA'
#!/bin/bash
case "$1 $2" in
  "worktree ps") echo '{"result":{"worktrees":[]}}' ;;
  "orchestration worker-start") sleep 1; echo x >> "$T/starts"; echo "dispatchId=d$$ workspace=id::/w/$$" ;;
esac
ORCA
chmod +x "$T/bin/"*
echo "fix #652" > "$T/spec"
export T PATH="$T/bin:$PATH"
# The copies in $T (e.g. nolock.sh) read boilerplate.txt from the same bot home as start.sh.
export BOT_HOME=${BOT_HOME:-$(cd "$HERE/../.." && pwd)}
fail=0

race() { # $1 = script. Prints how many workers started.
  rm -rf "$T/locks" "$T/starts"
  START_LOCKS="$T/locks" bash "$1" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err" &
  START_LOCKS="$T/locks" bash "$1" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err" &
  wait
  wc -l < "$T/starts" 2>/dev/null | tr -d ' ' || echo 0
}
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }

check "two parallel starts: one worker" "$(race "$HERE/start.sh")" 1
grep -v '^  mkdir "\$L" 2>/dev/null' "$HERE/start.sh" > "$T/nolock.sh"
check "lock line cut out" "$(cmp -s "$HERE/start.sh" "$T/nolock.sh"; echo $?)" 1
check "with no lock: two workers (the test can fail)" "$(race "$T/nolock.sh")" 2

# Reviewer starts: "start.sh - <spec> pr-<n>" takes locks/pr-<n>-<spec name>. Two sweeps that both
# see "no-reviewer" on PR 701 start one adversarial reviewer, and one code-review reviewer beside it.
cp "$T/spec" "$T/adversarial.txt"; cp "$T/spec" "$T/codereview.txt"
prace() { # $1 = script, $2 = spec (default adversarial.txt), $3 = PR (default 701). Prints how many workers started.
  rm -rf "$T/locks" "$T/starts"
  START_LOCKS="$T/locks" bash "$1" - "$T/${2:-adversarial.txt}" pr-${3:-701} >/dev/null 2>>"$T/err" &
  START_LOCKS="$T/locks" bash "$1" - "$T/${2:-adversarial.txt}" pr-${3:-701} >/dev/null 2>>"$T/err" &
  wait
  wc -l < "$T/starts" 2>/dev/null | tr -d ' ' || echo 0
}
check "two parallel reviewer starts on one PR: one worker" "$(prace "$HERE/start.sh")" 1
START_LOCKS="$T/locks" bash "$HERE/start.sh" - "$T/codereview.txt" pr-701 >/dev/null 2>>"$T/err"
check "the other reviewer kind still starts" "$(wc -l < "$T/starts" | tr -d ' ')" 2
grep -v '^  mkdir "\$L" 2>/dev/null' "$HERE/start.sh" > "$T/nolock.sh"
check "with no reviewer lock: two workers (the test can fail)" "$(prace "$T/nolock.sh")" 2
# Sweep step 7.2 "conflict": two sweeps that both see "WAIT 774 conflict" start one conflict worker.
cp "$T/spec" "$T/conflict.txt"
check "two parallel conflict starts on one PR: one worker" "$(prace "$HERE/start.sh" conflict.txt 774)" 1
check "with no lock: two conflict workers (the test can fail)" "$(prace "$T/nolock.sh" conflict.txt 774)" 2
# The lock drops when a review newer than the lock is on the PR, or after 3 hours.
rm -rf "$T/starts"; mkdir -p "$T/locks/pr-701-adversarial"
echo "2999-01-01T00:00:00Z" > "$T/comments"
START_LOCKS="$T/locks" bash "$HERE/start.sh" - "$T/adversarial.txt" pr-701 >/dev/null 2>>"$T/err"
check "a review newer than the lock drops it" "$(wc -l < "$T/starts" 2>/dev/null | tr -d ' ')" 1
rm -rf "$T/starts"; mkdir -p "$T/locks/pr-701-adversarial"
echo "2000-01-01T00:00:00Z" > "$T/comments"
START_LOCKS="$T/locks" bash "$HERE/start.sh" - "$T/adversarial.txt" pr-701 >/dev/null 2>>"$T/err"
check "an older review keeps the lock" "$( [ -f "$T/starts" ] && echo started || echo none)" none
touch -t 202601010000 "$T/locks/pr-701-adversarial"
START_LOCKS="$T/locks" bash "$HERE/start.sh" - "$T/adversarial.txt" pr-701 >/dev/null 2>>"$T/err"
check "a 3-hour-old reviewer lock is dropped" "$(wc -l < "$T/starts" 2>/dev/null | tr -d ' ')" 1
rm -f "$T/comments"
# gh fails while a reviewer lock exists: no start (fail closed).
rm -rf "$T/starts"; mkdir -p "$T/locks/pr-701-adversarial"; touch -t 202601010000 "$T/locks/pr-701-adversarial"
mv "$T/bin/gh" "$T/gh.keep"; printf '#!/bin/bash\nexit 1\n' > "$T/bin/gh"; chmod +x "$T/bin/gh"
START_LOCKS="$T/locks" bash "$HERE/start.sh" - "$T/adversarial.txt" pr-701 >/dev/null 2>>"$T/err"
check "gh fails on a reviewer lock: no start" "$( [ -f "$T/starts" ] && echo started || echo none)" none
mv "$T/gh.keep" "$T/bin/gh"

# A lock is dropped once the lane says the ticket is done, and after 3 hours.
rm -rf "$T/starts"; mkdir -p "$T/locks/652"; touch -t 202601010000 "$T/locks/652"
START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
check "a 3-hour-old lock is dropped" "$(wc -l < "$T/starts" | tr -d ' ')" 1
rm -rf "$T/starts"; mkdir -p "$T/locks/652"
echo "2999-01-01T00:00:00Z Ticket #652 done: PR #700" > "$T/comments"
START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
check "a lock is dropped after the done comment" "$(wc -l < "$T/starts" | tr -d ' ')" 1
# A fresh "worked by" with no later "done" stops the start, and leaves no lock behind.
rm -rf "$T/starts" "$T/locks"
echo "$(date -u +%FT%TZ) Ticket #652 worked by razorbill, since now" > "$T/comments"
START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
check "a live worked-by comment stops the start" "$( [ -f "$T/starts" ] && echo started || echo none)" none
check "the refused start drops its lock" "$( [ -d "$T/locks/652" ] && echo kept || echo dropped)" dropped
# A working agent whose task names #652 stops the start.
rm -f "$T/comments"
cat > "$T/bin/orca" <<'ORCA'
#!/bin/bash
case "$1 $2" in
  "worktree ps") echo '{"result":{"worktrees":[{"path":"/w/x","agents":[{"state":"working","prompt":"Task: fix #652 now"}]}]}}' ;;
  "orchestration worker-start") echo x >> "$T/starts"; echo "dispatchId=d workspace=id::/w/y" ;;
esac
ORCA
START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
check "a working agent on #652 stops the start" "$( [ -f "$T/starts" ] && echo started || echo none)" none
# A "worked by" older than 3 hours with no "done": stale, unless an agent (working or done) still names #652.
old=$(date -u -v-4H +%FT%TZ)
echo "$old Ticket #652 worked by razorbill, since then" > "$T/comments"
ps_agent() { # $1 = agent state, or "" for an empty ps
  if [ -n "$1" ]; then a='{"path":"/w/x","agents":[{"state":"'$1'","prompt":"Task: fix #652 now"}]}'; else a=; fi
  printf '#!/bin/bash\ncase "$1 $2" in\n  "worktree ps") echo '"'"'{"result":{"worktrees":[%s]}}'"'"' ;;\n  "orchestration worker-start") echo x >> "$T/starts"; echo "dispatchId=d workspace=id::/w/y" ;;\nesac\n' "$a" > "$T/bin/orca"
}
for st in "" done; do
  rm -rf "$T/starts" "$T/locks"; ps_agent "$st"
  START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
  want=$([ -z "$st" ] && echo started || echo none)
  check "a 4-hour-old worked-by, agent state '${st:-none}'" "$( [ -f "$T/starts" ] && echo started || echo none)" "$want"
done
# python3 fails: the start stops (fail closed) and leaves no lock.
rm -rf "$T/starts" "$T/locks"; ps_agent ""
printf '#!/bin/bash\nexit 1\n' > "$T/bin/python3"; chmod +x "$T/bin/python3"
START_LOCKS="$T/locks" bash "$HERE/start.sh" 7 "$T/spec" 652 280 >/dev/null 2>>"$T/err"
check "python3 fails: no start" "$( [ -f "$T/starts" ] && echo started || echo none)" none
check "python3 fails: no lock left" "$( [ -d "$T/locks/652" ] && echo kept || echo dropped)" dropped
rm -f "$T/bin/python3"

# The brief sits unsent in the worker's input box. start.sh sends Enter again, at most 3 times.
# Fake orca: the screen lines come from $T/screen, the read source from $T/source. Each Enter
# is counted. After $T/clear_after Enters the input box is empty (the brief was sent), and the
# sent brief shows as "❯ fix #652" in the history above it.
cat > "$T/bin/orca" <<'ORCA'
#!/bin/bash
case "$1 $2" in
  "orchestration worker-start") echo "dispatchId=d workspace=id::/w/y terminal=term_t" ;;
  "terminal read") n=$(cat "$T/enters" 2>/dev/null | wc -l)
    if [ "$n" -ge "$(cat "$T/clear_after")" ]; then f="$T/sent"; else f="$T/screen"; fi
    python3 -c 'import sys, json; print(json.dumps({"result": {"terminal": {"source": sys.argv[2], "tail": open(sys.argv[1]).read().splitlines()}}}))' "$f" "$(cat "$T/source")" ;;
  "terminal send") echo x >> "$T/enters" ;;
esac
ORCA
chmod +x "$T/bin/orca"
printf '  welcome\n───\n❯ [Pasted text #1 +40 lines]\n───\n' > "$T/screen"
printf '❯ fix #652\n  working\n───\n❯\n───\n' > "$T/sent"
echo screen > "$T/source"
submit() { # $1 = Enters needed, $2 = script. Prints "<enters> <exit>".
  rm -f "$T/enters"; echo "$1" > "$T/clear_after"
  SUBMIT_WAIT_SECS=0 bash "${2:-$HERE/start.sh}" - "$T/spec" > "$T/out" 2>>"$T/err"; rc=$?
  echo "$(cat "$T/enters" 2>/dev/null | wc -l | tr -d ' ') $rc"
}
check "brief sent at once: no Enter" "$(submit 0)" "0 0"
check "brief sent after one more Enter" "$(submit 1)" "1 0"
check "brief never sent: 3 Enters, exit 3" "$(submit 99)" "3 3"
check "brief never sent: says so" "$(grep -c 'still unsent in term_t' "$T/out")" 1
# Only the last "❯" line is the input box, so the history line "❯ fix #652" is no unsent brief.
check "history line is not an unsent brief" "$(submit 0)" "0 0"
sed 's/p\[-1\]/p[0]/g' "$HERE/start.sh" > "$T/firstline.sh"
check "reading the first ❯ line: Enters sent (the test can fail)" "$(submit 0 "$T/firstline.sh")" "3 3"
# No rendered screen: send no Enter into a screen that cannot be read.
echo screen-unavailable > "$T/source"
check "no rendered screen: no Enter, exit 3" "$(submit 99)" "0 3"
check "no rendered screen: says so" "$(grep -c 'still unknown in term_t' "$T/out")" 1
# A permission menu also starts with "❯". Enter would pick option 1, so it reads as unknown.
echo screen > "$T/source"
printf 'Do you want to proceed?\n❯ 1. Yes\n  2. No\n' > "$T/screen"
check "menu is not an unsent brief: no Enter" "$(submit 99)" "0 3"
[ $fail = 0 ] || cat "$T/err"; exit $fail
