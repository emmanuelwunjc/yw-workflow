#!/usr/bin/env bash
# Self-test for git-safety-guard.sh. Run after editing it:
#   bash git-safety-guard-selftest.sh
#
# Feeds crafted PreToolUse JSON payloads to the hook from specific working
# directories (mirroring how Claude Code actually invokes it) and asserts
# whether the result was a deny.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${HOOK:-$(cd "$DIR" && pwd)/git-safety-guard.sh}"
SCRATCH="${TMPDIR:-/tmp}/git-safety-guard-selftest-fixtures"

pass=0; fail=0
ok() { if eval "$1"; then echo "  PASS: $2"; pass=$((pass+1)); else echo "  FAIL: $2"; fail=$((fail+1)); fi; }

# Runs the hook with $1=command, $2=cwd. Prints the hook's raw JSON stdout.
run_hook() {
  local cmd="$1" cwd="$2"
  ( cd "$cwd" && jq -n --arg cmd "$cmd" '{tool_input:{command:$cmd}, session_id:"selftest"}' | "$HOOK" )
}

denied() { printf '%s' "$1" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; }

MAIN_REPO="$SCRATCH/repo"        # on branch "main"
FEATURE_REPO="$SCRATCH/feature-repo"  # on branch "work"

# Fixtures are rebuilt every run so the fixture state can't itself drift and
# produce a false pass/fail; this is deliberately cheap (two tiny repos).
rm -rf "$SCRATCH"
git init -q -b scratch "$MAIN_REPO"
git -C "$MAIN_REPO" config user.email t@t.com
git -C "$MAIN_REPO" config user.name t
git -C "$MAIN_REPO" commit -q --allow-empty -m init
git -C "$MAIN_REPO" branch -m scratch main
git -C "$MAIN_REPO" config alias.cm "commit --no-verify"

git init -q -b work "$FEATURE_REPO"
git -C "$FEATURE_REPO" config user.email t@t.com
git -C "$FEATURE_REPO" config user.name t
git -C "$FEATURE_REPO" commit -q --allow-empty -m init

echo "=== Regression: existing rules still fire ==="
out="$(run_hook 'git commit --no-verify -m x' "$FEATURE_REPO")"
ok 'denied "$out"' "rule 1: --no-verify still denied"

out="$(run_hook 'git commit -m x' "$MAIN_REPO")"
ok 'denied "$out"' "rule 2: direct commit to main (matching cwd) still denied"

out="$(run_hook 'git push --force origin HEAD:main' "$MAIN_REPO")"
ok 'denied "$out"' "rule 3: force-push HEAD:main still denied"

out="$(run_hook 'git commit -m x' "$FEATURE_REPO")"
ok '! denied "$out"' "commit on a feature branch is NOT denied"

echo "=== Bypass 2: git -C <other repo on main> commit ==="
out="$(run_hook "git -C $MAIN_REPO commit --allow-empty -m x" "$FEATURE_REPO")"
ok 'denied "$out"' "git -C targeting a repo on main is denied"

echo "=== Bypass 3: force-push via +refspec, no --force flag ==="
out="$(run_hook 'git push origin +main' "$MAIN_REPO")"
ok 'denied "$out"' "+refspec force-push to main is denied"

echo "=== Bypass 4: force-push with a fully-qualified ref path ==="
out="$(run_hook 'git push --force origin main:refs/heads/main' "$MAIN_REPO")"
ok 'denied "$out"' "force-push to refs/heads/main is denied"

echo "=== Bypass 5: core.hooksPath used to disable hooks instead of --no-verify ==="
out="$(run_hook 'git -c core.hooksPath=/dev/null commit -m x' "$FEATURE_REPO")"
ok 'denied "$out"' "core.hooksPath override on commit is denied"

echo "=== Bypass 6: alias that expands to --no-verify ==="
out="$(run_hook 'git cm -m x' "$MAIN_REPO")"
ok 'denied "$out"' "alias expanding to --no-verify is denied"

echo "=== False-positive guards: normal usage must not be denied ==="
out="$(run_hook "git -C $FEATURE_REPO log --oneline -5" "$MAIN_REPO")"
ok '! denied "$out"' "git -C <feature repo> log from main is NOT denied"

out="$(run_hook "git -C $FEATURE_REPO commit --allow-empty -m x" "$MAIN_REPO")"
ok '! denied "$out"' "git -C <feature repo> commit (not main) is NOT denied"

out="$(run_hook 'git push origin feature-branch' "$MAIN_REPO")"
ok '! denied "$out"' "plain push to a non-main branch is NOT denied"

out="$(run_hook 'git push --force origin feature-branch' "$MAIN_REPO")"
ok '! denied "$out"' "force-push to a non-main branch is NOT denied"

out="$(run_hook 'git status' "$MAIN_REPO")"
ok '! denied "$out"' "git status is never denied"

# --- Rule 5b fixtures: a real harness, and a shell that only mentions one ----
# Added 2026-08-03. Rule 5's deny message claimed committing during a harness
# run was blocked, but its regex only covered checkout/switch/pull/stash. A
# subagent came within one `git add -A` of committing a live injected mutation
# (`bad = []` inside _as_numbers) as if it were a real dtype fix.
#
# Two fixtures, because the false-positive half matters as much as the deny:
#   HARNESS_REPO  a real python process executing mutation_check.py, cwd = repo
#   MENTION_REPO  a bash process that only MENTIONS mutation_check.py in its
#                 command line (the observed `until ! pgrep -f
#                 "tools/mutation_check.py"; do sleep 10; done` poll loops).
# `pgrep -f` matches both. Blocking on the second would wedge every commit the
# user makes, in every repo, until they hunted the stray shell down.
HARNESS_REPO="$SCRATCH/harness-repo"
MENTION_REPO="$SCRATCH/mention-repo"

HARNESS_PID=""; MENTION_PID=""
cleanup() {
  local rc=$?
  trap - EXIT
  [ -n "$HARNESS_PID" ] && kill "$HARNESS_PID" 2>/dev/null
  [ -n "$MENTION_PID" ] && kill "$MENTION_PID" 2>/dev/null
  wait 2>/dev/null
  exit "$rc"
}
trap cleanup EXIT INT TERM

if ! command -v python3 >/dev/null 2>&1; then
  echo "  FAIL: python3 not available, cannot build the harness fixture"
  fail=$((fail+1))
else
  for r in "$HARNESS_REPO" "$MENTION_REPO"; do
    git init -q -b work "$r"
    git -C "$r" config user.email t@t.com
    git -C "$r" config user.name t
    git -C "$r" commit -q --allow-empty -m init
  done

  # A stand-in harness: same filename, so pgrep -f sees what it really sees.
  printf 'import time\ntime.sleep(120)\n' > "$HARNESS_REPO/mutation_check.py"
  ( cd "$HARNESS_REPO" && exec python3 mutation_check.py ) >/dev/null 2>&1 &
  HARNESS_PID=$!
  ( cd "$MENTION_REPO" && exec bash -c 'while true; do sleep 5; done # until ! pgrep -f "tools/mutation_check.py"; do sleep 10; done' ) >/dev/null 2>&1 &
  MENTION_PID=$!

  # Don't assert until both fixtures are actually visible to pgrep, or the
  # tests measure a race instead of the hook.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    n="$(pgrep -f 'mutation_check\.py' 2>/dev/null | wc -l | tr -d ' ')"
    [ "$n" -ge 2 ] && break
    sleep 0.5
  done
  ok '[ "$n" -ge 2 ]' "fixtures: both the harness and the mention-only shell are running"

  echo "=== Rule 5b: staging/committing during a harness run in THIS tree ==="
  out="$(run_hook 'git add -A' "$HARNESS_REPO")"
  ok 'denied "$out"' "git add -A during a harness run in this tree is denied"

  out="$(run_hook 'git add src/foo.py' "$HARNESS_REPO")"
  ok 'denied "$out"' "git add <path> during a harness run in this tree is denied"

  out="$(run_hook 'git commit -m x' "$HARNESS_REPO")"
  ok 'denied "$out"' "git commit during a harness run in this tree is denied"

  out="$(run_hook 'git checkout -b other' "$HARNESS_REPO")"
  ok 'denied "$out"' "rule 5 (tree-moving) still denied during a harness run"

  echo "=== Rule 5b false positives: the guard must not cry wolf ==="
  out="$(run_hook 'git commit -m x' "$FEATURE_REPO")"
  ok '! denied "$out"' "commit with no harness in this tree is NOT denied"

  out="$(run_hook 'git add -A' "$FEATURE_REPO")"
  ok '! denied "$out"' "git add -A while a harness runs in a DIFFERENT tree is NOT denied"

  out="$(run_hook 'git commit -m x' "$MENTION_REPO")"
  ok '! denied "$out"' "commit is NOT denied by a shell that merely mentions mutation_check.py"

  out="$(run_hook 'git add -A' "$MENTION_REPO")"
  ok '! denied "$out"' "git add -A is NOT denied by a mention-only shell"

  out="$(run_hook 'git checkout -b other' "$MENTION_REPO")"
  ok '! denied "$out"' "checkout is NOT denied by a mention-only shell"

  # === Rule 6b ==============================================================
  # Added 2026-08-03, after the real thing happened. Rule 6 only ever *noted*
  # that the primary checkout is a bad place to run the harness. Nothing
  # stopped a SECOND harness starting in a tree that already had one. Two runs
  # in one tree interleave on the same files: one restores while the other has
  # a snippet mutated, so results are meaningless in both directions (CAUGHT
  # because the sibling's mutation broke the suite, MISSED because a restore
  # landed mid-run) and the tree can be left holding a live mutation.
  # Broken pgrep/lsof stubs stand in for "detection is broken", while jq and
  # git still work so the hook can still deny if it wants to. A hook that
  # denied on its own internal error would brick every commit the user makes,
  # everywhere. Allowing through is the only safe failure mode. Built here
  # rather than beside the fail-open section because rule 6b's own fail-open
  # case below needs them too, and referencing them before they exist made
  # that case silently run against the REAL pgrep, which is a test that proves
  # nothing while looking like it passed.
  mkdir -p "$SCRATCH/brokenbin"
  for stub in pgrep lsof; do
    printf '#!/bin/sh\necho "%s: simulated failure" >&2\nexit 3\n' "$stub" > "$SCRATCH/brokenbin/$stub"
    chmod +x "$SCRATCH/brokenbin/$stub"
  done

  echo "=== Rule 6b: a second harness in a tree that already has one ==="
  out="$(run_hook 'python3 tools/mutation_check.py' "$HARNESS_REPO")"
  ok 'denied "$out"' "starting a harness where one already runs is denied"

  # The other half, and the more dangerous one to get wrong. Rule 6b fires on
  # the very command it guards, so a false positive here does not annoy the
  # user, it makes the harness unrunnable everywhere. These reuse
  # harness_pid_in_tree, so they hold for the same reasons rule 5b's do.
  out="$(run_hook 'python3 tools/mutation_check.py' "$FEATURE_REPO")"
  ok '! denied "$out"' "the FIRST harness in a quiet tree is NOT denied"

  out="$(run_hook 'python3 tools/mutation_check.py' "$MENTION_REPO")"
  ok '! denied "$out"' "a harness is NOT denied by a shell that merely mentions one"

  out="$( PATH="$SCRATCH/brokenbin:$PATH" run_hook 'python3 tools/mutation_check.py' "$HARNESS_REPO" )"
  ok '! denied "$out"' "a harness is NOT denied when harness detection cannot run"

  # The shape the real incident actually took. Agents run the harness as
  # `cd <worktree> && python3 tools/mutation_check.py` from wherever they
  # happen to be, so judging $PWD instead of the command's real target would
  # miss every case that matters. target_dir() already resolves the `cd`;
  # this pins that, because the rule is worthless without it.
  out="$(run_hook "cd $HARNESS_REPO && python3 tools/mutation_check.py" "$FEATURE_REPO")"
  ok 'denied "$out"' "a harness started via 'cd <tree> &&' is judged against THAT tree"

  out="$(run_hook "cd $FEATURE_REPO && python3 tools/mutation_check.py" "$HARNESS_REPO")"
  ok '! denied "$out"' "'cd <quiet tree> &&' is NOT denied from inside a busy one"

  # Mentioning the harness is not running it. This is the same distinction
  # harness_pid_in_tree draws between a python process and a shell that merely
  # names the script, one layer up: the command TEXT. Caught by rule 6b
  # blocking its own author's wait-for-the-harness poll loop minutes after it
  # shipped. Waiting for a run, or reading its log, must stay allowed, or the
  # rule makes the harness impossible to supervise.
  out="$(run_hook 'until ! pgrep -f "tools/mutation_check.py"; do sleep 10; done' "$HARNESS_REPO")"
  ok '! denied "$out"' "a poll loop waiting on the harness is NOT denied"

  out="$(run_hook 'pgrep -f tools/mutation_check.py | wc -l' "$HARNESS_REPO")"
  ok '! denied "$out"' "pgrep-ing for the harness is NOT denied"

  # ...while every shape that really starts one still is.
  out="$(run_hook 'nohup python3 tools/mutation_check.py > out.log 2>&1 &' "$HARNESS_REPO")"
  ok 'denied "$out"' "a backgrounded harness start is still denied"

  out="$(run_hook './tools/mutation_check.py' "$HARNESS_REPO")"
  ok 'denied "$out"' "running the harness as an executable is still denied"

  echo "=== Fail open: detection errors must never block a command ==="
  out="$( PATH="$SCRATCH/brokenbin:$PATH" run_hook 'git commit -m x' "$HARNESS_REPO" )"
  ok '! denied "$out"' "commit is NOT denied when harness detection cannot run"

  out="$( PATH="$SCRATCH/brokenbin:$PATH" run_hook 'git checkout -b other' "$HARNESS_REPO" )"
  ok '! denied "$out"' "checkout is NOT denied when harness detection cannot run"

  out="$(run_hook 'git add -A' "$SCRATCH")"
  ok '! denied "$out"' "git add outside any git repo is NOT denied"
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
