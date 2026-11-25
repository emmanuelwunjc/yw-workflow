#!/bin/bash
# Read-only label audit of one app's GCP resources. Runs only gcloud list/describe calls.
# Usage: bash audit.sh <project> <region> <app> [legacy-app-values]
#   e.g. bash audit.sh my-project us-east1 pay-bot pay-chatbot,pay-old
# A resource is in scope when its app label is <app>, or a legacy value (flagged RENAME),
# or it has no app label and its name holds the app's first word (e.g. "pay").
# Service accounts and Scheduler jobs take no labels: their description holds key=value pairs.
# Exit: 0 no gaps, 1 gaps found, 2 a gcloud call failed (never read as zero resources).
# AUDIT_MODE=fixes prints the fix commands instead of the table (fixes.sh sets it).
set -euo pipefail
[ $# -ge 3 ] || { sed -n '3,4p' "$0" >&2; exit 2; }
PROJECT=$1
REGION=$2
APP=$3
LEGACY=${4:-}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

fetch() {  # fetch <kind> <gcloud args...>: JSON to $T/<kind>.json, or stop with exit 2
  local kind=$1; shift
  if ! gcloud "$@" --project "$PROJECT" --format=json >"$T/$kind.json" 2>"$T/$kind.err"; then
    echo "ERROR: gcloud $* failed for $kind:" >&2
    head -3 "$T/$kind.err" >&2
    exit 2
  fi
}

fetch run-service run services list --region "$REGION"
fetch run-job run jobs list --region "$REGION"
fetch scheduler scheduler jobs list --location "$REGION"
fetch bucket storage buckets list
fetch repo artifacts repositories list --location "$REGION"
fetch topic pubsub topics list
fetch sa iam service-accounts list

python3 "$HERE/scan.py" "$T" "$PROJECT" "$REGION" "$APP" "$LEGACY" "${AUDIT_MODE:-table}"
