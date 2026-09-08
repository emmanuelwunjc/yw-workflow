#!/usr/bin/env python3
"""Effective policy for the guards: what is on, and what values it uses.

Every guard reads this instead of hardcoding a rule's existence or its
thresholds. Without it the package enforces one person's taste with no way to
disagree short of forking, which is what stopped it being usable by a team.

RESOLUTION

  user config   ~/.handrail.toml        the machine's owner
  repo config   <repo root>/.handrail.toml   the team, found by walking up

Both are optional. With neither, DEFAULTS apply: every rule on except
negation-then-correction, which is the one heuristic with known false positives
and is opt-in for that reason.

THE RATCHET

A repo config may switch a rule ON. Only the user config may switch one OFF. A
repo you clone can therefore make you stricter and never laxer, so a careless or
hostile repo cannot strip the guards off your machine by being cloned.

Thresholds are deliberately outside the ratchet: a repo sets them freely,
because a monorepo full of generated files has a real reason to move the review
threshold. So the honest claim is "a repo cannot switch a guard off", never "a
repo cannot weaken your guards". Documented that way on purpose.

CI

load(ci=True) ignores on/off entirely and returns CI_FLOOR, because a required
check a repo can switch off is not a required check. Negation is the exception:
it runs in CI only when a repo asks for it, and asking is one-way.

NOT WIRED YET. The action does not read this module, so today `scan` runs the
negation heuristic unconditionally in CI, which is the opposite of what
CI_OPT_IN describes. Wiring it is the next unit of this change. Until then treat
CI_FLOOR as the intended contract rather than the shipped one.

FORMAT

TOML, falling back to JSON where tomllib is missing (Python before 3.11). With
both files present the effective policy is ambiguous, so a session warns and
reads the TOML while CI fails the job. That mirrors the split the guards already
use: a crash fails open in a session and closed in CI.
"""
import json
import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

# Every rule the package can run, and whether a fresh install runs it.
DEFAULTS = {
    "em_dash": True,
    "negation": False,
    "ask_user_question": True,
    "handoff_freshness": True,
    "ai_attribution": True,
    "require_review": True,
    "git_safety": True,
}

# What the CI action enforces no matter what a repo's config says. Two rules are
# absent because they cannot run server-side rather than by choice:
# ask_user_question needs a live turn to inspect, and git_safety blocks a git
# command as it is typed, which branch protection covers in CI.
CI_FLOOR = ("em_dash", "ai_attribution", "require_review", "handoff_freshness")

# Rules a repo may add to the CI floor. Enabling is one-way: CI ignores a later
# attempt to switch one back off, same as the local ratchet.
CI_OPT_IN = ("negation",)

VALUE_DEFAULTS = {
    "git_safety": {
        "protected": ["main", "master"],
        # A tool that wraps git runs it as a subprocess, and every rule keyed on
        # the literal string "git " stops applying. Naming the wrappers here is
        # what keeps the hole closed when a team adopts one.
        "wrappers": [],
    },
    "handoff": {"path": "docs/HANDOFF.md"},
    "require_review": {
        "trivial_lines": 25,
        "code_suffixes": [".py", ".yml", ".yaml", ".toml", ".cfg", ".sh", ".ts", ".js"],
        "verdict_markers": [],
    },
}

BASENAMES = (".handrail.toml", ".handrail.json")


class AmbiguousConfig(Exception):
    """Both a TOML and a JSON config exist in one directory."""

    def __init__(self, directory):
        self.directory = directory
        super().__init__(
            "two config files in %s: .handrail.toml and .handrail.json. "
            "Delete one, because the effective policy is ambiguous." % directory
        )


def _parse(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    if tomllib is None:
        raise RuntimeError(
            "%s needs tomllib (Python 3.11+). Rename it to .handrail.json, "
            "or run the guards on a newer Python." % path
        )
    return tomllib.loads(text)


def _read_dir(directory, strict):
    """Parse the config in one directory, or None when there is none.

    strict is the CI/session split: ambiguity raises for CI and picks the TOML
    for a session, because a config mistake must never wedge a live session.
    """
    present = [directory / name for name in BASENAMES if (directory / name).is_file()]
    if not present:
        return None
    if len(present) > 1:
        if strict:
            raise AmbiguousConfig(directory)
        sys.stderr.write(
            "handrail: two config files in %s, reading .handrail.toml and "
            "ignoring .handrail.json\n" % directory
        )
    return _parse(present[0])


def _repo_root(start):
    """Nearest ancestor holding a config, else the git root, else None.

    Walking to a config first means a subdirectory can carry its own policy in a
    monorepo without every package needing a .git.
    """
    try:
        start = Path(start).resolve()
    except OSError:  # a deleted cwd still has to yield defaults, not a crash
        return None
    ancestors = (start, *start.parents)
    # The search for a config is BOUNDED by the INNERMOST ancestor whose .git is
    # a DIRECTORY, which is the repo you are actually in. Both halves matter:
    #
    #   outermost, as the first attempt used, walks past the repo into whatever
    #   contains it, so a config in a shared parent governs every checkout below.
    #   .exists(), as the first attempt used, accepts a zero-byte file, so
    #   `touch /tmp/.git` next to a hostile config restores that reach. /tmp is
    #   world-writable, so any local process could then pick the policy doc
    #   quoted at the model. That is the whole blast radius TODAY, because
    #   nothing in production reads values yet. It becomes thresholds and
    #   protected branch names the moment the unit that wires them lands, which
    #   is why this is bounded now rather than then.
    #
    # A submodule and a worktree both use a .git FILE, so bounding on a
    # directory keeps a nested checkout from shadowing the superproject's
    # config, which is what this bound was introduced for. With no git anywhere,
    # only the cwd is trusted.
    git = [i for i, directory in enumerate(ancestors)
           if (directory / ".git").is_dir()]
    bound = (min(git) + 1) if git else 1
    for directory in ancestors[:bound]:
        if any((directory / name).is_file() for name in BASENAMES):
            return directory
    # No config: the git root is still the right base for resolving a policy doc.
    return ancestors[min(git)] if git else None


class Config:
    def __init__(self, rules, values, policy_doc, root):
        self._rules = rules
        self._values = values
        self._policy_doc = policy_doc
        self.root = root

    def enabled(self, rule):
        # An unknown name is off. A typo in a config must not silently arm
        # something, and every real rule is present in DEFAULTS.
        return self._rules.get(rule, False)

    def value(self, section, key):
        return self._values[section][key]

    def citation(self):
        """A sentence pointing at the team's policy, or "" when there is none.

        A citation naming a file the reader does not have is worse than no
        citation, so an unset or missing policy_doc yields nothing and the
        message stands on its own.
        """
        return "See %s." % self._policy_doc if self._policy_doc else ""


def load(cwd=None, ci=False):
    """Effective config for this run.

    Raises on a malformed file, an unreadable one, or a config whose shape is
    wrong. Callers are what make that safe: every guard treats a failure to load
    as "enforce the defaults, cite nothing", so a broken config keeps the guards
    armed rather than disarming them.
    """
    cwd = Path(cwd or os.getcwd())
    user = _read_dir(Path.home(), strict=ci) or {}
    root = _repo_root(cwd)
    repo = (_read_dir(root, strict=ci) or {}) if root else {}

    rules = dict(DEFAULTS)
    rules.update({k: bool(v) for k, v in (user.get("rules") or {}).items()
                  if k in DEFAULTS})
    for name, on in (repo.get("rules") or {}).items():
        # The ratchet: a repo may enable, never disable.
        if name in DEFAULTS and on:
            rules[name] = True

    if ci:
        repo_rules = repo.get("rules") or {}
        rules = {name: (name in CI_FLOOR
                        or (name in CI_OPT_IN and bool(repo_rules.get(name))))
                 for name in DEFAULTS}

    values = {section: dict(defaults)
              for section, defaults in VALUE_DEFAULTS.items()}
    for source in (user, repo):
        for section, defaults in VALUE_DEFAULTS.items():
            for key, val in (source.get(section) or {}).items():
                if key in defaults:
                    values[section][key] = val

    doc, base = repo.get("policy_doc"), root
    if not doc:
        # A user-level policy doc is a file on that user's machine, so it
        # resolves against home. Resolving it against the current repo would
        # cite it only in repos that happen to carry the same filename.
        doc, base = user.get("policy_doc"), Path.home()
    if doc and (".." in Path(doc).parts or Path(doc).is_absolute()):
        doc = None  # a policy doc names a file in the tree, never one above it
    if doc and not (base and (base / doc).is_file()):
        if ci:
            sys.stderr.write("handrail: policy_doc %r cannot be resolved, so "
                             "messages will not cite it\n" % doc)
        doc = None
    return Config(rules, values, doc, root)
