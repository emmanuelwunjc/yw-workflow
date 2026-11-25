#!/usr/bin/env python3
"""Offline self-check of setup.py, the orca-bot setup step.

Runs setup.py against a temp home with a fake `orca` on PATH, so it needs no
Orca install. CI runs it through hooks/orca-bot-selftest.py.

Run: python3 skills/orca-bot/test_setup.py
"""
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SETUP = HERE / "setup.py"
MEMORY_FILES = ("feedback-delegate-fixes.md", "feedback-tell-agent-not-owner.md")
ORCA_OWNED = ("AGENTS.md", "CLAUDE.md", "bot.json", "MEMORY.md")
failures = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


def make_world(tmp, with_orca=True, with_soul=True):
    """A temp home with one bot, `demo`, laid out as Orca lays one out."""
    home = tmp / "home"
    bot = home / ".orca" / "bots" / "demo"
    (bot / "memory").mkdir(parents=True)
    for name in ORCA_OWNED:
        (bot / name).write_text("orca wrote %s\n" % name)
    if with_soul:
        (bot / "SOUL.md").write_text("# Demo\n\nRuns the demo repo.\n")
    bindir = tmp / "bin"
    bindir.mkdir()
    if with_orca:
        fake = bindir / "orca"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
    return home, bot, bindir


def run(home, bindir, *args):
    env = {"HOME": str(home), "PATH": str(bindir)}
    return subprocess.run([sys.executable, str(SETUP), *args],
                          env=env, capture_output=True, text=True)


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def one_line(r):
    out = (r.stdout + r.stderr).strip()
    return bool(out) and "\n" not in out


with tempfile.TemporaryDirectory() as d:
    print("stops with one line when orca is missing")
    home, bot, bindir = make_world(pathlib.Path(d), with_orca=False)
    before = snapshot(home / ".orca")
    r = run(home, bindir, "demo")
    check("exit is not 0", r.returncode != 0)
    check("one line of output", one_line(r), repr(r.stdout + r.stderr))
    check("names orca", "orca" in (r.stdout + r.stderr))
    check("nothing changed", snapshot(home / ".orca") == before)

with tempfile.TemporaryDirectory() as d:
    print("stops with one line when SOUL.md is missing")
    home, bot, bindir = make_world(pathlib.Path(d), with_soul=False)
    before = snapshot(home / ".orca")
    r = run(home, bindir, "demo")
    check("exit is not 0", r.returncode != 0)
    check("one line of output", one_line(r), repr(r.stdout + r.stderr))
    check("names SOUL.md", "SOUL.md" in (r.stdout + r.stderr))
    check("nothing changed", snapshot(home / ".orca") == before)
    r = run(home, bindir, "nobody")
    check("an unknown bot stops too", r.returncode != 0 and one_line(r))

with tempfile.TemporaryDirectory() as d:
    print("refuses a name that leaves ~/.orca/bots")
    home, bot, bindir = make_world(pathlib.Path(d))
    # a SOUL.md where each bad name points, so a name fails only by the guard
    for decoy in ("SOUL.md", "bots/SOUL.md", "demo/SOUL.md"):
        (home / ".orca" / decoy).parent.mkdir(parents=True, exist_ok=True)
        (home / ".orca" / decoy).write_text("# decoy\n")
    before = snapshot(home / ".orca")
    for bad in ("../demo", "demo/../demo", "", ".", ".."):
        r = run(home, bindir, bad)
        check("refuses %r" % bad, r.returncode != 0 and one_line(r))
    r = run(home, bindir)
    check("refuses no name", r.returncode != 0)
    check("nothing changed", snapshot(home / ".orca") == before)

with tempfile.TemporaryDirectory() as d:
    print("writes the pointer block and the memory files")
    home, bot, bindir = make_world(pathlib.Path(d))
    owned = {n: (bot / n).read_bytes() for n in ORCA_OWNED}
    soul_before = (bot / "SOUL.md").read_text()
    r = run(home, bindir, "demo")
    check("exit is 0", r.returncode == 0, r.stdout + r.stderr)
    soul = (bot / "SOUL.md").read_text()
    check("SOUL.md keeps its old text first", soul.startswith(soul_before))
    marker = (HERE / "templates" / "soul-pointer.md").read_text().splitlines()[0]
    check("the marker line is a comment that names the skill",
          marker.startswith("<!--") and "orca-bot" in marker)
    check("SOUL.md holds the marker once", soul.count(marker) == 1)
    check("SOUL.md names the skill", "yw-workflow:orca-bot" in soul)
    for name in MEMORY_FILES:
        f = bot / "memory" / name
        check("wrote memory/%s" % name,
              f.exists() and f.read_text() == (HERE / "templates" / "memory" / name).read_text())
    check("AGENTS.md, CLAUDE.md, bot.json, MEMORY.md unchanged",
          all((bot / n).read_bytes() == b for n, b in owned.items()))
    check("wrote nothing else in the bot home",
          set(snapshot(bot)) == {*ORCA_OWNED, "SOUL.md", *("memory/" + n for n in MEMORY_FILES)})

    print("a second run changes nothing")
    before = snapshot(home / ".orca")
    r = run(home, bindir, "demo")
    check("exit is 0", r.returncode == 0, r.stdout + r.stderr)
    check("nothing changed", snapshot(home / ".orca") == before)

with tempfile.TemporaryDirectory() as d:
    print("keeps a memory file the bot already has")
    home, bot, bindir = make_world(pathlib.Path(d))
    mine = bot / "memory" / MEMORY_FILES[0]
    mine.write_text("the bot's own words\n")
    r = run(home, bindir, "demo")
    check("exit is 0", r.returncode == 0, r.stdout + r.stderr)
    check("left it alone", mine.read_text() == "the bot's own words\n")
    check("wrote the other one", (bot / "memory" / MEMORY_FILES[1]).exists())

with tempfile.TemporaryDirectory() as d:
    print("makes memory/ when the bot home has none")
    home, bot, bindir = make_world(pathlib.Path(d))
    (bot / "memory").rmdir()
    r = run(home, bindir, "demo")
    check("exit is 0", r.returncode == 0, r.stdout + r.stderr)
    check("wrote both memory files",
          all((bot / "memory" / n).exists() for n in MEMORY_FILES))

with tempfile.TemporaryDirectory() as d:
    print("stops with one line when memory is a plain file")
    home, bot, bindir = make_world(pathlib.Path(d))
    (bot / "memory").rmdir()
    (bot / "memory").write_text("not a folder\n")
    before = snapshot(home / ".orca")
    r = run(home, bindir, "demo")
    check("exit is not 0", r.returncode != 0)
    check("one line of output", one_line(r), repr(r.stdout + r.stderr))
    check("names memory", "memory" in (r.stdout + r.stderr))
    check("nothing changed, SOUL.md too", snapshot(home / ".orca") == before)

with tempfile.TemporaryDirectory() as d:
    print("keeps a dangling symlink at a memory file name")
    home, bot, bindir = make_world(pathlib.Path(d))
    link = bot / "memory" / MEMORY_FILES[0]
    target = bot / "gone.md"
    link.symlink_to(target)
    r = run(home, bindir, "demo")
    check("exit is 0", r.returncode == 0, r.stdout + r.stderr)
    check("did not write through the link", not target.exists())
    check("the link is still a link", link.is_symlink())

print("SKILL.md names a source date for each rule")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
skill = (HERE / "SKILL.md").read_text()
rules = skill.split("\n## The rules\n", 1)[-1]
sections = re.split(r"\n(?=### )", rules)[1:]
check("SKILL.md has rule sections", len(sections) >= 4, str(len(sections)))
for sec in sections:
    title = sec.splitlines()[0]
    check("%s names a date" % title, bool(DATE.search(sec)))
    for bullet in re.findall(r"^- \*\*.*?(?=^- |\Z)", sec, re.M | re.S):
        check("%s: %s names a date" % (title, bullet.split("**")[1]),
              bool(DATE.search(bullet)))

print("RESULT: " + ("FAIL: " + ", ".join(failures) if failures else "orca-bot setup checks pass"))
sys.exit(1 if failures else 0)
