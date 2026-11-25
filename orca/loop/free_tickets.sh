#!/bin/bash
# The free work check: prints `FREE: #<ticket>` for each ticket the sweep may start. See free_tickets.py.
# Usage: free_tickets.sh [--project <name>]
exec python3 -I "$(dirname "$0")/free_tickets.py" "$@"
