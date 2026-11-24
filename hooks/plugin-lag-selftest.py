#!/usr/bin/env python3
"""Self-test for plugin-lag.py. Run it after any edit to that hook.

Builds a fake Claude config folder (CLAUDE_CONFIG_DIR) that holds an installed
copy of the plugin at plugins/cache/<marketplace>/<plugin>/<version>/, a
known_marketplaces.json, and a marketplace clone of a bare "origin" repo. Each
case runs the installed copy of the hook and compares its stdout.

Cases: installed equals the clone (silent), the clone is newer by a two-digit
part (1.9.9 against 1.9.10, so the compare is numeric), origin/HEAD is newer
than the clone's work tree, installed is newer than the clone (silent), the
hook run from outside a cache folder (silent), a missing or broken
known_marketplaces.json, a missing clone, a broken plugin.json (all silent,
exit 0). The background fetch: it updates origin/HEAD for the next session,
and a fetch that hangs does not hold the hook open.

Run: ./hooks/plugin-lag-selftest.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = pathlib.Path(__file__).with_name("plugin-lag.py")
GIT = shutil.which("git")
MKT, PLUGIN = "mkt", "plug"
failures = []


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def write_version(repo, version):
    p = pathlib.Path(repo, ".claude-plugin", "plugin.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"name": PLUGIN, "version": version}))


def commit_version(repo, version):
    write_version(repo, version)
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", version)


def install(config, version, layout=True):
    """An installed copy of the hook, in a cache folder or (layout=False) not."""
    root = (pathlib.Path(config, "plugins", "cache", MKT, PLUGIN, version) if layout
            else pathlib.Path(config, "loose", PLUGIN))
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK, root / "hooks" / HOOK.name)
    write_version(root, version)
    return root / "hooks" / HOOK.name


def known(config, clone):
    p = pathlib.Path(config, "plugins", "known_marketplaces.json")
    p.write_text(json.dumps({MKT: {"installLocation": str(clone)}}))
    return p


def run(config, hook, path=None):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config))
    if path:
        env["PATH"] = path
    start = time.time()
    out = subprocess.run([sys.executable, str(hook)], input="{}", env=env,
                         capture_output=True, text=True, timeout=30)
    return out.returncode, out.stdout.strip(), time.time() - start


def expect(name, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print("       want: %r\n       got:  %r" % (want, got))
        failures.append(name)


def behind(installed, latest):
    return ("%s plugin is behind: installed %s, latest %s. To update, run "
            "`claude plugin marketplace update %s && claude plugin update %s@%s`, "
            "then restart Claude Code." % (PLUGIN, installed, latest, MKT, PLUGIN, MKT))


def setup(root):
    """A bare origin at 1.9.10, a clone of it, and a fake config folder."""
    origin = os.path.join(root, "origin.git")
    sh(root, "git", "init", "-q", "--bare", "-b", "main", origin)
    work = os.path.join(root, "work")
    sh(root, "git", "clone", "-q", origin, work)
    commit_version(work, "1.9.10")
    sh(work, "git", "push", "-q", "origin", "HEAD:main")
    config = pathlib.Path(root, "config")
    clone = config / "plugins" / "marketplaces" / MKT
    clone.parent.mkdir(parents=True)
    sh(root, "git", "clone", "-q", origin, str(clone))
    known(config, clone)
    return work, config, clone


def main():
    root = tempfile.mkdtemp()
    try:
        work, config, clone = setup(root)

        expect("installed equals the clone: silent",
               run(config, install(config, "1.9.10"))[:2], (0, ""))
        expect("clone newer, numeric compare (1.9.9 < 1.9.10)",
               run(config, install(config, "1.9.9"))[:2], (0, behind("1.9.9", "1.9.10")))
        expect("installed newer than the clone: silent",
               run(config, install(config, "1.11.0"))[:2], (0, ""))
        expect("outside a cache folder: silent",
               run(config, install(config, "1.0.0", layout=False))[:2], (0, ""))

        # origin moves on. The clone's work tree stays at 1.9.10.
        commit_version(work, "1.10.0")
        sh(work, "git", "push", "-q", "origin", "HEAD:main")
        new = sh(work, "git", "rev-parse", "HEAD")
        hook = install(config, "1.9.10")
        run(config, hook)  # starts the background fetch
        for _ in range(100):
            if sh(str(clone), "git", "rev-parse", "origin/main") == new:
                break
            time.sleep(0.1)
        expect("the background fetch updates origin/main",
               sh(str(clone), "git", "rev-parse", "origin/main"), new)
        expect("origin/HEAD newer than the clone's work tree",
               run(config, hook)[:2], (0, behind("1.9.10", "1.10.0")))

        # a fetch that hangs must not hold the hook (or its stdout) open
        bindir = pathlib.Path(root, "bin")
        bindir.mkdir()
        (bindir / "git").write_text(
            '#!/bin/sh\nfor a in "$@"; do [ "$a" = fetch ] && exec sleep 20; done\n'
            'exec %s "$@"\n' % GIT)
        (bindir / "git").chmod(0o755)
        code, out, took = run(config, hook, "%s:%s" % (bindir, os.environ["PATH"]))
        expect("a hanging fetch does not hold the hook open",
               (code, out, took < 10), (0, behind("1.9.10", "1.10.0"), True))

        broken = known(config, clone)
        broken.write_text("{not json")
        expect("broken known_marketplaces.json: silent", run(config, hook)[:2], (0, ""))
        broken.unlink()
        expect("missing known_marketplaces.json: silent", run(config, hook)[:2], (0, ""))
        known(config, pathlib.Path(root, "nowhere"))
        expect("missing clone: silent", run(config, hook)[:2], (0, ""))
        known(config, clone)
        hook.parent.parent.joinpath(".claude-plugin", "plugin.json").write_text("{")
        expect("broken installed plugin.json: silent", run(config, hook)[:2], (0, ""))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if failures:
        print("%d failed" % len(failures))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
