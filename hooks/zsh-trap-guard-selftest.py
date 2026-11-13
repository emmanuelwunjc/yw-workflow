#!/usr/bin/env python3
"""Self-test for zsh-trap-guard.py. Run it after any edit to that hook.

Each case was checked against zsh 5.9 with `zsh -c` before it was written.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).with_name("zsh-trap-guard.py"))
BLOCK, ALLOW = 2, 0

CASES = [
    # (name, expected exit, command, text the block message must hold)
    ("the push that failed in edsim-paper", BLOCK,
     'for p in "a:b"; do s=${p%%:*}; d=${p##*:}; '
     'git push -q origin origin/$s:refs/heads/$d; done', "${s}:"),
    ("a modifier at the end of a word", BLOCK, "cp $src:r/file .", "${src}:"),
    ("a modifier inside double quotes", BLOCK, 'echo "$s:h"', "${s}:"),
    ("the :A modifier", BLOCK, "ls $dir:A", "${dir}:"),
    ("the :gs modifier", BLOCK, "echo $s:gs/a/b/", "${s}:"),
    ("a positional parameter", BLOCK, "echo $1:t", "${1}:"),
    ("the w prefix", BLOCK, "echo $s:wr", "${s}:"),
    ("the g prefix in a word", BLOCK, 'echo "$h:gateway"', "${h}:"),
    ("the f prefix", BLOCK, "echo $s:fr", "${s}:"),
    ("an unsplit for-loop", BLOCK, "for n in $LIST; do echo $n; done", "${=VAR}"),
    ("an unsplit for-loop, braced", BLOCK, "for n in ${LIST}\ndo echo $n\ndone",
     "${=VAR}"),
    ("braced name", ALLOW, "git push origin ${s}:refs/heads/x", ""),
    ("quote closes before the colon", ALLOW, 'echo "$s":x', ""),
    ("a URL with a port", ALLOW, "curl http://host:8080", ""),
    ("a PATH value", ALLOW, "PATH=$HOME:/bin ls", ""),
    ("a colon then another variable", ALLOW, "PATH=$HOME:$PATH ls", ""),
    ("a letter zsh does not consume", ALLOW, "echo $s:x $s:wide $s:go", ""),
    ("a prefix with no modifier after it", ALLOW, "echo $s:ww $s:fx $s:fo", ""),
    ("an escaped dollar", ALLOW, r"echo \$s:r", ""),
    ("single-quoted text goes to bash", ALLOW,
     "bash -c 'git push origin $s:refs/heads/x'", ""),
    ("an apostrophe inside double quotes", ALLOW,
     'echo "it\'s ${s}:r"', ""),
    ("a quoted heredoc", ALLOW,
     "bash <<'EOF'\nfor n in $LIST; do git push origin $s:refs; done\nEOF", ""),
    ("a double-quoted heredoc", ALLOW, 'cat <<"EOF"\n$s:r\nEOF', ""),
    ("a backslash heredoc", ALLOW, "cat <<\\EOF\n$s:r\nEOF", ""),
    ("an unquoted heredoc still expands", BLOCK,
     "cat <<EOF\n$s:r\nEOF", "${s}:"),
    ("a split for-loop", ALLOW, "for n in ${=LIST}; do echo $n; done", ""),
    ("a literal for-loop", ALLOW, "for n in a b c; do echo $n; done", ""),
    ("a quoted argument list", ALLOW, 'for n in "$@"; do echo $n; done', ""),
]
# every letter zsh consumes, so dropping one from the hook fails a case
CASES += [("the :%s modifier" % x, BLOCK, "echo $s:%szz" % x, "${s}:")
          for x in "aAcehlPqQrstu&"]


def run(payload, env=None):
    return subprocess.run([sys.executable, HOOK], input=payload, env=env,
                          capture_output=True, text=True)


def main():
    failures = 0
    for name, want, command, needle in CASES:
        got = run(json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": command}}))
        if got.returncode != want or needle not in got.stderr:
            failures += 1
            print(f"FAIL want={want} got={got.returncode}  {name}  "
                  f"stderr={got.stderr.strip()!r}")
    for name, payload in (("non-Bash tool",
                           json.dumps({"tool_name": "Read", "tool_input": {}})),
                          ("empty stdin", ""),
                          ("malformed stdin", "{not json")):
        got = run(payload).returncode
        if got != ALLOW:
            failures += 1
            print(f"FAIL want={ALLOW} got={got}  {name}")

    # the off switch: a user config with the rule off lets the command run
    with tempfile.TemporaryDirectory() as home:
        Path(home, ".handrail.toml").write_text("[rules]\nzsh_traps = false\n")
        env = dict(os.environ, HOME=home)
        got = run(json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "echo $s:r"}}),
                  env=env).returncode
        if got != ALLOW:
            failures += 1
            print(f"FAIL want={ALLOW} got={got}  rule switched off in config")

    print("zsh-trap-guard: all checks pass" if not failures
          else f"zsh-trap-guard: {failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
