#!/bin/bash
# Runs the offline self-test of skills/gcp-cost-audit (fake gcloud and bq, no network).
# It lives in hooks/ so the loop that runs every self-test, in CI and by hand, runs it too.
# Run: ./hooks/gcp-cost-audit-selftest.sh
exec bash "$(dirname "$0")/../skills/gcp-cost-audit/test-audit.sh"
