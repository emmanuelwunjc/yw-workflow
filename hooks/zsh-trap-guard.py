#!/usr/bin/env python3
"""Block two zsh traps in Bash tool commands, which run under zsh.

Catches:
  - An unbraced `$name:` followed by a letter zsh reads as a modifier
    (`a A c e h l P q Q r s t u &`), with an optional `g`, `f` or `w`
    prefix (e.g. `:gs`, `:wr`, `:fh`). zsh applies the modifier and keeps
    the rest of the word, so `origin/$s:refs/heads/x` becomes
    `origin/<s without extension>efs/heads/x`. Double quotes do not stop it.
  - `for v in $VAR` (or `${VAR}`) with one unquoted variable. zsh does not split
    words, so the loop runs once over the whole string, with no error.

Ignores text in single quotes (e.g. a `bash -c '...'` script), escaped `\\$`,
and the body of a quoted heredoc (`<<'EOF'`, `<<"EOF"`, `<<\\EOF`).

Misses:
  - Special parameters such as `$?:h` and `$#:h`, which zsh also modifies.
  - An apostrophe in an unquoted heredoc body. The scanner reads it as an
    open single quote and skips the text after it.
  - `for v in $A $B`: only a single variable is caught.
  - A `#` comment is read as code. A commented `for n in $LIST` is blocked,
    and an apostrophe in a comment (`# it's`) hides the text after it.
  - `$'...'` with an escaped quote (`$'it\\'s'`) hides the text after it.

Limits:
  - `arr=(a b); for n in $arr` is blocked, though zsh iterates an array
    correctly. Kept on purpose: the commands here are bash style, and the
    rewrite to `${=VAR}` or `"${arr[@]}"` is cheap.
  - Commands a script or a wrapper runs: only the command text is read.

Off switch: `[rules] zsh_traps = false` in `~/.handrail.toml`.
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

# The letters zsh 5.9 consumes after `$name:`, each with an optional
# `g`, `f` or `w` prefix. Checked with `zsh -c 's=a/b.c; echo $s:X'` for each
# letter X. A prefix alone is left as text (`$s:wide`, `$s:go` print as is).
MODIFIER = re.compile(r"(?<!\\)\$([A-Za-z_]\w*|\d):[gfw]*[aAcehlPqQrstu&]")
UNSPLIT_FOR = re.compile(r"\bfor\s+\w+\s+in\s+\$(\w+|\{\w+\})\s*(;|\n)")
QUOTED_HEREDOC = re.compile(
    r"<<-?\s*(?:'(\w+)'|\"(\w+)\"|\\(\w+))[^\n]*\n.*?^\s*(?:\1|\2|\3)\s*$",
    re.M | re.S)


def strip_quoted(command):
    """The command with quoted heredoc bodies and single-quoted text removed."""
    command = QUOTED_HEREDOC.sub("", command)
    out, in_double, i = [], False, 0
    while i < len(command):
        ch = command[i]
        if ch == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        if ch == '"':
            in_double = not in_double
        elif ch == "'" and not in_double:
            end = command.find("'", i + 1)
            i = len(command) if end < 0 else end + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def problems(command):
    """One message per trap found in the command."""
    text = strip_quoted(command)
    found = []
    for name in dict.fromkeys(m.group(1) for m in MODIFIER.finditer(text)):
        found.append("write `${%s}:` (zsh reads `$%s:` plus a letter as a "
                     "modifier, e.g. `$s:r` drops the extension)" % (name, name))
    if UNSPLIT_FOR.search(text):
        found.append("zsh does not split words in `for v in $VAR`: use "
                     "`${=VAR}` or run under `bash <<'EOF'`")
    return found


def enabled():
    if handrail_config is None:
        return True
    try:
        return handrail_config.load().enabled("zsh_traps")
    except Exception as exc:
        sys.stderr.write("handrail: config unreadable (%s), enforcing "
                         "defaults\n" % handrail_config.safe_error(exc))
        return True


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    found = problems(payload.get("tool_input", {}).get("command", ""))
    # the config costs a git call, so read it only when there is a hit
    if found and enabled():
        print("Blocked: the Bash tool runs this under zsh.\n- "
              + "\n- ".join(found), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
