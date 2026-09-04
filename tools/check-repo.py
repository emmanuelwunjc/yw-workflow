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
import re
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

# 1c. The README describes the skills, and nothing checked that it still did.
# Adding two skills left it claiming seven in one place and nine in another, and
# gave one row a summary that differed from its own skill.
#
# The first version of this check searched the whole README for each one-liner.
# That is green when two rows swap summaries, when a row is deleted and its text
# survives in a code block, and when a row is missing entirely. It has to find
# the row BY NAME and compare that cell, which is why this parses the table.
wiring_for_readme = json.loads((ROOT / "hooks" / "hooks.json").read_text())
print("README agrees with the skills")
# fenced blocks are examples, not claims. Without this, deleting a row and
# leaving its text in a code sample reads as though the row is still there, and
# the guard's own module already knows how to strip them.
readme = guard.strip_fences((ROOT / "README.md").read_text())
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
n = len(skills)
right = {WORDS.get(n, str(n)), str(n)}
# digits count too: "7 skills" beside "Nine skills" is the same defect
# Every "<count> skills" in the README is treated as a claim about the total. A
# subset phrasing ("the two skills at the bottom") would false-positive, and an
# earlier version excluded a leading determiner to allow it. That also excluded
# "The seven skills", which is the drift this check exists for, so the exclusion
# cost more than it bought. Rephrase the README if the subset case ever arises.
stated = set(re.findall(r"\b([a-z]+|\d+)\s+skills\b", readme, re.IGNORECASE))
stated = {w.lower() for w in stated} & ({str(k) for k in WORDS} | set(WORDS.values()))
check("README states %d skills and no other count" % n,
      bool(stated & right) and not (stated - right),
      "found: " + ", ".join(sorted(stated)) if stated else "no count found")

# one row per skill in the Skills table, keyed by the bolded name in column one
# only the Skills section counts: a correct copy in a later table must not cover
# for a corrupted row in this one
check("README has a ## Skills section", "## Skills" in readme)
section = readme.split("## Skills", 1)[-1].split("\n## ", 1)[0]
found = re.findall(r"^\|\s*\*\*([a-z0-9-]+)\*\*\s*\|\s*(.+?)\s*\|\s*$",
                   section, re.MULTILINE)
check("no skill is listed twice in the Skills table",
      len(found) == len({n for n, _ in found}),
      "rows: " + ", ".join(n for n, _ in found))
rows = dict(found)
names = {s.parent.name for s in skills}
check("the Skills table has exactly one row per skill",
      set(rows) == names,
      "table only: %s | skills only: %s" % (sorted(set(rows) - names),
                                            sorted(names - set(rows))))
for skill in skills:
    name = skill.parent.name
    text = skill.read_text()
    marker = "**In one line:**"
    if marker not in text:
        check("%s has a one-line summary" % name, False)
        continue
    line = " ".join(text.split(marker, 1)[1].split("\n\n", 1)[0].split())
    check("README row for %s matches its skill" % name,
          " ".join(rows.get(name, "").split()) == line,
          "row: %s | skill: %s" % (rows.get(name, "<missing>"), line))

# 1c-ii. Same treatment for the hooks half of the README, which had none. The
# count and the table drift exactly the way the skills ones did.
wired = sorted({
    hook["command"].split("/")[-1].split()[0]
    for groups in wiring_for_readme["hooks"].values()
    for g in groups for hook in g.get("hooks", [])
})
hn = len(wired)
hright = {WORDS.get(hn, str(hn)), str(hn)}
hstated = {w.lower() for w in re.findall(r"\b([a-z]+|\d+)\s+hooks\b", readme,
                                         re.IGNORECASE)}
hstated &= ({str(k) for k in WORDS} | set(WORDS.values()))
check("README states %d hooks and no other count" % hn,
      bool(hstated & hright) and not (hstated - hright),
      "found: " + ", ".join(sorted(hstated)) if hstated else "no count found")
hook_rows = set(re.findall(r"^\|\s*\*\*([a-z0-9_.-]+)\*\*\s*\|", readme,
                           re.MULTILINE)) & {w for w in wired}
check("the Hooks table has a row for every wired hook",
      hook_rows == set(wired),
      "missing: " + ", ".join(sorted(set(wired) - hook_rows)))

# 1d. the marketplace description lists skill names by hand, which drifts the
# moment a skill is added. Same failure the README check above exists for.
market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
blurb = market["plugins"][0]["description"]
# tokenised, because a substring test lets "eli5-text" satisfy "eli5"
words = set(re.findall(r"[a-z0-9-]+", blurb.lower()))
missing = sorted(n for n in names if n not in words)
check("marketplace.json names every skill", not missing,
      "missing: " + ", ".join(missing))
# and the other direction: a name left in the blurb after its skill is gone, or
# one that was never a skill. A heuristic over loose words cannot tell a skill
# name from an English one, so the blurb states its list in a fixed shape and
# this parses it: everything between the colon and ", plus".
check("marketplace.json lists its skills after a colon and before ', plus'",
      ":" in blurb and ", plus" in blurb)
listed = blurb.split(":", 1)[-1].split(", plus", 1)[0]
listed = {w.strip() for part in listed.split(",") for w in part.split(" and ")}
listed = {w for w in listed if w}
check("marketplace.json names no skill that does not exist",
      listed <= names, "not skills: " + ", ".join(sorted(listed - names)))
blurb_counts = {w.lower() for w in re.findall(r"\b([a-z]+|\d+)\s+skills\b", blurb,
                                              re.IGNORECASE)}
blurb_counts &= ({str(k) for k in WORDS} | set(WORDS.values()))
check("marketplace.json states the right count, if it states one",
      not (blurb_counts - right), "found: " + ", ".join(sorted(blurb_counts)))

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
wiring = wiring_for_readme
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
