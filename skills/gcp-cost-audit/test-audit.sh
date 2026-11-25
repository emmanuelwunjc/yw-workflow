#!/bin/bash
# Self-test for audit.sh and fixes.sh with a fake gcloud on PATH. Nothing reaches Google.
# The fixtures copy the JSON shapes of real list calls on mdi-yimingwu-pets (2026-11-24).
# Run: bash ~/.orca/bots/mdi-mac/skills/gcp-cost-audit/test-audit.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }

mkdir -p "$T/bin" "$T/fx"
cat >"$T/bin/gcloud" <<'EOF'
#!/bin/bash
echo "$*" >>"$FAKE_LOG"
case "$*" in
  "run services list"*) k=run-service ;; "run jobs list"*) k=run-job ;;
  "scheduler jobs list"*) k=scheduler ;; "storage buckets list"*) k=bucket ;;
  "artifacts repositories list"*) k=repo ;; "pubsub topics list"*) k=topic ;;
  "iam service-accounts list"*) k=sa ;; *) echo "fake gcloud: unknown call $*" >&2; exit 9 ;;
esac
[ "$k" = "$FAKE_FAIL" ] && { echo "ERROR: (gcloud.$k) PERMISSION_DENIED" >&2; exit 1; }
cat "$FAKE_DIR/$k.json"
EOF
chmod +x "$T/bin/gcloud"

L='"owner": "yw1084", "team": "mdi", "purpose": "twenty-bot", "app": "twenty-bot"'
D='Runs it. owner=yw1084,team=mdi,purpose=friday-dump-run,app=twenty-bot'
cat >"$T/fx/run-service.json" <<EOF
[{"metadata": {"name": "twenty-chatbot", "labels": {$L, "cloud.googleapis.com/location": "us-east1"}}},
 {"metadata": {"name": "pets-model", "labels": {"app": "kathleen-chatbot"}}}]
EOF
echo "[{\"metadata\": {\"name\": \"twenty-friday\", \"labels\": {$L}}}]" >"$T/fx/run-job.json"
echo "[{\"description\": \"$D\", \"httpTarget\": {\"uri\": \"https://x\"}, \"name\": \"projects/p/locations/us-east1/jobs/twenty-friday-run\"}]" >"$T/fx/scheduler.json"
echo "[{\"labels\": {$L}, \"name\": \"p-twenty-friday\"}, {\"labels\": {\"app\": \"ibadat-rag\"}, \"name\": \"p-ibadat-rag\"}]" >"$T/fx/bucket.json"
echo "[{\"labels\": {\"app\": \"kathleen-chatbot\"}, \"name\": \"projects/p/locations/us-east1/repositories/cloud-run-source-deploy\"}]" >"$T/fx/repo.json"
echo '[{"labels": {"goog-managed-by": "artifact-analysis"}, "name": "projects/p/topics/container-analysis-notes-v1beta1"}]' >"$T/fx/topic.json"
echo "[{\"description\": \"$D\", \"email\": \"twenty-friday-runtime@p.iam.gserviceaccount.com\"}]" >"$T/fx/sa.json"

run() {  # run <script> [FAKE_FAIL kind]: stdout to $T/out, exit code to $T/rc
  PATH="$T/bin:$PATH" FAKE_DIR="$T/fx" FAKE_LOG="$T/calls" FAKE_FAIL="${2:-none}" \
    bash "$HERE/$1" p us-east1 >"$T/out" 2>"$T/err"; echo $? >"$T/rc"
}

# 1. Every twenty resource labelled. Other apps and Google topics are out of scope.
run audit.sh
check "all labelled: exit 0" '[ "$(cat $T/rc)" = 0 ]'
check "all labelled: 5 in scope, 0 gaps" 'grep -q "^5 in scope for app=twenty-bot, 0 with gaps" $T/out'
check "other apps not listed" '! grep -qE "pets-model|ibadat|cloud-run-source|container-analysis" $T/out'

# 2. One bucket lacks team, and carries the legacy app value.
echo '[{"labels": {"owner": "yw1084", "purpose": "eval", "app": "twenty-chatbot"}, "name": "p-twenty-chatbot-eval"}]' >"$T/fx/bucket.json"
run audit.sh
check "one missing: exit 1" '[ "$(cat $T/rc)" = 1 ]'
check "one missing: row names team and the rename" 'grep -q "p-twenty-chatbot-eval .*missing team + RENAME app=twenty-chatbot" $T/out'
check "one missing: 1 gap" 'grep -q "1 with gaps" $T/out'
run fixes.sh
check "fixes: one printed command" '[ "$(wc -l <$T/out)" -eq 1 ]'
check "fixes: keeps purpose, fills team, renames app" 'grep -q "buckets update gs://p-twenty-chatbot-eval --update-labels=owner=yw1084,team=mdi,purpose=eval,app=twenty-bot --project p" $T/out'

# 3. A gcloud error stops the run. It is never read as zero resources.
run audit.sh bucket
check "gcloud error: exit 2" '[ "$(cat $T/rc)" = 2 ]'
check "gcloud error: no table" '! grep -q "in scope" $T/out'
check "gcloud error: says why" 'grep -q PERMISSION_DENIED $T/err'
run fixes.sh sa
check "fixes on gcloud error: exit 2, prints nothing" '[ "$(cat $T/rc)" = 2 ] && [ ! -s $T/out ]'

# 4. Read-only: no call made a write, and no script line holds a write verb outside printed text.
W='(create|update|delete|add-iam|set-iam|deploy)'
check "no write call reached gcloud" '! grep -qE "$W" $T/calls'
check "no write verb outside print text" '! grep -nE "\b$W\b" "$HERE"/audit.sh "$HERE"/fixes.sh "$HERE"/cost.sh "$HERE"/scan.py | grep -vE ":[0-9]+:\s*(#|print\(|echo )"'
check "scripts are ASCII" 'python3 -c "import sys; [open(f, \"rb\").read().decode(\"ascii\") for f in sys.argv[1:]]" "$HERE"/*.sh "$HERE"/scan.py "$HERE"/SKILL.md 2>/dev/null'

[ $fail = 0 ] && echo "all checks pass" || { echo "some checks failed"; exit 1; }
