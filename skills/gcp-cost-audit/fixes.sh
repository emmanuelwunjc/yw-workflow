#!/bin/bash
# Print, never run, the gcloud commands that fill each label gap audit.sh finds.
# Usage: bash fixes.sh <project> [region] [app] [legacy-app-values]
# Values for a missing owner or team come from the app's other resources. purpose comes from the
# resource name. Read and edit each line, then the owner runs it. Exit 2 if a gcloud list call failed.
AUDIT_MODE=fixes exec bash "$(dirname "$0")/audit.sh" "$@"
