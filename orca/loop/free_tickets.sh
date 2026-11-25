#!/bin/bash
# The free work check: prints `FREE: #<ticket>` for each ticket the twenty sweep may start. See free_tickets.py.
exec python3 -I "$(dirname "$0")/free_tickets.py"
