#!/usr/bin/env bash
# PreToolUse(Bash) hook: mechanically enforces the git-safety rules stated in
# ~/CLAUDE.md's "Git Workflow and Concurrent Work" and "Executing actions
# with care" sections, instead of relying on the model to remember them.
# Wired in ~/.claude/settings.json under hooks.PreToolUse (matcher: Bash).
#
# Known structural limit, not fixable from inside this script: it only ever
# runs when a git command reaches the local Bash tool. An agent given
# `isolation: "remote"` runs in a separate cloud environment where this file
# and its settings.json wiring don't exist, and any non-Bash tool with shell
# access wouldn't match the "Bash" hook matcher either. Neither is caught
# here; both need to be handled by choosing not to grant remote isolation (or
# other shell-capable tools) to sessions that share a working tree with
# something this hook is supposed to protect.
set -uo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
sid="$(printf '%s' "$input" | jq -r '.session_id // "nosession"')"
[ -z "$cmd" ] && exit 0

# The directory a command actually operates on isn't always $PWD: `git -C
# <dir> ...` and a leading `cd <dir> &&`/`cd <dir>;` both redirect it. Without
# this, checking $PWD's branch lets `git -C <other-repo-on-main> commit` slip
# straight past rule 2 -- the hook would be judging the wrong repo entirely.
# Last `-C`/`cd` wins, matching git's own "last flag wins" precedent; this is
# a heuristic over the raw string, not a real shell parse, so it can still
# miss more exotic constructions (it's the same class of gap noted in rule 5's
# comment below, not a claim of full coverage).
target_dir() {
  local text="$1" dir="$PWD" hit
  hit="$(printf '%s' "$text" | grep -oE '(^|[;&]) *cd +[^ ;&]+' | tail -1 | sed -E 's/^[;&]* *cd +//')"
  [ -n "$hit" ] && dir="$hit"
  hit="$(printf '%s' "$text" | grep -oE -- '-C +[^ ;&]+' | tail -1 | sed -E 's/^-C +//')"
  [ -n "$hit" ] && dir="$hit"
  ( cd "$PWD" 2>/dev/null && cd "$dir" 2>/dev/null && pwd ) 2>/dev/null || printf '%s' "$PWD"
}

# A git alias can hide any command inside a name the rules below never
# checked for (`git config alias.cm "commit --no-verify"` then `git cm`).
# Expand known aliases into the string the rules actually match against, so
# `git cm` is judged as what it really runs, not as a name.
expand_aliases() {
  local text="$1" name value key
  local expanded="$text"
  while read -r name value; do
    [ -z "$name" ] && continue
    key="${name#alias.}"
    if printf '%s' "$expanded" | grep -Eq "(^|[^A-Za-z0-9_-])git +$key(\$|[^A-Za-z0-9_-])"; then
      # Prefixed with "git " so the existing "git +(commit|push)...--no-verify"
      # style regexes match inside this appended expansion the same way they
      # would against the flag written out literally.
      expanded="$expanded ## alias:$key expands to: git $value"
    fi
  done < <(git -C "$resolved_dir" config --get-regexp '^alias\.' 2>/dev/null)
  printf '%s' "$expanded"
}

resolved_dir="$(target_dir "$cmd")"
branch="$(git -C "$resolved_dir" branch --show-current 2>/dev/null || true)"
check_cmd="$(expand_aliases "$cmd")"
# `git -C <dir> commit` and `git -c k=v commit` put a global flag between
# "git" and the subcommand, so a plain `git +commit\b` regex never matches
# against check_cmd as-is. norm_cmd strips those known flag forms so the
# subcommand-adjacency checks in rules 1 and 2 still fire; check_cmd itself
# is kept unstripped since rule 1's core.hooksPath check needs to see the
# `-c core.hooksPath=...` flag it's specifically looking for.
norm_cmd="$(printf '%s' "$check_cmd" | sed -E 's/git +(-C +[^ ]+ +|-c +[^ ]+ +)+/git /g')"
marker="${TMPDIR:-/tmp}/claude-git-status-seen-${sid}"

deny() {
  jq -n --arg reason "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
  exit 0
}

note() {
  jq -n --arg msg "$1" '{systemMessage:$msg}'
  exit 0
}

# Remember that a status check happened this session, for rule 4 below.
if printf '%s' "$cmd" | grep -Eq '(^|[;&|]) *git +status\b'; then
  touch "$marker" 2>/dev/null || true
fi

# 1. Never skip hooks/signing on commit or push (CLAUDE.md: "never skip
#    hooks... or bypass signing... unless the user has explicitly requested").
#    Checked against check_cmd (alias-expanded) so `git cm` aliased to
#    `commit --no-verify` can't hide the flag behind a name.
if printf '%s' "$norm_cmd" | grep -Eq 'git +(commit|push)[^;&|]*--no-verify\b'; then
  deny "CLAUDE.md: never skip hooks (--no-verify) unless explicitly requested by the user. Ask first if you believe this case warrants it."
fi
if printf '%s' "$norm_cmd" | grep -Eq 'git +commit[^;&|]*--no-gpg-sign\b'; then
  deny "CLAUDE.md: never bypass commit signing (--no-gpg-sign) unless explicitly requested by the user."
fi
# core.hooksPath is the config-level equivalent of --no-verify: it disables
# git's local hooks just as effectively, without ever writing that flag.
# Checked against check_cmd (pre-flag-stripping) since norm_cmd would have
# already erased the very -c core.hooksPath=... flag this looks for.
if printf '%s' "$check_cmd" | grep -Eq 'core\.hooksPath' && printf '%s' "$norm_cmd" | grep -Eq 'git +(commit|push)\b'; then
  deny "CLAUDE.md: setting core.hooksPath disables local git hooks the same way --no-verify does. Same rule applies: don't, unless the user explicitly asked for it."
fi

# 2. No direct commits to main/master (CLAUDE.md: trunk-based development —
#    short-lived branches, not commits straight to trunk). branch is resolved
#    from the command's actual target dir (see target_dir above), not
#    blindly from the hook's own $PWD.
if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  if printf '%s' "$norm_cmd" | grep -Eq 'git +commit\b'; then
    deny "CLAUDE.md: trunk-based workflow — branch off ($branch) before committing instead of committing directly to it. Create a short-lived feature/fix branch first."
  fi
fi

# 3. Force-push to main/master needs explicit user confirmation, not a
#    silently-approved hook (CLAUDE.md: hard-to-reverse + affects shared
#    state → confirm first). The target is whatever branch the push command
#    actually names, not just the locally checked-out branch -- pushing some
#    other feature branch while sitting on main must not trip this.
if printf '%s' "$cmd" | grep -Eq 'git +push\b'; then
  push_line="$(printf '%s' "$cmd" | grep -oE 'git +push[^;&|]*')"
  read -r -a words <<< "$push_line"
  # A refspec's own leading "+" means force, same as --force/-f -- git's own
  # convention for "push, no matter what's there." Missing this let
  # `git push origin +main` force-push with no --force flag anywhere.
  has_plus_refspec=0
  for w in "${words[@]:2}"; do
    case "$w" in +*) has_plus_refspec=1 ;; esac
  done
  is_force=0
  if printf '%s' "$cmd" | grep -Eq -- '--force-with-lease\b|--force\b|(^| )-f( |$)'; then is_force=1; fi
  if [ "$is_force" -eq 1 ] || [ "$has_plus_refspec" -eq 1 ]; then
    target=""
    remote_seen=0
    for w in "${words[@]:2}"; do
      case "$w" in
        -*) continue ;;
      esac
      if [ "$remote_seen" -eq 0 ]; then remote_seen=1; continue; fi
      target="${w#+}"
      target="${target##*:}"
      # `main:refs/heads/main` and `main:main` both mean the same destination
      # as plain `main` -- strip the refs/heads/ prefix so a fully-qualified
      # ref path still compares equal instead of silently missing the check.
      target="${target#refs/heads/}"
      break
    done
    [ -z "$target" ] && target="$branch"
    if [ "$target" = "main" ] || [ "$target" = "master" ]; then
      deny "CLAUDE.md: force-pushing $target is hard to reverse and affects shared state. Confirm explicitly with the user before running this, don't just execute it."
    fi
  fi
fi

# 4. Destructive, working-tree-discarding commands should follow a git
#    status check in the same session (CLAUDE.md: "run git status before any
#    command that could discard uncommitted work").
if printf '%s' "$cmd" | grep -Eq 'git +reset +--hard\b|git +clean +-[a-zA-Z]*f|git +checkout +--( |$)|git +checkout +\.( |$)|git +restore\b'; then
  if [ ! -f "$marker" ]; then
    note "CLAUDE.md reminder: run 'git status' before a destructive command like this one ($cmd), and stash/commit anything uncommitted first."
  fi
fi

# Shared by rules 5 and 5b: prints the pid of a mutation harness actually
# running in <dir>'s working tree, or nothing. Both rules need the identical
# question answered, so it lives in one place rather than being copy-pasted
# and drifting.
#
# Two filters, both load-bearing:
#  - cwd must equal THIS working tree. A harness in a sibling worktree cannot
#    touch our files, and a guard that cries wolf gets ignored.
#  - the process must really be a python interpreter running the script.
#    `pgrep -f` matches full command lines, so it also matches shells that
#    merely NAME the harness. On 2026-08-03 there were live poll loops with
#    `until ! pgrep -f "tools/mutation_check.py"; do sleep 10; done` as their
#    command line, and no harness running at all. Keying off pgrep alone would
#    have blocked every commit, in every repo, until the stray shell was hunted
#    down: a worse bug than the one this guards against. `ps -o comm=` reports
#    the executable (a Python binary vs `bash`), which separates the two.
#
# Fails OPEN by design. No pgrep, no lsof, not a git repo, anything unexpected:
# print nothing and let the command run. A hook that denied on its own internal
# error would brick every commit the user makes.
harness_pid_in_tree() {
  local dir="$1" here p comm hcwd
  command -v pgrep >/dev/null 2>&1 || return 0
  command -v lsof  >/dev/null 2>&1 || return 0
  here="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)"
  [ -n "$here" ] || return 0
  for p in $(pgrep -f 'mutation_check\.py' 2>/dev/null); do
    comm="$(ps -o comm= -p "$p" 2>/dev/null)"
    printf '%s' "$comm" | grep -Eqi 'python' || continue
    hcwd="$(lsof -a -d cwd -p "$p" -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
    if [ -n "$hcwd" ] && [ "$hcwd" = "$here" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  return 0
}

# 5. Never move the working tree while another session is active there.
#    (CLAUDE.md: "Concurrent and multi-agent work" -- never share one working
#    directory.) File ownership does not prevent this: checkout/pull/stash
#    move the WHOLE tree regardless of who owns which file. Added 2026-08-02
#    after two agents and the maintainer interleaved work in one checkout.
if printf '%s' "$cmd" | grep -Eq 'git +(checkout|switch)\b|git +pull\b|git +stash\b'; then
  # A running mutation harness has tracked files transiently mutated, so a
  # checkout can abort mid-run.
  hp="$(harness_pid_in_tree "$resolved_dir")"
  if [ -n "$hp" ]; then
    deny "A mutation harness (mutation_check.py, pid $hp) is RUNNING in THIS working tree ($resolved_dir). It mutates tracked files transiently, so switching or moving the tree now can abort the run and leave a reverted snippet behind. Wait for it, or work in a separate 'git worktree add'."
  fi
  # Uncommitted work you did not create means someone else is in this tree.
  dirty="$(git status --porcelain 2>/dev/null | head -1)"
  if [ -n "$dirty" ] && [ ! -f "$marker" ]; then
    note "CLAUDE.md: this working tree has uncommitted changes. If they are not yours, another session is active here -- do not move the tree. Use 'git worktree add <path> -b <branch>' instead. Run 'git status' to confirm before proceeding."
  fi
fi

# 5b. Never stage or commit while a mutation harness is running in this tree.
#     Added 2026-08-03. Rule 5's deny message already told the user that
#     "committing now can capture a reverted snippet as if it were real code",
#     but rule 5's regex only ever matched checkout/switch/pull/stash. The
#     commit half of the stated danger was documented and never enforced.
#     Nearly hit for real: a subagent had `bad = []` (a live injected mutation
#     inside _as_numbers) sitting in its tracked files while preparing to
#     commit. One `git add -A` would have shipped a silently broken function
#     inside a PR labelled as a dtype fix.
#     Matched against norm_cmd so `git -C <dir> add` is judged too, and the
#     tree checked is the command's real target dir, not blindly $PWD.
if printf '%s' "$norm_cmd" | grep -Eq 'git +(add|commit)\b'; then
  hp="$(harness_pid_in_tree "$resolved_dir")"
  if [ -n "$hp" ]; then
    deny "A mutation harness (mutation_check.py, pid $hp) is RUNNING in THIS working tree ($resolved_dir). It reverts and restores tracked files in place, so 'git add -A' right now can stage a transiently mutated snippet and commit it as if it were real code. Wait for the run to finish, or work in a separate 'git worktree add'."
  fi
fi

# 6. Never run the mutation harness in a shared checkout. It rewrites tracked
#    files in place; an interrupted run leaves a reverted snippet behind, and
#    that snippet has already been committed once as if it were real work.
#    Matched on EXECUTION, not mention. `pgrep -f 'mutation_check.py'` and
#    `until ! pgrep ...; do sleep 10; done` name the script without running
#    it, and those are exactly how you wait for or supervise a run. A rule
#    that blocked them would make the harness unsupervisable: rule 6b did
#    precisely that to its own author's poll loop minutes after it shipped.
#    This is the same mention-vs-execution distinction harness_pid_in_tree
#    already draws between a python process and a shell that merely names the
#    script, one layer up at the command text.
#    Two forms count as running it: an interpreter invoked on the script, and
#    the script invoked directly at a command boundary (start, or after ; & |).
#    Wrappers are spelled out rather than allowing any prefix: `[^;&|]*` here
#    would drift straight back to matching mentions (an `echo` about the
#    harness would deny), which is the bug this regex exists to avoid.
_wrap='((nohup|exec|env|time|sudo|caffeinate)( +-[^ ]+)* +)*'
_runs_harness="(^|[;&|] *)${_wrap}([A-Za-z0-9_/.-]*python[0-9.]* +([^;&|]* )?)?(\./|[A-Za-z0-9_./-]*/)?mutation_check\.py"
if printf '%s' "$cmd" | grep -Eq "$_runs_harness"; then
  # 6b. Never start a SECOND harness in a tree that already has one running.
  #     Added 2026-08-03, the day it happened: two harnesses ran concurrently
  #     in one worktree for ~20 minutes. Rule 6 below only ever *noted* that
  #     the primary checkout is a poor place to run it, and rule 5b blocks
  #     add/commit during a run, so the one thing nobody blocked was starting
  #     the run itself.
  #     Two harnesses in one tree interleave on the same files: one restores a
  #     snippet while the other still has it mutated. That corrupts the result
  #     in BOTH directions (CAUGHT because the sibling's mutation broke the
  #     suite, MISSED because a restore landed mid-run), so the run is not
  #     merely slower, it is untrustworthy, and the tree can be left holding a
  #     live mutation. Denying is right even though the command is read-only
  #     looking: the damage is to the answer, not just the files.
  hp="$(harness_pid_in_tree "$resolved_dir")"
  if [ -n "$hp" ]; then
    deny "A mutation harness (mutation_check.py, pid $hp) is ALREADY RUNNING in this working tree ($resolved_dir). Two of them interleave on the same tracked files, so both runs report meaningless results and the tree can be left holding a live mutation. Wait for pid $hp to finish, or run yours in a separate 'git worktree add'."
  fi

  wt_count="$(git worktree list 2>/dev/null | wc -l | tr -d ' ')"
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
  common="$(git rev-parse --git-common-dir 2>/dev/null)"
  # In the PRIMARY checkout (not a linked worktree) while worktrees exist.
  if [ "$wt_count" -gt 1 ] && [ "$common" = "$toplevel/.git" ]; then
    note "CLAUDE.md: mutation_check.py mutates tracked files in place, and $((wt_count-1)) other worktree(s) share this repo. Prefer running it inside your own worktree so an interrupted run cannot leave a reverted snippet in a tree someone else commits from."
  fi
fi

exit 0
