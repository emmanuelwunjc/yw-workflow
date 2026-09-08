#!/usr/bin/env python3
"""Block the "Generated with Claude Code" footer and session URLs from anything
that gets published: PR bodies, issues, comments, releases, commit messages.

The default harness instructions tell the model to append that footer to PR
bodies. This hook is what makes a repo's own rule win over that instruction,
since prose alone lost.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import handrail_config
except Exception:  # a missing or broken config must not disarm the guard
    handrail_config = None


def _policy():
    """Effective policy, or None when it cannot be read.

    None means "enforce with no citation": a config that fails to load is a
    reason to keep guarding, never a reason to stop.
    """
    if handrail_config is None:
        return None
    try:
        return handrail_config.load()
    except Exception as exc:
        # The kind of failure, never the parser's message: that message quotes
        # the config back, and a TOML key is arbitrary text of unbounded length
        # reaching a block reason the model reads as an instruction.
        sys.stderr.write("handrail: config unreadable (%s), enforcing "
                         "defaults\n" % handrail_config.safe_error(exc))
        return None

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


def _safe_path(value):
    return (handrail_config.safe_path(value) if handrail_config
            else str(value))


def _safe_error(exc):
    return (handrail_config.safe_error(exc) if handrail_config
            else type(exc).__name__)


def scan(paths, exempt_trailer=True):
    """CI mode: check files instead of a Bash command.

    The hook stops a publish at the moment it is typed. That only covers this
    laptop, so CI re-checks the artefacts themselves: the PR body, and any file
    in the diff.

    exempt_trailer keeps a Claude-Session line legal, which is right for a
    commit message and wrong for a PR body. Pass --published for text that other
    people read, where the trailer is the thing being banned. Without that, a
    hand-written trailer in a PR body walks straight through the check that
    exists to stop it.

    Returns the number of files with at least one finding.
    """
    bad = 0
    for name in paths:
        try:
            text = Path(name).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # Unreadable means unchecked, and unchecked must not read as clean.
            print("%s: cannot read (%s)" % (_safe_path(name),
                                            _safe_error(exc)), file=sys.stderr)
            bad += 1
            continue
        stripped = TRAILER.sub("", text) if exempt_trailer else text
        hits = [label for pattern, label in BANNED if pattern.search(stripped)]
        if hits:
            bad += 1
            for label in hits:
                print("%s: publishes %s" % (_safe_path(name), label),
                      file=sys.stderr)
    return bad


def main():
    # scan takes paths on argv. CI has no hook payload and must not block on a
    # stdin read that will never be fed.
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        args = sys.argv[2:]
        published = "--published" in args
        sys.exit(1 if scan([a for a in args if a != "--published"],
                           exempt_trailer=not published) else 0)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    # The cheap checks come first so a broken config warns on a Bash command
    # rather than on every tool call. This hook fires constantly, and a steady
    # warning is what teaches people to stop reading stderr.
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    # The patterns are matched BEFORE the config is read. Resolving the policy
    # shells out to git, which costs about 11 ms, and this hook runs on every
    # Bash command while a command carrying a footer is rare. Checking the
    # switch here rather than up front is the same decision, paid for only when
    # it matters.
    stripped = TRAILER.sub("", command)
    for pattern, label in BANNED:
        if pattern.search(stripped):
            policy = _policy()
            if policy is not None and not policy.enabled("ai_attribution"):
                sys.exit(0)
            citation = policy.citation() if policy else ""
            print(
                f"Blocked: this command would publish {label}.\n"
                "Never put AI-generation footers or session URLs in anything "
                "other people read: PR bodies, issues, comments, releases. "
                "Remove those lines and run it again.\n"
                "Co-Authored-By and Claude-Session trailers in a git commit "
                "message are history attribution rather than publication, and "
                "stay."
                + (("\n" + citation) if citation else ""),
                file=sys.stderr,
            )
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
