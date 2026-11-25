#!/bin/bash
# Test start-grill.sh against a fake gh and orca. No network. Usage: bash test-start-grill.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
echo "$*" >> "$T/gh.log"
echo "The bot replies by mail as Twenty Bot"
GH
cat > "$T/bin/orca" <<'ORCA'
#!/bin/bash
case "$1 $2" in
  "worktree ps") # like orca: 200 rows and truncated, unless --limit is large
    case " $* " in *" --limit 100000 "*) cat "$T/ps" ;;
      *) jq '.result.worktrees |= .[:200] | .result.truncated = (.result.worktrees | length > 200)' "$T/ps" ;; esac ;;
  "worktree create") printf '%s\n' "$@" > "$T/args"
    echo '{"ok":true,"result":{"worktree":{"id":"r::/w/grill-416-the-bot-replies-by-mail"}}}' ;;
esac
ORCA
chmod +x "$T/bin/"*
export T PATH="$T/bin:$PATH" BOT_HOME=$T/home
# Two fake projects: alpha (alone in its own file, the default) and beta (in a two-project file).
echo '{"projects": {"alpha": {"repo": "o/alpha", "orca_repo_id": "rid-alpha"}, "beta": {"repo": "o/beta", "orca_repo_id": "rid-beta"}}}' > "$T/projects.json"
jq '{projects: {alpha: .projects.alpha}}' "$T/projects.json" > "$T/alpha.json"
export PROJECTS_JSON=$T/alpha.json
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: want $3, got $2"; fail=1; fi; }
S="$HERE/start-grill.sh"

echo '{"result":{"truncated":false,"worktrees":[{"path":"/w/grill-4160-x"},{"path":"/w/other"}]}}' > "$T/ps"
check "prints the workspace path" "$(bash "$S" 416 "who gets a reply")" /w/grill-416-the-bot-replies-by-mail
check "name comes from the title" "$(sed -n '4p' "$T/args")" grill-416-the-bot-replies-by-mail
grep -q -- '--surface' "$T/args" && grep -q -- '--no-parent' "$T/args" && grep -q -- '--activate' "$T/args"; check "chat, no parent, activate" $? 0
grep -q 'Topics: who gets a reply.' "$T/args"; check "extra topic text is in the prompt" $? 0
grep -q 'ONE English comment on #416' "$T/args"; check "prompt asks for one comment on the ticket" $? 0
check "alpha: the Orca repo of alpha" "$(grep -A1 -x -- --repo "$T/args" | tail -1)" id:rid-alpha
grep -q -- '-R o/alpha' "$T/gh.log"; check "alpha: reads alpha's repo" $? 0
rm -f "$T/args" "$T/gh.log"
PROJECTS_JSON=$T/projects.json bash "$S" 416 >/dev/null 2>&1; check "two projects and no --project: exit 2" $? 2
check "  and no create" "$([ -f "$T/args" ] && echo ran || echo none)" none
PROJECTS_JSON=$T/projects.json bash "$S" --project beta 416 >/dev/null
check "--project beta: the Orca repo of beta" "$(grep -A1 -x -- --repo "$T/args" | tail -1)" id:rid-beta
grep -q 'Repo: o/beta.' "$T/args" && ! grep -q 'o/alpha' "$T/gh.log" "$T/args"; check "--project beta: only beta in the prompt and gh calls" $? 0

rm -f "$T/args"
out=$(bash "$S" --dry-run 416)
check "dry run creates nothing" "$([ -f "$T/args" ] && echo ran || echo none)" none
case "$out" in "orca worktree create --name grill-416-"*) r=0 ;; *) r=1 ;; esac; check "dry run prints the command" $r 0

echo '{"result":{"truncated":false,"worktrees":[{"path":"/w/grill-416-mail-reply"}]}}' > "$T/ps"
bash "$S" 416 >/dev/null 2>&1; check "an existing grill for the ticket: exit 1" $? 1
check "  and no create" "$([ -f "$T/args" ] && echo ran || echo none)" none
bash "$S" 41x >/dev/null 2>&1; check "a ticket that is not a number: exit 1" $? 1

echo '{"result":{"truncated":false,"worktrees":[{"path":"/w/grill-1-a"},{"path":"/w/grill-2-b"},{"path":"/w/other"}]}}' > "$T/ps"
check "2 grill workspaces open: a third one opens" "$(bash "$S" 416)" /w/grill-416-the-bot-replies-by-mail

# 1544 rows, the grill for #416 is row 1200: past the default page of 200.
rm -f "$T/args"
jq -n '{result: {truncated: false, worktrees: [range(1544) | {path: (if . == 1199 then "/w/grill-416-mail-reply" else "/w/ws-\(.)" end)}]}}' > "$T/ps"
bash "$S" 416 >/dev/null 2>&1; check "grill at row 1200 of 1544: exit 1" $? 1
check "  and no create" "$([ -f "$T/args" ] && echo ran || echo none)" none
jq '.result.truncated = true' "$T/ps" > "$T/ps2" && mv "$T/ps2" "$T/ps"
out=$(bash "$S" 417 2>&1); r=$?; check "truncated ps output: exit 1" $r 1
case "$out" in *truncated*) r=0 ;; *) r=1 ;; esac; check "  and it says truncated" $r 0
check "  and no create" "$([ -f "$T/args" ] && echo ran || echo none)" none
exit $fail
