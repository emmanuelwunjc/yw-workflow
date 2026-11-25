#!/usr/bin/env python3
"""Add the general bot rules to one Orca bot's home.

  python3 setup.py <bot name>

What it writes, in ~/.orca/bots/<bot name>/:
  - SOUL.md: appends templates/soul-pointer.md once. Its first line is the
    marker. When SOUL.md holds the marker, it appends nothing.
  - memory/<file>: each file in templates/memory/, only when the bot has no
    file of that name.

It never writes AGENTS.md, CLAUDE.md, bot.json or MEMORY.md: Orca owns the
first three and replaces edits to them, and MEMORY.md changes only through
`orca bot memory`. A second run changes nothing.

It stops with one line, and writes nothing, when `orca` is not on PATH or the
bot home has no SOUL.md.

Self-test: test_setup.py beside this file.
"""
import shutil
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"


def stop(message):
    print("orca-bot setup: " + message, file=sys.stderr)
    sys.exit(1)


def main(argv):
    if len(argv) != 1:
        stop("give one bot name, e.g. `setup.py twenty`")
    name = argv[0]
    # the name becomes a path segment, so a name that leaves ~/.orca/bots stops
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        stop("%r is not a bot name" % name)
    if shutil.which("orca") is None:
        stop("no `orca` on PATH, so there is no Orca bot home to set up")
    home = Path.home() / ".orca" / "bots" / name
    soul = home / "SOUL.md"
    if not soul.is_file():
        stop("%s is missing: create the bot with `orca bot create` first" % soul)

    pointer = (TEMPLATES / "soul-pointer.md").read_text()
    marker = pointer.splitlines()[0]
    text = soul.read_text()
    if marker in text:
        print("kept      %s (it holds the marker)" % soul)
    else:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        soul.write_text(text + sep + pointer)
        print("appended  %s" % soul)

    memory = home / "memory"
    memory.mkdir(exist_ok=True)
    for src in sorted((TEMPLATES / "memory").glob("*.md")):
        dst = memory / src.name
        if dst.exists():
            print("kept      %s" % dst)
        else:
            dst.write_text(src.read_text())
            print("wrote     %s" % dst)


if __name__ == "__main__":
    main(sys.argv[1:])
