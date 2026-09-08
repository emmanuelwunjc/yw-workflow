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
spec = importlib.util.spec_from_file_location("handrail_config", HOOKS / "handrail_config.py")
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

    # Outside any repo there is nothing to resolve a policy_doc against, so the
    # existence check has to run rather than being skipped along with the root.
    # Every hook invocation outside a repo takes this path.
    loose = tmp / "loose"
    loose.mkdir()
    write(home, ".handrail.toml", 'policy_doc = "NOWHERE.md"\n')
    c = load(home, loose)
    check("no repo root: a policy doc that cannot be resolved is not cited",
          c.citation(), "")
    (home / ".handrail.toml").unlink()

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
    # The two files must DISAGREE, or the case passes whichever one is read and
    # reversing the lookup order goes unnoticed.
    write(repo, ".handrail.toml", "[rules]\nnegation = true\n")
    write(repo, ".handrail.json", '{"rules": {"em_dash": true}, '
                                  '"policy_doc": "FROM-JSON.md"}')
    write(repo, "FROM-JSON.md", "would be cited if the JSON won\n")
    c = load(home, repo)
    check("both present: a session reads the TOML and keeps working",
          c.enabled("negation"), True)
    check("both present: the JSON is ignored, not merged", c.citation(), "")
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

    # A submodule or a vendored checkout puts a .git between the cwd and the
    # repo's config. Stopping at it silently drops the team's opt-in, so the
    # walk looks for a config across every ancestor before falling back to git.
    (nested / ".git").write_text("gitdir: ../../.git/modules/api\n")
    c = load(home, nested)
    check("resolution: a nested .git does not shadow the repo's config",
          c.enabled("negation"), True)

# --- the guards actually read it ------------------------------------------
# Resolution being right proves nothing about whether a guard consults it. Each
# case here runs the guard as a subprocess with HOME and cwd pointed at fixtures.
BLOCK, ALLOW = 2, 0


def guard(script, payload, home, cwd, *args):
    """Run a guard with HOME and cwd pointed at fixtures.

    args carries the mode. Omitting it on a guard that needs one exits 0 with no
    output, which reads exactly like "did not block" and is how these cases
    first passed for the wrong reason.
    """
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(HOOKS / script), *args],
                          input=payload, capture_output=True, text=True,
                          timeout=20, cwd=str(cwd), env=env)


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

    # --- the prose guard reads it too -----------------------------------
    # Resolution and one guard are not the wiring. Every mutation to
    # claude-md-guard.py's gates survived until these existed.
    transcript = repo / "t.jsonl"
    transcript.write_text(
        '{"message": {"role": "user", "content": "go"}}\n'
        '{"message": {"role": "assistant", "content": [{"type": "text", '
        '"text": "This sentence has an em dash \u2014 right here."}]}}\n')
    turn = [0]

    def blocked(home_dir):
        """True when the Stop hook asked for a rewrite.

        Each call gets its own session id. The guard spends a per-session block
        budget, so reusing one id makes the third case pass for having run out
        of budget rather than for reading the config.
        """
        turn[0] += 1
        stop = json.dumps({"transcript_path": str(transcript),
                           "session_id": "cfg-%d" % turn[0]})
        out = guard("claude-md-guard.py", stop, home_dir, repo, "check").stdout
        return '"decision": "block"' in out or '"decision":"block"' in out

    (repo / ".handrail.toml").write_text("")
    check("wiring: the prose guard blocks an em-dash by default",
          blocked(home), True)

    (home / ".handrail.toml").write_text("[rules]\nem_dash = false\n")
    check("wiring: the user config switches the prose rule off",
          blocked(home), False)

    (repo / ".handrail.toml").write_text("[rules]\nem_dash = true\n")
    check("wiring: a repo switches the prose rule back on",
          blocked(home), True)
    (home / ".handrail.toml").unlink()

    (repo / ".handrail.toml").write_text("[rules\nnot toml\n")
    check("wiring: a malformed config leaves the prose guard armed",
          blocked(home), True)

    # negation is the one rule off by default, so its gate has to be checked in
    # the other direction: silent until asked for, then loud.
    negation_turn = repo / "n.jsonl"
    negation_turn.write_text(
        '{"message": {"role": "user", "content": "go"}}\n'
        '{"message": {"role": "assistant", "content": [{"type": "text", '
        '"text": "Not a chatbot. A colleague that edits real files here."}]}}\n')

    def negation_blocked(session):
        payload = json.dumps({"transcript_path": str(negation_turn),
                              "session_id": session})
        out = guard("claude-md-guard.py", payload, home, repo, "check").stdout
        return '"decision": "block"' in out

    (repo / ".handrail.toml").write_text("")
    check("wiring: negation stays quiet by default",
          negation_blocked("neg-off"), False)
    (repo / ".handrail.toml").write_text("[rules]\nnegation = true\n")
    check("wiring: a repo can switch negation on",
          negation_blocked("neg-on"), True)

    # The reminder arms the interview format. Injecting it while the check that
    # enforces it is off would be an instruction with no gate behind it.
    grill = json.dumps({"prompt": "grill me on this plan", "session_id": "g1"})
    (repo / ".handrail.toml").write_text("")
    cases += 1
    if "AskUserQuestion" not in guard("claude-md-guard.py", grill, home, repo,
                                      "remind").stdout:
        failures.append("FAIL wiring: the interview reminder is not injected "
                        "by default")
    (home / ".handrail.toml").write_text("[rules]\nask_user_question = false\n")
    cases += 1
    if guard("claude-md-guard.py", grill, home, repo, "remind").stdout.strip():
        failures.append("FAIL wiring: the reminder is injected while the rule "
                        "that enforces it is off")
    (home / ".handrail.toml").unlink()

    # The prose guard cites the policy doc through the same helper the
    # attribution guard uses, and had no case proving it.
    (repo / ".handrail.toml").write_text('policy_doc = "TEAM.md"\n')
    (repo / "TEAM.md").write_text("rules\n")
    payload = json.dumps({"transcript_path": str(transcript),
                          "session_id": "cite"})
    cases += 1
    if "See TEAM.md." not in guard("claude-md-guard.py", payload, home, repo,
                                   "check").stdout:
        failures.append("FAIL wiring: the prose guard does not cite the "
                        "configured policy doc")

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
