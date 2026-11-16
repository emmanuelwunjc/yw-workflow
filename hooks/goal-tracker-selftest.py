#!/usr/bin/env python3
"""Runs the offline self-check of skills/goal-tracker/tracker_sync.py.

It lives in hooks/ so the loop that runs every self-test, in CI and by hand,
runs it too.

Run: ./hooks/goal-tracker-selftest.py
"""
import pathlib
import subprocess
import sys

TEST = (pathlib.Path(__file__).resolve().parent.parent
        / "skills" / "goal-tracker" / "test_tracker_sync.py")
sys.exit(subprocess.run([sys.executable, str(TEST)]).returncode)
