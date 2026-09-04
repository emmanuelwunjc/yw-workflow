#!/usr/bin/env python3
"""Block the "Generated with Claude Code" footer and session URLs from anything
that gets published: PR bodies, issues, comments, releases, commit messages.

Yiming asked for this globally on 2026-09-01. The default harness instructions
tell the model to append that footer to PR bodies; this hook is what makes the
CLAUDE.md rule win over it, since prose alone lost.
"""
import json
import re
import sys

BANNED = [
    (re.compile(r"Generated with \[?Claude Code", re.I), 'the "Generated with Claude Code" footer'),
    (re.compile(r"🤖\s*Generated with"), 'the robot-emoji generation footer'),
    (re.compile(r"https://claude\.ai/code/session_"), "a claude.ai session URL"),
]

# A Claude-Session trailer in a commit message is wanted; git history attribution
# is not publication. Exempt only the URL token on that trailer, never the rest of
# the line: a compound command can put a `gh pr create` after it on the same line.
TRAILER = re.compile(
    r"^[ \t]*Claude-Session:[ \t]*https://claude\.ai/code/session_\S+", re.M)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    stripped = TRAILER.sub("", command)
    for pattern, label in BANNED:
        if pattern.search(stripped):
            print(
                f"Blocked: this command would publish {label}.\n"
                "Yiming's standing rule: never put AI-generation footers or session "
                "URLs in anything other people read (PR bodies, issues, comments, "
                "releases). Remove those lines and run it again.\n"
                "Co-Authored-By and Claude-Session trailers in a git commit message "
                "are fine and are not what this blocks.",
                file=sys.stderr,
            )
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
