#!/usr/bin/env python3
"""Self-test for the effective-policy resolution in hooks/config.py.

Each case is one decision the config exists to implement, so a case failing
names the decision that broke rather than a line number.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("handrail_config", HOOKS / "config.py")
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

failures = []
cases = 0


def check(name, got, want):
    global cases
    cases += 1
    if got != want:
        failures.append("FAIL %s: want %r, got %r" % (name, want, got))


def write(directory, name, body):
    (directory / name).write_text(body, encoding="utf-8")


def load(home, repo, ci=False):
    """Resolve with HOME pointed at a fixture, since Path.home() reads it.

    Warnings are captured so a passing run prints only its own result line.
    Several cases exist precisely to provoke one.
    """
    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    stderr, sys.stderr = sys.stderr, io.StringIO()
    try:
        return cfg.load(cwd=repo, ci=ci)
    finally:
        sys.stderr = stderr
        if previous is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = previous


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    home, repo = tmp / "home", tmp / "repo"
    home.mkdir()
    repo.mkdir()
    # A marker so _repo_root stops here rather than walking into the real repo
    # this test runs inside, which would read that repo's config.
    (repo / ".git").mkdir()

    # --- defaults -------------------------------------------------------
    c = load(home, repo)
    check("default: em_dash on", c.enabled("em_dash"), True)
    check("default: negation off", c.enabled("negation"), False)
    check("default: require_review on", c.enabled("require_review"), True)
    check("default: trivial_lines is 25",
          c.value("require_review", "trivial_lines"), 25)
    check("default: no citation without a policy doc", c.citation(), "")

    # --- the ratchet ----------------------------------------------------
    write(repo, ".handrail.toml", "[rules]\nem_dash = false\nnegation = true\n")
    c = load(home, repo)
    check("ratchet: a repo cannot switch a rule off", c.enabled("em_dash"), True)
    check("ratchet: a repo can switch a rule on", c.enabled("negation"), True)

    write(home, ".handrail.toml", "[rules]\nem_dash = false\n")
    c = load(home, repo)
    check("ratchet: the user config can switch a rule off",
          c.enabled("em_dash"), False)
    (home / ".handrail.toml").unlink()

    # --- thresholds sit outside the ratchet -----------------------------
    write(repo, ".handrail.toml",
          "[require_review]\ntrivial_lines = 100000\n")
    c = load(home, repo)
    check("thresholds: a repo may loosen one",
          c.value("require_review", "trivial_lines"), 100000)

    write(repo, ".handrail.toml", "[git_safety]\nprotected = [\"trunk\"]\n")
    c = load(home, repo)
    check("values: a repo may name its own protected branches",
          c.value("git_safety", "protected"), ["trunk"])
    check("values: an unset key keeps its default",
          c.value("handoff", "path"), "docs/HANDOFF.md")

    # --- the policy doc -------------------------------------------------
    write(repo, ".handrail.toml", 'policy_doc = "ENGINEERING.md"\n')
    c = load(home, repo)
    check("policy doc: configured but missing is not cited", c.citation(), "")
    write(repo, "ENGINEERING.md", "the team's rules\n")
    c = load(home, repo)
    check("policy doc: cited once the file exists",
          c.citation(), "See ENGINEERING.md.")

    # --- CI ignores on/off ----------------------------------------------
    write(repo, ".handrail.toml",
          "[rules]\nem_dash = false\nrequire_review = false\n"
          "[require_review]\ntrivial_lines = 10\n")
    c = load(home, repo, ci=True)
    check("CI: the floor ignores a repo switching a rule off",
          c.enabled("em_dash"), True)
    check("CI: the floor covers require_review", c.enabled("require_review"), True)
    check("CI: negation stays off unless a repo asks", c.enabled("negation"), False)
    check("CI: a rule that cannot run server-side is off",
          c.enabled("ask_user_question"), False)
    check("CI: values are still honored",
          c.value("require_review", "trivial_lines"), 10)

    write(repo, ".handrail.toml", "[rules]\nnegation = true\n")
    c = load(home, repo, ci=True)
    check("CI: a repo can opt into negation", c.enabled("negation"), True)

    # A user config must not be able to lift a rule out of the CI floor, or the
    # required check would depend on whose laptop happened to run it.
    write(home, ".handrail.toml", "[rules]\nem_dash = false\n")
    c = load(home, repo, ci=True)
    check("CI: a user config cannot open the floor", c.enabled("em_dash"), True)
    (home / ".handrail.toml").unlink()

    # --- both formats present -------------------------------------------
    write(repo, ".handrail.json", '{"rules": {"negation": true}}')
    c = load(home, repo)
    check("both present: a session reads the TOML and keeps working",
          c.enabled("negation"), True)
    cases += 1
    try:
        load(home, repo, ci=True)
        failures.append("FAIL both present: CI accepted an ambiguous config")
    except cfg.AmbiguousConfig:
        pass
    (repo / ".handrail.json").unlink()

    # --- a subdirectory finds the repo's config -------------------------
    nested = repo / "packages" / "api"
    nested.mkdir(parents=True)
    write(repo, ".handrail.toml", "[rules]\nnegation = true\n")
    c = load(home, nested)
    check("resolution: a subdirectory reads the repo's config",
          c.enabled("negation"), True)

# --- the guards actually read it ------------------------------------------
# Resolution being right proves nothing about whether a guard consults it. Each
# case here runs the guard as a subprocess with HOME and cwd pointed at fixtures.
BLOCK, ALLOW = 2, 0


def guard(script, payload, home, cwd):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(HOOKS / script)], input=payload,
                          capture_output=True, text=True, timeout=20,
                          cwd=str(cwd), env=env)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    home, repo = tmp / "home", tmp / "repo"
    home.mkdir()
    repo.mkdir()
    (repo / ".git").mkdir()

    publish = json.dumps({"tool_name": "Bash", "tool_input": {
        "command": 'gh pr create --body "Generated with Claude Code"'}})

    got = guard("no-ai-attribution.py", publish, home, repo)
    check("wiring: the attribution guard blocks by default",
          got.returncode, BLOCK)
    cases += 1
    if "Yiming" in got.stderr:
        failures.append("FAIL wiring: the block message names a person")

    (home / ".handrail.toml").write_text("[rules]\nai_attribution = false\n")
    check("wiring: the user config switches the guard off",
          guard("no-ai-attribution.py", publish, home, repo).returncode, ALLOW)

    # The ratchet again, this time through the guard rather than the resolver.
    (repo / ".handrail.toml").write_text("[rules]\nai_attribution = true\n")
    check("wiring: a repo can switch it back on over the user's off",
          guard("no-ai-attribution.py", publish, home, repo).returncode, BLOCK)
    (home / ".handrail.toml").unlink()

    # A config that cannot be parsed must leave the guard armed. Failing to
    # read the policy is a reason to keep guarding, and a guard that disarms on
    # a syntax error is one broken keystroke away from enforcing nothing.
    (repo / ".handrail.toml").write_text("[rules\nthis is not toml\n")
    check("wiring: a malformed config leaves the guard armed",
          guard("no-ai-attribution.py", publish, home, repo).returncode, BLOCK)

    (repo / ".handrail.toml").write_text('policy_doc = "TEAM.md"\n')
    (repo / "TEAM.md").write_text("rules\n")
    got = guard("no-ai-attribution.py", publish, home, repo)
    cases += 1
    if "See TEAM.md." not in got.stderr:
        failures.append("FAIL wiring: a configured policy doc is not cited, got: "
                        + got.stderr.strip()[:120])

if failures:
    print("\n".join(failures))
    print("\nRESULT: %d failed of %d cases" % (len(failures), cases))
    sys.exit(1)
print("config: %d cases pass" % cases)
