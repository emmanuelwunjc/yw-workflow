#!/usr/bin/env python3
"""Self-test for slack-language.py. Run it after any edit to that hook.

It runs with no `orca` on PATH, because the hook reads the command text and
never runs `orca` itself. CJK test text is made with chr() so this file stays
English.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).with_name("slack-language.py"))
BLOCK, ALLOW = 2, 0
HAN = chr(0x4F60) + chr(0x597D)  # two Han characters
KANA = chr(0x3053) + chr(0x3093)  # two hiragana characters
HANGUL = chr(0xC548) + chr(0xB155)  # two Hangul syllables
ON = "[rules]\nslack_language = true\n"


def path_without_orca():
    """PATH with every directory that holds an `orca` left out."""
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not Path(d, "orca").exists()]
    return os.pathsep.join(dirs)


def run(command, home, cwd):
    payload = json.dumps({"tool_name": "Bash", "cwd": cwd,
                          "tool_input": {"command": command}})
    env = dict(os.environ, HOME=home, PATH=path_without_orca())
    return subprocess.run([sys.executable, HOOK], input=payload, env=env,
                          cwd=cwd, capture_output=True, text=True)


def main():
    failures = 0

    def expect(name, want, command, home, cwd, needle=""):
        nonlocal failures
        got = run(command, home, cwd)
        if (got.returncode != want or needle not in got.stderr
                or "Traceback" in got.stderr):
            failures += 1
            print(f"FAIL want={want} got={got.returncode}  {name}  "
                  f"stderr={got.stderr.strip()!r}")

    with tempfile.TemporaryDirectory() as on_home, \
            tempfile.TemporaryDirectory() as off_home, \
            tempfile.TemporaryDirectory() as work:
        Path(on_home, ".handrail.toml").write_text(ON)
        Path(work, "cjk.md").write_text("hello " + HAN + "\n", encoding="utf-8")
        Path(work, "en.md").write_text("hello team\n", encoding="utf-8")

        cases = [
            # (name, expected exit, command, text the block message must hold)
            ("CJK argument", BLOCK,
             'orca slack post "#general" "' + HAN + '"', "cjk"),
            ("CJK in --text", BLOCK,
             "orca slack post '#general' --text '" + KANA + "'", "cjk"),
            ("Hangul argument", BLOCK,
             'orca slack post @matteo "' + HANGUL + '"', "U+C548"),
            ("CJK text file", BLOCK,
             "orca slack post '#general' --text-file cjk.md", "cjk.md"),
            ("CJK text file, = form", BLOCK,
             "orca slack post '#general' --text-file=cjk.md", "cjk.md"),
            ("text file read from stdin", BLOCK,
             "orca slack post '#general' --text-file - <<'EOF'\nhi\nEOF",
             "stdin"),
            ("full path to orca", BLOCK,
             '/usr/local/bin/orca slack post "#g" "' + HAN + '"', "cjk"),
            ("post after another command", BLOCK,
             'cd . && orca slack post "#g" "' + HAN + '"', "cjk"),
            ("English passes", ALLOW,
             'orca slack post "#general" "hello team"', ""),
            ("English text file passes", ALLOW,
             "orca slack post '#general' --text-file en.md", ""),
            ("no orca command passes", ALLOW, 'echo "' + HAN + '"', ""),
            ("CJK in a later command passes", ALLOW,
             'orca slack post "#g" "hi"; echo "' + HAN + '"', ""),
            ("CJK on a later line passes", ALLOW,
             'orca slack post "#g" "hi"\necho "' + HAN + '"', ""),
            ("another orca slack verb passes", ALLOW,
             'orca slack find "' + HAN + '"', ""),
            ("missing text file passes (orca reports it)", ALLOW,
             "orca slack post '#g' --text-file nope.md", ""),
        ]
        for name, want, command, needle in cases:
            expect(name, want, command, on_home, work, needle)

        # A bad repo value must keep the user's switch and the default
        # ranges, and no config shape may crash the hook.
        for n, shape in enumerate(("disallowed = 5", "disallowed = { cjk = [['1', '99999']] }",
                      "disallowed = { cjk = [[1]] }", "disallowed = { cjk = 5 }")):
            repo = Path(work, "repo-%d" % n)
            repo.mkdir()
            Path(repo, ".handrail.toml").write_text(
                "[slack_language]\n" + shape + "\n")
            expect("bad repo value %r keeps the rule on" % shape, BLOCK,
                   'orca slack post "#g" "' + HAN + '"', on_home, str(repo),
                   "cjk")
            expect("bad repo value %r passes English" % shape, ALLOW,
                   'orca slack post "#g" "hi"', on_home, str(repo))

        expect("rule off (the default) passes", ALLOW,
               'orca slack post "#general" "' + HAN + '"', off_home, work)
        expect("rule off passes stdin", ALLOW,
               "orca slack post '#g' --text-file -", off_home, work)

    for name, payload in (("non-Bash tool",
                           json.dumps({"tool_name": "Read", "tool_input": {}})),
                          ("empty stdin", ""),
                          ("malformed stdin", "{not json")):
        got = subprocess.run([sys.executable, HOOK], input=payload,
                             capture_output=True, text=True).returncode
        if got != ALLOW:
            failures += 1
            print(f"FAIL want={ALLOW} got={got}  {name}")

    print("slack-language: all checks pass" if not failures
          else f"slack-language: {failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
