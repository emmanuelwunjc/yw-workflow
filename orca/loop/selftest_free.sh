#!/bin/bash
# Fake-data test of free_tickets.py and precheck.sh. A fake `gh` goes first on PATH: no network.
# One case per rule of the free work check (ticket #689). Each case fails when its rule is removed:
# see selftest_mutations.sh.
D=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
# iss <number> <labels, comma list> [subIssues] [blockedBy states, comma list] [linked branch] [closing PRs]
iss() {
  jq -nc --arg n "$1" --arg l "$2" --arg s "${3:-0}" --arg b "${4:-}" --arg br "${5:-}" --arg c "${6:-0}" '{
    number: ($n|tonumber), labels: {nodes: [$l | split(",")[] | select(. != "") | {name: .}]},
    subIssues: {totalCount: ($s|tonumber)}, blockedBy: {nodes: [$b | split(",")[] | select(. != "") | {state: .}]},
    linkedBranches: {nodes: [$br | select(. != "") | {ref: {name: .}}]},
    closedByPullRequestsReferences: {totalCount: ($c|tonumber)}}'
}
page() { jq -sc '{data: {repository: {issues: {nodes: .}}}}'; }
# Page 1:
#  #3 another slice: free, after every mvp ticket. #5, #10 mvp: free. #11 an open blocker. #12 a closed blocker: free. #13 to #18 one SKIP label each.
#  #19 a layer (sub-issues): not free and no NO SLICE line. #20 taken by a branch with no PR (1 worker,
#  its diff is BUSY). #21 taken by the head branch of an open PR (no worker). #22 an open PR closes it.
#  #23 no slice label: NO SLICE. #40 a nit: waits while another ticket is free.
{ iss 3 slice:twenty-data; iss 5 slice:mvp-chat; iss 10 slice:mvp-rules; iss 11 slice:mvp-rules 0 OPEN; iss 12 slice:mvp-rules 0 CLOSED
  iss 13 slice:mvp-rules,needs-owner; iss 14 slice:mvp-rules,wayfinder:grilling; iss 15 slice:mvp-rules,wayfinder:map
  iss 16 slice:mvp-rules,deferred; iss 17 slice:later-slices; iss 18 slice:mvp-rules,tracker; iss 19 slice:mvp-rules 3
  iss 20 slice:mvp-rules 0 "" ticket-20; iss 21 slice:mvp-rules 0 "" feat/x; iss 22 slice:mvp-rules 0 "" "" 1
  iss 23 bug; iss 40 slice:nits; } | page > "$T/p1.json"
# Page 2: #30 another slice, read only when the second page is read.
iss 30 slice:reads-more | page > "$T/p2.json"
jq -s . "$T/p1.json" "$T/p2.json" > "$T/gql.json"
echo '["scripts/b.py"]' > "$T/compare-ticket-20.json"
echo '[{"number":60,"headRefName":"feat/x","files":[{"path":"scripts/a.py"}],"isDraft":false},
       {"number":61,"headRefName":"draft/y","files":[],"isDraft":true}]' > "$T/prs.json"
mkdir "$T/bin"
cat > "$T/bin/gh" <<EOF
#!/bin/bash
case "\$1 \$2" in
  "pr list") cat "\${PRS:-$T/prs.json}" ;;
  "api graphql") [ -n "\${GQL_FAIL:-}" ] && { echo "gh: FORBIDDEN" >&2; exit 1; }; cat "\${GQL:-$T/gql.json}" ;;
  "api repos/"*) b=\${2##*...}; cat "$T/compare-\$b.json" ;;
  *) echo "fake gh: unknown call \$*" >&2; exit 1 ;;
esac
EOF
chmod +x "$T/bin/gh"
echo '{"result":{"worktrees":[]}}' > "$T/ps.json"
cat > "$T/bin/orca" <<EOF
#!/bin/bash
[ "\$*" = "worktree ps --since 1d --json" ] || { echo "fake orca: unknown call \$*" >&2; exit 1; }
[ -n "\${ORCA_FAIL:-}" ] && { echo "orca: not running" >&2; exit 1; }
cat "\${PS:-$T/ps.json}"
EOF
chmod +x "$T/bin/orca"
export PATH="$T/bin:$PATH" START_LOCKS=$T/locks  # start locks of start.sh: never the live folder
export BOT_HOMES=$T/no-homes  # the other bot homes whose start locks also count: never the live ones
mkdir "$T/locks"
# $T/held: fresh start locks for #20 and #101 to #108, so those taken tickets have a worker (not DEAD).
mkdir -p "$T/held/20" && for i in 101 102 103 104 105 106 107 108; do mkdir "$T/held/$i"; done
fail=0
want() { [ "$2" = "$3" ] || { echo "FAIL: $1"; echo "  want: $(tr '\n' '|' <<<"$3")"; echo "  got:  $(tr '\n' '|' <<<"$2")"; fail=1; }; }
lines() { bash "$D/free_tickets.sh" 2>&1 | grep "^$1" ; }

out=$(bash "$D/free_tickets.sh"); echo "$out" | sed 's/^/  /'
want "FREE: mvp by number, then other slices, nits wait, each rule drops its ticket" \
  "$(grep '^FREE' <<<"$out")" "$(printf 'FREE: #5\nFREE: #10\nFREE: #12\nFREE: #3\nFREE: #30')"
want "NO SLICE: only the open ticket with no slice label" "$(grep '^NO SLICE' <<<"$out")" "NO SLICE: #23"
want "BUSY: files of open PRs and of a taken branch with no PR" "$(grep '^BUSY' <<<"$out")" \
  "$(printf 'BUSY: scripts/a.py PR #60\nBUSY: scripts/b.py #20 branch ticket-20')"
want "WORKERS: a linked branch with no PR is one worker" "$(grep '^WORKERS' <<<"$out")" "WORKERS: 1/8"

# Nits wait while another ticket is free, also with no worker (no #20).
jq '[.[] | .data.repository.issues.nodes |= map(select(.number != 20))]' "$T/gql.json" > "$T/gql-0.json"
want "a nit waits while 5 others are free" "$(GQL=$T/gql-0.json lines FREE)" \
  "$(printf 'FREE: #5\nFREE: #10\nFREE: #12\nFREE: #3\nFREE: #30')"
# Nits start only when nothing else is free.
jq '[.[] | .data.repository.issues.nodes |= map(select(.number as $n | [3,5,10,12,30] | index($n) | not))]' \
  "$T/gql.json" > "$T/gql-nits.json"
want "a nit starts when nothing else is free" "$(GQL=$T/gql-nits.json lines FREE)" "FREE: #40"

# The worker cap limits what the sweep starts, never what this script lists (bug of 2026-11-24:
# 5 FREE lines, all dropped for clashes or owner waits, hid 27 more). 1 worker, 8 free: all 8 print.
jq --slurpfile x <(for b in 50 51 52; do iss $b slice:mvp-chat; done) \
  '.[1].data.repository.issues.nodes += $x' "$T/gql.json" > "$T/gql-8.json"
want "1 worker, 8 free tickets: all 8 FREE lines, best first" "$(GQL=$T/gql-8.json lines 'WORKERS\|FREE')" \
  "$(printf 'WORKERS: 1/8\nFREE: #5\nFREE: #10\nFREE: #12\nFREE: #50\nFREE: #51\nFREE: #52\nFREE: #3\nFREE: #30')"
want "TAKEN: every linked branch, with or without a PR" "$(lines TAKEN)" "$(printf 'TAKEN: #20 ticket-20\nTAKEN: #21 feat/x PR #60')"
# taken <k>: gql.json (1 worker, #20) plus k taken tickets #101.. with no PR, so 1+k workers.
taken() { for ((i=101; i<101+$1; i++)); do echo '[]' > "$T/compare-ticket-$i.json"; done
  jq --slurpfile x <(for ((i=101; i<101+$1; i++)); do iss $i slice:mvp-rules 0 "" ticket-$i; done) \
    '.[1].data.repository.issues.nodes += $x' "$T/gql.json" > "$T/gql-w$((1+$1)).json"; }
taken 7; taken 8; taken 1; taken 5
want "8 workers run: WORKERS 8/8 and all 5 FREE lines" "$(GQL=$T/gql-w8.json lines 'WORKERS\|FREE')" \
  "$(printf 'WORKERS: 8/8\nFREE: #5\nFREE: #10\nFREE: #12\nFREE: #3\nFREE: #30')"
GQL=$T/gql-w8.json START_LOCKS=$T/held bash "$D/precheck.sh" >/dev/null && { echo "FAIL: precheck must fail when 8 workers run"; fail=1; }

# Live count (owner decision 2026-11-24): a working twenty workspace that is no review and on no TAKEN
# branch with no PR takes a slot. ws <name> <branch> <displayName> [state] [root] [archived] [taskTitle]
ws() { jq -nc --arg n "$1" --arg b "$2" --arg d "$3" --arg s "${4:-working}" --arg r "${5:-$HOME/orca/workspaces/twenty}" --arg a "${6:-false}" --arg t "${7:-}" \
  '{path: ($r + "/" + $n), branch: $b, displayName: $d, isArchived: ($a == "true"), agents: [{state: $s, taskTitle: $t, prompt: $t}]}'; }
psj() { jq -sc '{result: {worktrees: .}}'; }
{ ws a refs/heads/feat/a "Fix a"; ws b "" "Review code review 1"; ws c refs/heads/me/review-adversarial-x "Adversarial x"
  ws d refs/heads/ticket-20 "Ticket 20"; ws e refs/heads/feat/e "Fix e" done; ws f refs/heads/feat/f "Fix f" working "$HOME/orca/workspaces/other"
  ws g refs/heads/feat/g "Fix g" working "" true; ws h "" "Chore h"
  # i: on #21's taken branch feat/x, which has open PR #60: WORKERS skips it, so LIVE counts it (review BLOCK 1).
  ws i refs/heads/feat/x "Fix conflict PR 60"
  # Reviewers by task title, as review-spec.sh and the reviewer specs write it. m is a fixer: it counts.
  ws j "" "Pr 793" working "" "" "Review of PR 793."
  ws k "" "Round" working "" "" "FIX ROUND of PR 701. Review ONLY the fix diff"
  ws l "" "Fresh eye 36" working "" "" "Repo: twenty (~/code/twenty). You are an independent adversarial reviewer (sk..."
  ws n "" "Task 34" working "" "" "Repo: twenty (~/code/twenty). You run mattpocock-skills:code-review on a chan..."
  ws m "" "Fix twenty status" working "" "" "Cap 8 review: BLOCK 2, fix now"; } | psj > "$T/ps-live.json"
want "LIVE: working non-review twenty workspaces on no taken branch without a PR" \
  "$(PS=$T/ps-live.json bash -c "python3 -I '$D/slots.py'" | grep '^LIVE\|^SLOTS')" "$(printf 'LIVE: 4 (a, h, i, m)\nSLOTS: 3')"
# A cut ps list (result.truncated) may hide live work: the count fails.
jq '.result.truncated = true' "$T/ps-live.json" > "$T/ps-cut.json"
PS=$T/ps-cut.json python3 -I "$D/slots.py" >/dev/null 2>&1 && { echo "FAIL: slots must fail on a truncated ps list"; fail=1; }
# Sweeps of 2026-11-25: ps sets truncated when a paired host is not covered (hostScope.omittedHostIds), with
# every local row in the page (worktrees = totalCount). Twenty workspaces are local, so the count goes on.
n=$(jq '.result.worktrees | length' "$T/ps-live.json")
jq --argjson n "$n" '.result.truncated = true | .result.totalCount = $n | .result.hostScope = {hostIds: ["local"], omittedHostIds: ["runtime:x"]}' \
  "$T/ps-live.json" > "$T/ps-omit.json"
want "an uncovered paired host with every local row in the page still counts" \
  "$(PS=$T/ps-omit.json python3 -I "$D/slots.py" 2>&1 | grep '^LIVE\|^SLOTS\|^slots:')" "$(printf 'LIVE: 4 (a, h, i, m)\nSLOTS: 3')"
jq '.result.totalCount += 1' "$T/ps-omit.json" > "$T/ps-omit-cut.json"
PS=$T/ps-omit-cut.json python3 -I "$D/slots.py" >/dev/null 2>&1 && { echo "FAIL: slots must fail when rows are cut (fewer than totalCount)"; fail=1; }

# Double count of 2026-11-24: 6 taken tickets, 3 live workspaces, 2 of them the workers of taken tickets
# (on ticket-104 and ticket-105, in the real ps shape). A workspace on a taken branch counts once: 8 - 6 - 1.
# #104 and #105 have no start lock: their workspace holds them.
mkdir "$T/held6" && for i in 20 101 102 103; do mkdir "$T/held6/$i"; done
{ ws mako refs/heads/ticket-104 "Fix ticket 104" working "" "" "Repo: georgetown-mdi-gates4/twenty (~/code/twenty). Ticket: #104 (a..."
  ws koi refs/heads/ticket-105 "Fix chat short" working "" "" "Repo: georgetown-mdi-gates4/twenty. Ticket: #105 (short list..."
  ws tope refs/heads/me/fix-twenty-status "Fix twenty status" working "" "" "Repo: none (bot home files under ~/.orca/bots/<bot>/skills/twen..."
} | psj > "$T/ps-dbl.json"
want "6 taken, 3 live of which 2 are taken workers: LIVE 1, SLOTS 1" \
  "$(GQL=$T/gql-w6.json PS=$T/ps-dbl.json START_LOCKS=$T/held6 python3 -I "$D/slots.py" | grep '^DEAD\|^LIVE\|^SLOTS')" \
  "$(printf 'LIVE: 1 (tope)\nSLOTS: 1')"
# A live bot-home helper on no taken branch counts (owner, 2026-11-24: it uses compute), next to 6 held tickets.
ws tope refs/heads/me/fix-twenty-status "Fix twenty status" working "" "" "Repo: none (bot home files under ~/.orca/bots/<bot>/skills/twen..." \
  | psj > "$T/ps-helper.json"
want "a live bot-home helper takes a slot: 8 - 6 - 1" \
  "$(GQL=$T/gql-w6.json PS=$T/ps-helper.json START_LOCKS=$T/held python3 -I "$D/slots.py" | grep '^LIVE\|^SLOTS')" \
  "$(printf 'LIVE: 1 (tope)\nSLOTS: 1')"
# Cutover (2026-11-25): the Twenty bot runs this with its own BOT_HOME. A live twenty workspace that another
# bot started still takes a slot: the count reads workspaces by path, never by bot.
mkdir -p "$T/twenty-home" && echo '{"name": "Twenty"}' > "$T/twenty-home/bot.json"
want "another bot's live workspace takes a slot under this bot's BOT_HOME" \
  "$(BOT_HOME=$T/twenty-home GQL=$T/gql-w6.json PS=$T/ps-helper.json START_LOCKS=$T/held python3 -I "$D/slots.py" | grep '^LIVE\|^SLOTS')" \
  "$(printf 'LIVE: 1 (tope)\nSLOTS: 1')"
# 2 DEAD tickets free their slots: 6 taken, locks on 4, no workspace: 8 - 4 - 0.
want "2 DEAD tickets free their slots" \
  "$(GQL=$T/gql-w6.json START_LOCKS=$T/held6 python3 -I "$D/slots.py" | grep '^DEAD\|^LIVE\|^SLOTS')" \
  "$(printf 'DEAD: #104 ticket-104\nDEAD: #105 ticket-105\nLIVE: 0 ()\nSLOTS: 4')"
# Cutover (2026-11-25): a ticket another bot started under 3 hours ago has its start lock in that bot's home.
# It keeps its slot here too, or a sweep right after the cutover reads it as DEAD and may unlink its branch.
mkdir -p "$T/homes/other/locks/104" "$T/homes/stale/locks/105"; touch -t "$(date -v-4H +%Y%m%d%H%M)" "$T/homes/stale/locks/105"
want "a fresh start lock in another bot home keeps its ticket, a stale one does not" \
  "$(BOT_HOMES=$T/homes GQL=$T/gql-w6.json START_LOCKS=$T/held6 python3 -I "$D/slots.py" | grep '^DEAD\|^SLOTS')" \
  "$(printf 'DEAD: #105 ticket-105\nSLOTS: 3')"
# slot.sh <n>: the ticket the sweep just linked has no lock yet, and still holds its slot.
want "slot.sh <n> counts its own new link" \
  "$(GQL=$T/gql-w6.json START_LOCKS=$T/held6 python3 -I "$D/slots.py" 104 | grep '^DEAD\|^SLOTS')" \
  "$(printf 'DEAD: #105 ticket-105\nSLOTS: 3')"

# DEAD: a taken ticket with no PR, no working workspace on its branch or naming it, and no start lock under
# 3 hours old, and no live terminal on its branch. It frees its slot, and the line stays until someone
# unlinks the branch (review nit, 2026-11-24).
dead() { python3 -I "$D/slots.py" | grep '^DEAD' ; }
want "DEAD: #20 has no workspace and no start lock" "$(dead)" "DEAD: #20 ticket-20"
want "DEAD: a working workspace on the branch keeps it" "$(PS=$T/ps-live.json dead)" ""
ws q "" "Chore" working "" "" "Fix ticket #20 now" | psj > "$T/ps-name.json"
want "DEAD: a working agent that names #20 keeps it" "$(PS=$T/ps-name.json dead)" ""
ws d refs/heads/ticket-20 "Ticket 20" done | psj > "$T/ps-done.json"
want "DEAD: a done agent on the branch does not keep it" "$(PS=$T/ps-done.json dead)" "DEAD: #20 ticket-20"
# Review BLOCK 2 (2026-11-24): a worker that waits at its prompt is "done" with a live terminal. It keeps
# its ticket, whatever the agent state. A crashed one (terminalVerdict none) does not.
ws d refs/heads/ticket-20 "Ticket 20" done | jq -c '.terminalVerdict = "live"' | psj > "$T/ps-idle.json"
want "DEAD: a done agent with a live terminal on the branch keeps it" "$(PS=$T/ps-idle.json dead)" ""
ws d refs/heads/ticket-20 "Ticket 20" done | jq -c '.terminalVerdict = "none"' | psj > "$T/ps-crash.json"
want "DEAD: a done agent with no live terminal does not keep it" "$(PS=$T/ps-crash.json dead)" "DEAD: #20 ticket-20"
mkdir "$T/locks/20"
want "DEAD: a start lock under 3 hours old keeps it" "$(dead)" ""
touch -t "$(date -v-4H +%Y%m%d%H%M)" "$T/locks/20"
want "DEAD: a start lock over 3 hours old does not" "$(dead)" "DEAD: #20 ticket-20"
# Review BLOCK 1 (2026-11-24): a missing locks folder must not read as "every lock is gone" (8 DEAD, SLOTS 8).
out=$(GQL=$T/gql-w8.json START_LOCKS=$T/no/such python3 -I "$D/slots.py" 2>&1) && { echo "FAIL: a missing locks folder must exit nonzero"; fail=1; }
want "a missing locks folder: one error line, no DEAD and no SLOTS line" "$(grep -E '^(DEAD|SLOTS|slots:)' <<<"$out")" \
  "slots: no locks folder $T/no/such"
rmdir "$T/locks/20"
for i in 1 2 3 4 5 6 7; do ws "l$i" "" "Fix $i"; done | psj > "$T/ps-7.json"
PS=$T/ps-7.json START_LOCKS=$T/held bash "$D/precheck.sh" >/dev/null && { echo "FAIL: precheck must fail at 1 worker + 7 live"; fail=1; }
for i in 1 2 3 4 5 6; do ws "l$i" "" "Fix $i"; done | psj > "$T/ps-6.json"
PS=$T/ps-6.json START_LOCKS=$T/held bash "$D/precheck.sh" >/dev/null || { echo "FAIL: precheck must pass at 1 worker + 6 live"; fail=1; }
out=$(ORCA_FAIL=1 bash "$D/precheck.sh") || { echo "FAIL: precheck must pass when orca fails"; fail=1; }
grep -q '^PRECHECK ERROR: slots.py failed' <<<"$out" && grep -q 'orca worktree ps failed' <<<"$out" || { echo "FAIL: precheck must name the orca failure, got: $out"; fail=1; }

# PR cap: 6 non-draft PRs (plus a draft) still start work. 7 start nothing. The first PR keeps #21's head.
prs() { { for ((i=0; i<$1; i++)); do echo "{\"number\":$((70+i)),\"headRefName\":\"$( ((i)) && echo b$i || echo feat/x)\",\"files\":[],\"isDraft\":false}"; done
          echo '{"number":99,"headRefName":"d","files":[],"isDraft":true}'; } | jq -s . > "$T/prs$1.json"; }
prs 6; prs 7
[ -n "$(PRS=$T/prs6.json lines FREE)" ] || { echo "FAIL: 6 PRs wait, FREE lines must still print"; fail=1; }
want "7 PRs wait: a CAP line and no FREE line" "$(PRS=$T/prs7.json bash "$D/free_tickets.sh")" \
  "CAP: 7 open PRs, more than 6: start nothing"

# slot.sh runs after the sweep links its own branch, so that branch is in WORKERS: SLOTS 0 may start, -1 may not.
# Two overlapping sweeps (review of 2026-11-24): per-ticket locks let them start one worker over the cap.
GQL=$T/gql-w8.json START_LOCKS=$T/held bash "$D/slot.sh" 107 >/dev/null || { echo "FAIL: slot must pass at 8/8 (own branch counted)"; fail=1; }
want "slot: 9 workers after linking, the start stops" "$(GQL=$T/gql-w9.json START_LOCKS=$T/held bash "$D/slot.sh" 108; echo "exit $?")" \
  "$(printf 'WORKERS: 9/8 LIVE: 0 () no slot, start nothing\nexit 1')"
GQL=$T/gql-w2.json PS=$T/ps-7.json START_LOCKS=$T/held bash "$D/slot.sh" 101 >/dev/null && { echo "FAIL: slot must count live work (2 + 7 > 8)"; fail=1; }
GQL_FAIL=1 bash "$D/slot.sh" 20 >/dev/null 2>&1 && { echo "FAIL: slot must fail when free_tickets.sh fails"; fail=1; }
ORCA_FAIL=1 bash "$D/slot.sh" 20 >/dev/null 2>&1 && { echo "FAIL: slot must fail when orca fails"; fail=1; }
PRS=$T/prs7.json bash "$D/slot.sh" 20 >/dev/null && { echo "FAIL: slot must fail on the PR cap (no SLOTS line)"; fail=1; }
# Review NIT 2: no ticket, two tickets, a word, or a ticket on no TAKEN line with no PR starts nothing.
for a in "" "107 108" abc 999 21; do
  GQL=$T/gql-w8.json START_LOCKS=$T/held bash "$D/slot.sh" $a >/dev/null 2>&1 && { echo "FAIL: slot.sh '$a' must exit 1"; fail=1; }
done

# A GraphQL error stops the script: a ticket it could not read is never FREE.
jq '.[0].errors = [{"type":"FORBIDDEN"}]' "$T/gql.json" > "$T/gql-err.json"
out=$(GQL=$T/gql-err.json bash "$D/free_tickets.sh" 2>/dev/null) && { echo "FAIL: a GraphQL error must exit non-zero"; fail=1; }
[ -z "$(grep '^FREE' <<<"$out")" ] || { echo "FAIL: a GraphQL error must print no FREE line"; fail=1; }

# precheck.sh passes on a FREE line, fails on the PR cap, and passes with a PRECHECK ERROR line on a failure.
bash "$D/precheck.sh" >/dev/null || { echo "FAIL: precheck must pass when a ticket is free"; fail=1; }
PRS=$T/prs7.json bash "$D/precheck.sh" >/dev/null && { echo "FAIL: precheck must fail when 7 PRs wait"; fail=1; }
jq '[.[] | .data.repository.issues.nodes |= map(select(.number == 20))]' "$T/gql.json" > "$T/gql-none.json"
GQL=$T/gql-none.json bash "$D/precheck.sh" >/dev/null && { echo "FAIL: precheck must fail with slots but no FREE line"; fail=1; }
out=$(GQL_FAIL=1 bash "$D/precheck.sh") || { echo "FAIL: precheck must pass when free_tickets.sh fails"; fail=1; }
grep -q '^PRECHECK ERROR: slots.py failed.*free_tickets.sh failed' <<<"$out" || { echo "FAIL: precheck must name the failure, got: $out"; fail=1; }

# Run from another folder (sweep run 97, 2026-11-24: status.sh called by a relative path cd'd into the twenty
# repo, so slots.py was not found, exit 2, and no worker started). The absolute path works from any folder.
want "slots.py by its absolute path from a temp folder" "$(cd "$T" && START_LOCKS=$T/held python3 -I "$D/slots.py" | grep '^SLOTS')" "SLOTS: 7"
out=$(cd "$D/.." && bash twenty-status/status.sh 2>&1 | sed -n '/== free work check/,$p')
grep -q '^SLOTS: ' <<<"$out" || { echo "FAIL: status.sh by a relative path must still run slots.py, got: $out"; fail=1; }
# slots.py with no free_tickets.sh beside it (a lone copy): one hint line before the error, exit nonzero.
mkdir "$T/lone" && cp "$D/slots.py" "$T/lone/"
out=$(cd "$T" && python3 -I lone/slots.py 2>&1) && { echo "FAIL: a lone slots.py must exit nonzero"; fail=1; }
want "hint line first when slots.py cannot read free_tickets.sh" "$(head -1 <<<"$out")" \
  "slots.py: run it by its absolute path ~/.orca/bots/<bot>/skills/twenty-status/slots.py"
# A wrong relative path never runs slots.py, so only python's own error shows: exit nonzero.
(cd "$T" && python3 -I twenty-status/slots.py >/dev/null 2>&1) && { echo "FAIL: a wrong relative path must exit nonzero"; fail=1; }
[ $fail = 0 ] && echo "selftest_free ok"
exit $fail
