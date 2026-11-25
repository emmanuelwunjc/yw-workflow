#!/usr/bin/env python3
"""Runs the offline self-check of skills/orca-bot/setup.py.

It lives in hooks/ so the loop that runs every self-test, in CI and by hand,
runs it too.

Run: ./hooks/orca-bot-selftest.py
"""
import pathlib
import subprocess
import sys

TEST = (pathlib.Path(__file__).resolve().parent.parent
        / "skills" / "orca-bot" / "test_setup.py")
sys.exit(subprocess.run([sys.executable, str(TEST)]).returncode)
