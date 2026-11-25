#!/bin/bash
# One sweep at a time counts slots and starts workers (review NIT 1, 2026-11-24: five sweeps ran at once,
# each passed slot.sh, and WORKERS read 9/8). The sweep takes it before step 5.2 of its first ticket and
# releases it after its last step 5.5, also when it stops early.
# Usage: start-guard.sh [--project <name>] take|release
# --project is taken and has no effect, so a wrapper can pass it to every loop script (yw-workflow #301).
# take: exit 0 when taken, 1 when another sweep holds it. A guard over 10 minutes old is from a sweep that
#   died, so it is dropped first. release: exit 0.
# ponytail: two sweeps that both see one stale guard can both drop it, one after the other took a new one.
# The window is one stale guard per 10 minutes and a few milliseconds wide.
# One guard for all projects of the bot: the starts share one machine. It lives in $BOT_HOME/locks
# (START_LOCKS moves it, for tests).
[ -n "${START_LOCKS:-}" ] || [ -n "${BOT_HOME:-}" ] || { echo "BOT_HOME is not set: export the bot's home folder" >&2; exit 2; }
L=${START_LOCKS:-$BOT_HOME/locks}/sweep-start
case "${1:-}" in --project) shift; shift ;; --project=*) shift ;; esac
case "${1:-}" in
  take)
    mkdir -p "$(dirname "$L")"
    find "$L" -maxdepth 0 -mmin +10 -exec rmdir {} \; 2>/dev/null
    mkdir "$L" 2>/dev/null && exit 0
    echo "sweep-start held by another sweep since $(date -r "$L" +%H:%M 2>/dev/null): start no worker in this run"
    exit 1 ;;
  release) rmdir "$L" 2>/dev/null; exit 0 ;;
  *) echo "usage: start-guard.sh [--project <name>] take|release" >&2; exit 2 ;;
esac
