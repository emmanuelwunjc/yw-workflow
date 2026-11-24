#!/usr/bin/env python3
"""At SessionStart, say when the installed plugin is older than its marketplace.

On 2026-11-24 the installed copy of yw-workflow was 16 versions behind the
repo, because nothing updates a third-party plugin by itself. The review gate
kept a bug that main had already fixed. This hook prints one line with the
two versions and the update command when the installed copy is behind.

The installed version is the one in this copy's own .claude-plugin/plugin.json.
The copy lives at <config>/plugins/cache/<marketplace>/<plugin>/<version>/, so
the folder names give the marketplace. known_marketplaces.json gives its local
clone. The latest version is the higher of the clone's work tree and the
clone's origin/HEAD.

The clone only moves when someone runs `claude plugin marketplace update`. So
the hook also starts `git fetch` in the clone, detached, and does not wait for
it. The fetch updates origin/HEAD for the next session. This session compares
against what the last fetch brought. The hook never touches the network
itself.

Prints nothing when the copy is current or newer, when it does not run from a
cache folder (e.g. `--plugin-dir`), and when any file it reads is missing or
broken. Always exits 0.

Self-test: ./hooks/plugin-lag-selftest.py
"""
import json
import os
import pathlib
import subprocess
import sys

MANIFEST = ".claude-plugin/plugin.json"
LINE = ("{plugin} plugin is behind: installed {installed}, latest {latest}. "
        "To update, run `claude plugin marketplace update {mkt} && "
        "claude plugin update {plugin}@{mkt}`, then restart Claude Code.")


def parts(version):
    return tuple(int(p) for p in version.split("."))


def git(clone, *args):
    out = subprocess.run(["git", "-C", str(clone), *args], capture_output=True,
                         text=True, timeout=5, stdin=subprocess.DEVNULL)
    return out.stdout if out.returncode == 0 else ""


def fetch_later(clone):
    """Start a fetch that outlives this hook. Every stream goes to /dev/null, so
    the harness does not wait on a pipe the fetch holds open."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    subprocess.Popen(["git", "-C", str(clone), "fetch", "--quiet", "origin"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=env)


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    manifest = json.loads((root / MANIFEST).read_text())
    plugin, installed = manifest["name"], manifest["version"]
    mkt = root.parent.parent.name
    config = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR")
                          or pathlib.Path.home() / ".claude").resolve()
    if root.parent.parent.parent != config / "plugins" / "cache":
        return
    known = json.loads((config / "plugins" / "known_marketplaces.json").read_text())
    clone = pathlib.Path(known[mkt]["installLocation"])
    latest = [json.loads((clone / MANIFEST).read_text())["version"]]
    remote = git(clone, "show", "origin/HEAD:" + MANIFEST)
    if remote:
        latest.append(json.loads(remote)["version"])
    fetch_later(clone)
    newest = max(latest, key=parts)
    if parts(newest) > parts(installed):
        print(LINE.format(plugin=plugin, installed=installed, latest=newest, mkt=mkt))


if __name__ == "__main__":
    try:
        sys.stdin.read()
        main()
    except Exception:  # noqa: BLE001 - a version check must never break session start
        pass
    sys.exit(0)
