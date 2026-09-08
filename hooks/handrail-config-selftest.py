#!/usr/bin/env python3
"""Self-test for the effective-policy resolution in hooks/handrail_config.py.

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


def init_repo(directory):
    """A real repository, because the boundary is whatever git says it is.

    A hand-made .git directory used to be enough when the walk detected markers
    itself. It is not a repository to `git rev-parse`, which is the point: an
    attacker planting one no longer creates a boundary.
    """
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(directory)], check=True,
                   capture_output=True)
    return directory


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
    init_repo(repo)

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

    # A config above the git root must not capture the repo. Anything writable
    # above a checkout, /tmp included, could otherwise set that repo's
    # thresholds and protected branches, and thresholds sit outside the ratchet.
    outer = tmp / "outer"
    inner = init_repo(outer / "checkout")
    write(outer, ".handrail.toml",
          'policy_doc = "EVIL.md"\n[require_review]\ntrivial_lines = 999999\n')
    write(outer, "EVIL.md", "not this repo's policy\n")
    c = load(home, inner)
    check("capture: a config above the git root is ignored",
          c.value("require_review", "trivial_lines"), 25)
    check("capture: and its policy doc is not cited", c.citation(), "")

    # An enclosing REAL repository still must not reach past the inner one.
    # This is the case that matters: a repo cloned inside another repo, or a
    # dotfiles repo at $HOME with projects beneath it.
    init_repo(outer)
    c = load(home, inner)
    check("capture: an enclosing repository does not extend the bound",
          c.value("require_review", "trivial_lines"), 25)
    check("capture: nor does it move the root", c.root, inner.resolve())

    # Outside any repository only the directory itself is trusted, or the same
    # stray config would capture every loose directory beneath it.
    loose_child = tmp / "loosetree" / "child"
    loose_child.mkdir(parents=True)
    write(loose_child.parent, ".handrail.toml",
          "[require_review]\ntrivial_lines = 999999\n")
    c = load(home, loose_child)
    check("capture: outside a repo, an ancestor config is still ignored",
          c.value("require_review", "trivial_lines"), 25)

    # The positive half: trusting nothing at all would also pass the case above.
    write(loose_child, ".handrail.toml", "[require_review]\ntrivial_lines = 7\n")
    c = load(home, loose_child)
    check("capture: with no git root, the cwd's own config is still read",
          c.value("require_review", "trivial_lines"), 7)
    (loose_child / ".handrail.toml").unlink()

    # A policy doc names a file in the tree. Without this an ancestor config
    # could quote any file on disk into a block message.
    write(inner, ".handrail.toml", 'policy_doc = "../EVIL.md"\n')
    c = load(home, inner)
    check("policy doc: a relative path escaping the tree is refused",
          c.citation(), "")
    write(inner, ".handrail.toml", 'policy_doc = "/etc/hosts"\n')
    c = load(home, inner)
    check("policy doc: an absolute path is refused", c.citation(), "")
    (inner / ".handrail.toml").unlink()

    # A repo with no config of its own still resolves to its git root, which is
    # what a relative path in the config is measured against. Deleting that
    # fallback left every other case green, because nothing else reads root.
    bare = init_repo(tmp / "bare")
    deep = bare / "src" / "pkg"
    deep.mkdir(parents=True)
    # resolve() on both sides: macOS hands back /private/var for a temp dir.
    check("fallback: a repo with no config still resolves to its git root",
          load(home, deep).root, bare.resolve())

    # A config in a SUBDIRECTORY governs that subtree. Without this the walk
    # could return the repo root for everything and still pass, because
    # load() reads a config at the root either way.
    write(bare, ".handrail.toml", "[rules]\nnegation = true\n")
    write(deep, ".handrail.toml", "[rules]\nem_dash = false\n")
    c = load(home, deep)
    check("resolution: the nearest config wins over the repo root's",
          c.root, deep.resolve())
    check("resolution: and the root's config is not merged in",
          c.enabled("negation"), False)
    (deep / ".handrail.toml").unlink()
    (bare / ".handrail.toml").unlink()

    write(inner, ".handrail.toml", 'policy_doc = "OK.md"\n')
    write(inner, "OK.md", "the repo's policy\n")
    c = load(home, inner)
    check("fallback: the repo's own config still wins",
          c.citation(), "See OK.md.")

    # A user's policy doc lives on their machine, so it resolves against home.
    # The repo's own doc wins when it has one, so clear it first.
    write(repo, ".handrail.toml", "")
    write(home, ".handrail.toml", 'policy_doc = "MINE.md"\n')
    write(home, "MINE.md", "my rules\n")
    c = load(home, repo)
    check("policy doc: a user-level one resolves against home",
          c.citation(), "See MINE.md.")
    (home / ".handrail.toml").unlink()
    (home / "MINE.md").unlink()

    # Thresholds sit outside the ratchet, so a repo overrides the user's value.
    write(home, ".handrail.toml", "[require_review]\ntrivial_lines = 5\n")
    write(repo, ".handrail.toml", "[require_review]\ntrivial_lines = 50\n")
    c = load(home, repo)
    check("thresholds: a repo value overrides the user's",
          c.value("require_review", "trivial_lines"), 50)
    (home / ".handrail.toml").unlink()

    check("an unknown rule name is off", c.enabled("nosuchrule"), False)

    # The JSON fallback is a documented guarantee and had no case: deleting the
    # branch that reads it left every case green.
    json_only = tmp / "jsononly"
    (json_only / ".git").mkdir(parents=True)
    write(json_only, ".handrail.json", '{"rules": {"negation": true}}')
    check("format: a JSON config is read when it is the only one",
          load(home, json_only).enabled("negation"), True)

    # Without tomllib a .toml cannot be read, and silently applying defaults
    # would leave the user enforcing a policy they did not write.
    toml_only = tmp / "tomlonly"
    (toml_only / ".git").mkdir(parents=True)
    write(toml_only, ".handrail.toml", "[rules]\nnegation = true\n")
    real_tomllib, cfg.tomllib = cfg.tomllib, None
    cases += 1
    try:
        load(home, toml_only)
        failures.append("FAIL format: a .toml loaded with no tomllib available")
    except RuntimeError:
        pass
    finally:
        cfg.tomllib = real_tomllib

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

    # The floor written out literally. Comparing against CI_FLOOR itself would
    # pass whatever that tuple said, so dropping a member from it went unnoticed.
    write(repo, ".handrail.toml", "")
    c = load(home, repo, ci=True)
    check("CI: the floor is exactly these four rules",
          sorted(n for n in cfg.DEFAULTS if c.enabled(n)),
          ["ai_attribution", "em_dash", "handoff_freshness", "require_review"])

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

    # A corrupt .git file is a broken checkout, and git refuses to name a root
    # for it. Nothing above is trusted then, which is the safe answer: a
    # directory whose repository identity cannot be established gets defaults
    # rather than someone else's policy.
    (nested / ".git").write_text("gitdir: ../../.git/modules/gone\n")
    c = load(home, nested)
    check("resolution: a corrupt .git file yields defaults, not the parent's",
          c.enabled("negation"), False)
    (nested / ".git").unlink()

    # A REAL linked worktree, made by git rather than by hand. Requiring the
    # marker to be a directory broke every subdirectory of one of these, and
    # worktrees are this project's mandated workflow for concurrent agents.
    # The fixture sits outside the superproject so a config above it cannot
    # reach the case regardless of what the boundary does.
    source = init_repo(tmp / "wtsource")
    write(source, "seed.txt", "seed\n")
    for args in (["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t",
                                 "commit", "-qm", "seed"]):
        subprocess.run(["git", "-C", str(source), *args], check=True,
                       capture_output=True)
    linked = tmp / "linked"
    subprocess.run(["git", "-C", str(source), "worktree", "add", "-q",
                    str(linked)], check=True, capture_output=True)
    write(linked, ".handrail.toml", "[rules]\nnegation = true\n")
    linked_src = linked / "src"
    linked_src.mkdir()
    c = load(home, linked_src)
    check("resolution: a subdirectory of a linked worktree reads its config",
          c.enabled("negation"), True)
    check("resolution: and the worktree is its own root",
          c.root, linked.resolve())

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
    init_repo(repo)

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

    # RULE 1's Stop half: the check that refuses to end a grilling turn asked in
    # prose. The remind half was covered and this one was not, so forcing this
    # gate on passed every case. It needs a grill state file next to a transcript
    # whose last text ends in a question.
    state = home / ".claude" / "state" / "claude-md-guard"
    state.mkdir(parents=True, exist_ok=True)
    prose_question = repo / "q.jsonl"
    prose_question.write_text(
        '{"message": {"role": "user", "content": "grill me"}}\n'
        '{"message": {"role": "assistant", "content": [{"type": "text", '
        '"text": "Which database should we use for this?"}]}}\n')

    def asked_in_prose(session):
        (state / ("%s.grill" % session)).write_text("1")
        payload = json.dumps({"transcript_path": str(prose_question),
                              "session_id": session})
        out = guard("claude-md-guard.py", payload, home, repo, "check").stdout
        return "AskUserQuestion" in out

    (repo / ".handrail.toml").write_text("")
    check("wiring: a grilling turn asked in prose is refused by default",
          asked_in_prose("ask-on"), True)
    (home / ".handrail.toml").write_text("[rules]\nask_user_question = false\n")
    check("wiring: switching the interview rule off stops the refusal",
          asked_in_prose("ask-off"), False)
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
