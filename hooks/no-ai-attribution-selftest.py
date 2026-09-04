#!/usr/bin/env python3
"""Self-test for no-ai-attribution.py. Run it after any edit to that hook.

Every case here exists because the hook once got it wrong, or because a check
that has never gone red proves nothing.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).with_name("no-ai-attribution.py"))
BLOCK, ALLOW = 2, 0

CASES = [
    ("PR body carrying the footer", BLOCK,
     'gh pr create --body "fix stuff\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"'),
    ("PR body carrying a session URL", BLOCK,
     'gh pr create --body "fix stuff\n\nhttps://claude.ai/code/session_01ABC"'),
    ("issue comment carrying the footer", BLOCK,
     'gh issue comment 5 --body "done. Generated with Claude Code"'),
    ("release notes carrying the footer", BLOCK,
     'gh release create v1 --notes "🤖 Generated with Claude Code"'),
    ("heredoc PR body carrying a session URL", BLOCK,
     'gh pr create --body-file - <<EOF\nwork\n\nhttps://claude.ai/code/session_01XYZ\nEOF'),
    ("commit message with only the trailers", ALLOW,
     'git commit -m "fix: thing\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n'
     'Claude-Session: https://claude.ai/code/session_01ABC"'),
    ("commit trailers plus a PR body in one command", BLOCK,
     'git commit -m "fix: x\n\nClaude-Session: https://claude.ai/code/session_01ABC" && '
     'gh pr create --body "🤖 Generated with Claude Code"'),
    ("ordinary PR", ALLOW, 'gh pr create --body "a normal body"'),
    ("a PR that merely mentions the product by name", ALLOW,
     'gh pr create --body "adds a Claude Code hook"'),
]


def run(payload):
    return subprocess.run([sys.executable, HOOK], input=payload,
                          capture_output=True, text=True).returncode


def main():
    failures = 0
    for name, want, command in CASES:
        got = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))
        if got != want:
            failures += 1
            print(f"FAIL want={want} got={got}  {name}")
    for name, payload in (("non-Bash tool", json.dumps({"tool_name": "Read", "tool_input": {}})),
                          ("empty stdin", ""),
                          ("malformed stdin", "{not json")):
        got = run(payload)
        if got != ALLOW:
            failures += 1
            print(f"FAIL want={ALLOW} got={got}  {name}")

    print("no-ai-attribution: all checks pass" if not failures
          else f"no-ai-attribution: {failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
