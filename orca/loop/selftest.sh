#!/bin/bash
# Run every test of the loop: each test-*.sh beside this file, on fake projects, with no network.
# The cleanup and status tests also delete each guard in turn, so a full run takes about 40 minutes.
# Usage: bash selftest.sh. Exit 1 when any test fails, and its name is printed.
D=$(cd "$(dirname "$0")" && pwd); fail=0
for t in "$D"/test-*.sh; do
  if bash "$t" > /dev/null 2>&1; then echo "ok   $(basename "$t")"; else echo "FAIL $(basename "$t")"; fail=1; fi
done
exit $fail
