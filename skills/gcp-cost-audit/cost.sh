#!/bin/bash
# Read-only spend check for one GCP project.
# Usage: bash cost.sh <project> <app> [legacy-app-values]
# 1. If a BigQuery billing export exists (env BILLING_EXPORT_TABLE=proj.dataset.table, or a
#    gcp_billing_export_* table in a dataset of <project>), print spend to date by label app.
# 2. Else print the budgets that cover <project>, and the manual source for spend.
# Exit 2 if a gcloud or bq call failed.
set -euo pipefail
[ $# -ge 2 ] || { sed -n '3p' "$0" >&2; exit 2; }
PROJECT=$1
APP=$2
LEGACY=${3:-}
die() { echo "ERROR: $*" >&2; exit 2; }

TABLE=${BILLING_EXPORT_TABLE:-}
if [ -z "$TABLE" ]; then
  datasets=$(bq ls --project_id="$PROJECT" --format=json) || die "bq ls of $PROJECT failed"
  for ds in $(echo "${datasets:-[]}" | python3 -c 'import json,sys; [print(d["datasetReference"]["datasetId"]) for d in json.loads(sys.stdin.read() or "[]")]'); do
    t=$(bq ls --format=json "$PROJECT:$ds" | python3 -c 'import json,sys; [print(t["tableReference"]["tableId"]) for t in json.loads(sys.stdin.read() or "[]") if t["tableReference"]["tableId"].startswith("gcp_billing_export")]' | head -1) || die "bq ls of $PROJECT:$ds failed"
    [ -n "$t" ] && { TABLE="$PROJECT.$ds.$t"; break; }
  done
fi

if [ -n "$TABLE" ]; then
  echo "Spend to date by label app, from the billing export $TABLE:"
  bq query --project_id="$PROJECT" --use_legacy_sql=false --format=pretty \
    "SELECT IFNULL(l.value, '(no app label)') AS app, ROUND(SUM(cost), 2) AS cost
     FROM \`$TABLE\` LEFT JOIN UNNEST(labels) AS l ON l.key = 'app'
     WHERE project.id = '$PROJECT' GROUP BY app ORDER BY cost DESC" || die "bq query failed"
  echo "The export lags about a day behind real use."
  exit 0
fi

echo "No BigQuery billing export found for $PROJECT."
number=$(gcloud projects describe "$PROJECT" --project "$PROJECT" --format='value(projectNumber)') || die "projects describe failed"
account=$(gcloud billing projects describe "$PROJECT" --project "$PROJECT" --format='value(billingAccountName)') || die "billing projects describe failed"
[ -n "$account" ] || die "$PROJECT has no billing account"
budgets=$(gcloud billing budgets list --billing-account="${account#billingAccounts/}" --project "$PROJECT" --format=json) || die "budgets list failed"
echo "$budgets" | python3 -c '
import json, sys
number, app, legacy = sys.argv[1], sys.argv[2], set(filter(None, sys.argv[3].split(",")))
apps = set()
for b in json.load(sys.stdin):
    f = b.get("budgetFilter", {})
    if f.get("projects") and "projects/" + number not in f["projects"]:
        continue
    amt = b.get("amount", {}).get("specifiedAmount", {})
    lab = f.get("labels", {}).get("app", [])
    apps |= set(lab)
    print("Budget %s: %s %s per %s, app label filter: %s" % (b["displayName"], amt.get("units", "(last period spend)"),
          amt.get("currencyCode", ""), f.get("calendarPeriod", "custom period"), ",".join(lab) or "none"))
if app not in apps:
    print("WARNING: no budget on this project filters on app=%s." % app)
for v in sorted(legacy - apps):
    print("WARNING: spend labelled app=%s falls outside every budget. Rename the label to app=%s." % (v, app))
' "$number" "$APP" "$LEGACY"
echo "The budget API holds the limit and the alert thresholds, not the spend so far."
echo "Manual source for spend: console Billing > Reports, project $PROJECT, group or filter by label app."
echo "Billing Reports and the budget alerts lag about a day behind real use."
