#!/usr/bin/env python3
"""Block an `orca slack post` whose text is in a disallowed script.

A bot that posts to Slack must write in the allowed languages. Before this hook
that held only through a wrapper the bot had to remember to use. This hook
reads the Bash command instead, so every bot on a machine with the plugin is
covered.

Reads:
  - Every argument after `orca slack post` (the place, `--text`, a bare text).
  - The file `--text-file <path>` names, relative to the call's cwd.
  - `--text-file -` reads stdin, which a hook cannot see, so it is blocked.

Misses:
  - The final message of a Slack-woken turn, which Orca sends without a tool
    call. `~/.claude/hooks/orca-final-language.py` covers it, on the owner's
    machine only.
  - Text the shell makes at run time: `$VAR`, `$(cat file)`, a file written
    earlier in the same command.
  - `orca bot reply` and every other route to Slack.

Limits:
  - A missing or unreadable text file passes, because `orca` itself fails on it.
  - A channel or person name in a disallowed script is blocked too.
  - A config that cannot load leaves the rule at its default, which is off.
    A bad `disallowed` value keeps the switch and uses the default ranges.

Settings in `.handrail.toml`: `[rules] slack_language = true` turns it on.
`[slack_language] disallowed` maps a script name to [first, last] code point
ranges. Self-test: slack-language-selftest.py.
"""
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import handrail_config
except Exception:  # without the config the rule stays at its default, off
    handrail_config = None

OPERATORS = set(";&|()<>\n")
TEXT_FILE = "--text-file"


def post_args(command):
    """The argument lists of each `orca slack post` in the command."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="".join(OPERATORS))
    lexer.whitespace = " \t\r"
    lexer.commenters = ""  # an unquoted #channel is an argument
    try:
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes: the shell refuses it anyway
        return []
    found = []
    for i in range(len(tokens) - 2):
        if (Path(tokens[i]).name == "orca"
                and tokens[i + 1:i + 3] == ["slack", "post"]):
            args = []
            for token in tokens[i + 3:]:
                if set(token) <= OPERATORS:
                    break
                args.append(token)
            found.append(args)
    return found


def text_files(args):
    """The paths `--text-file` names, in either spelling."""
    for i, arg in enumerate(args):
        if arg == TEXT_FILE and i + 1 < len(args):
            yield args[i + 1]
        elif arg.startswith(TEXT_FILE + "="):
            yield arg[len(TEXT_FILE) + 1:]


def first_hit(text, disallowed):
    """(script name, code point) for the first disallowed character, or None.

    The name comes from a config a repo may set, and it lands in the block
    message the model reads, so it goes through safe_path like a path does.
    """
    for ch in text:
        point = ord(ch)
        for name, ranges in disallowed.items():
            if any(lo <= point <= hi for lo, hi in ranges):
                return handrail_config.safe_path(name, limit=40), point
    return None


def problems(command, cwd, disallowed):
    found = []
    for args in post_args(command):
        hit = first_hit(" ".join(args), disallowed)
        if hit:
            found.append("an argument holds %s text (U+%04X)" % hit)
        for name in text_files(args):
            if name == "-":
                found.append("`--text-file -` reads stdin, which this check "
                             "cannot see: write the text to a file and pass "
                             "its path")
                continue
            try:
                text = (Path(cwd) / name).read_text(encoding="utf-8",
                                                    errors="replace")
            except OSError:
                continue  # orca reports a missing file itself
            hit = first_hit(text, disallowed)
            if hit:
                found.append("`%s` holds %s text (U+%04X)"
                             % ((handrail_config.safe_path(name),) + hit))
    return found


def valid(disallowed):
    """True when the value is a map of name to [first, last] integer pairs."""
    def is_int(x):
        return isinstance(x, int) and not isinstance(x, bool)
    return isinstance(disallowed, dict) and all(
        isinstance(ranges, list) and all(
            isinstance(pair, list) and len(pair) == 2
            and all(is_int(x) for x in pair) for pair in ranges)
        for ranges in disallowed.values())


def settings(cwd):
    """(on, disallowed) from the config.

    A config that cannot load leaves the rule at its default, off. A bad
    `disallowed` value keeps the switch and uses the default ranges, so a repo
    cannot switch off a rule the user switched on by writing a broken value.
    """
    if handrail_config is None:
        return False, {}
    default = handrail_config.VALUE_DEFAULTS["slack_language"]["disallowed"]
    try:
        config = handrail_config.load(cwd)
    except Exception as exc:
        sys.stderr.write("handrail: config unreadable (%s), slack_language "
                         "stays off\n" % handrail_config.safe_error(exc))
        return False, default
    disallowed = config.value("slack_language", "disallowed")
    if not valid(disallowed):
        sys.stderr.write("handrail: [slack_language] disallowed is not a map of "
                         "name to [first, last] integer pairs, using the "
                         "default\n")
        disallowed = default
    return config.enabled("slack_language"), disallowed


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "")
    if "slack" not in command or "post" not in command:
        sys.exit(0)  # the config costs a git call, so skip it when it cannot matter
    cwd = payload.get("cwd") or "."
    on, disallowed = settings(cwd)
    if not on:
        sys.exit(0)
    found = problems(command, cwd, disallowed)
    if found:
        print("Blocked: this Slack post holds text in a script the "
              "config disallows. Rewrite it without that script.\n- " + "\n- ".join(found), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
