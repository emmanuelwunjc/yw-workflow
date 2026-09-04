#!/usr/bin/env python3
"""Repo checks that the four hook self-tests do not cover.

Runnable locally and in CI, deliberately the same command in both, so a green
result before pushing means the same thing as a green result on the PR.

  ./tools/check-repo.py

Checks, each one because something actually broke:
  1. The repo's own prose obeys the two writing rules its own guard enforces.
     Four real violations shipped into skill text before this existed.
  2. Manifests parse. A broken marketplace.json makes the plugin uninstallable
     and nothing else notices.
  3. Hook scripts are executable IN THE GIT INDEX. A hook that loses its exec
     bit fails silently at the exact moment it should block something.
  4. Every command in hooks.json resolves to a file that exists.
  5. The plugin version differs from the last tag's, if there is one, because
     `claude plugin update` keys off the version and a stale one is
     uninstallable in place.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
failures = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


# 1. the writing rules, enforced by the repo's own guard against its own prose
spec = importlib.util.spec_from_file_location(
    "guard", ROOT / "hooks" / "claude-md-guard.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

print("writing rules (the repo's own guard, on the repo's own prose)")
before = len(failures)
scanned = 0
# .worktrees holds full checkouts of other branches, so globbing into it
# double-counts and would judge a copy. Anything vendored gets skipped for the
# separate reason that these are this repo's writing rules, not a third party's.
SKIP = {".git", ".worktrees", "node_modules", "vendor", ".venv"}
# NOTICE and LICENSE carry prose too, and an extension-based glob misses them
extra = [ROOT / n for n in ("NOTICE", "LICENSE") if (ROOT / n).exists()]
for md in sorted(ROOT.glob("**/*.md")) + extra:
    # relative, because SKIP against md.parts also matches directories ABOVE
    # the repo: a checkout under any path containing "vendor" skipped everything
    if SKIP & set(md.relative_to(ROOT).parts):
        continue
    scanned += 1
    prose = guard.prose_only(md.read_text())
    rel = md.relative_to(ROOT)
    if guard.EM_DASH in prose:
        check("%s has no em-dash" % rel, False)
    hit = guard.find_negation(prose)
    if hit:
        check("%s has no negation-then-correction" % rel, False, hit[1])
check("found markdown files to scan", scanned > 0)
if len(failures) == before:
    print("  ok   %d markdown files clean" % scanned)

# 1b. the plugin's actual payload. Break a SKILL.md's frontmatter and the skill
# silently vanishes from the plugin, which is the likeliest real regression
# here, and nothing else looks at it. Parsed by hand rather than with pyyaml,
# which is not guaranteed on a runner.
print("skill frontmatter")
skills = sorted(ROOT.glob("skills/*/SKILL.md"))  # top level only, by design
dirs = sorted(d for d in (ROOT / "skills").iterdir() if d.is_dir())
check("skills/ is non-empty", bool(skills))
# a directory without a SKILL.md is a skill that silently left the plugin
check("every skills/ directory has a SKILL.md (%d dirs, %d files)"
      % (len(dirs), len(skills)), len(dirs) == len(skills))
for skill in skills:
    text = skill.read_text().replace("\r\n", "\n")
    # the fence has to be a whole line, or a horizontal rule in the body
    # re-anchors the block and an unterminated one parses as if it closed
    front = ""
    if text.startswith("---\n"):
        rest = text[4:]
        end = rest.find("\n---")
        front = rest[:end] if end != -1 else ""
    # A "---" in the body looks exactly like a terminator, so an unterminated
    # block parses as though it closed. What gives it away is content: a real
    # frontmatter block is key/value lines and nothing else, and a markdown
    # heading or paragraph swept in has no colon.
    stray = [ln for ln in front.splitlines()
             if ln.strip() and ":" not in ln and not ln.startswith((" ", "\t"))]
    check("%s frontmatter is terminated" % skill.parent.name, not stray,
          "swept in: " + repr(stray[:1]))
    keys = {}
    for line in front.splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # a folded or literal block whose body is gone leaves just the marker
        keys[key.strip()] = "" if value in (">", "|") else value
    want = skill.parent.name
    check("%s frontmatter name is %s" % (want, want), keys.get("name") == want,
          "got " + repr(keys.get("name")))
    check("%s has a description" % want, bool(keys.get("description")))

# 2. manifests parse
print("manifests")
for rel in (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json",
            "hooks/hooks.json"):
    try:
        json.loads((ROOT / rel).read_text())
        check(rel + " parses", True)
    except Exception as exc:  # noqa: BLE001 - report any parse failure the same way
        check(rel + " parses", False, str(exc))

# 3. the exec bit as git records it, which is what a fresh clone gets
print("hook permissions (git index, not the local filesystem)")
listing = subprocess.run(
    ["git", "ls-files", "-s", "hooks/"], cwd=ROOT, capture_output=True, text=True
).stdout.splitlines()
# an empty listing would make this whole section check nothing and say so by
# saying nothing, which is the failure this script exists to catch
check("git ls-files found hooks", bool(listing))
for line in listing:
    mode, _, rest = line.partition(" ")
    path = rest.split("\t", 1)[-1]
    if path.endswith((".py", ".sh")):
        check(path + " is executable", mode == "100755", "mode " + mode)

# 4. every wired command points at something real
print("hooks.json commands resolve")
wiring = json.loads((ROOT / "hooks" / "hooks.json").read_text())
for event, groups in wiring["hooks"].items():
    for group in groups:
        for hook in group.get("hooks", []):
            cmd = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")
            # a wired command may carry arguments ("... remind"), so only the
            # first token is the path
            script = cmd.split()[0]
            check("%s -> %s" % (event, cmd), (ROOT / script).exists())

# 5. a version that never moves is a plugin that never updates
print("plugin version")
version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
tag = subprocess.run(
    ["git", "describe", "--tags", "--abbrev=0"], cwd=ROOT,
    capture_output=True, text=True,
).stdout.strip()
def parts(v):
    return tuple(int(n) for n in v.split(".") if n.isdigit())


if tag:
    check("version %s is ahead of last tag %s" % (version, tag),
          parts(version) > parts(tag.lstrip("v")))
else:
    check("version is set (%s), no tag to compare" % version, bool(version))

print()
if failures:
    print("RESULT: %d failed" % len(failures))
    sys.exit(1)
print("RESULT: repo checks pass")
