#!/usr/bin/env python3
"""Self-test for the CI entry points: `scan` and `check-pr`.

The hook selftests next to this one cover the rules themselves. This covers the
three things that are different when the same rules run in CI:

  1. exit codes, because a CI gate communicates only through them,
  2. failing CLOSED, because a scan that crashed or could not read its input
     proved nothing and passing on it makes a required check a rubber stamp,
  3. reading argv rather than stdin, because a job that blocks on a hook payload
     that never arrives hangs until the runner times out.
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
CMG = HOOKS / "claude-md-guard.py"
ATTR = HOOKS / "no-ai-attribution.py"
REVIEW = HOOKS / "require-code-review.py"

EM_DASH = "—"
failures = []
cases = 0


def run(script, *args, stdin=""):
    """Run a guard with argv and a closed-ish stdin, returning its exit code.

    stdin is fed rather than inherited on purpose: if a scan mode ever starts
    reading it again, this returns instead of hanging the suite.
    """
    return subprocess.run([sys.executable, str(script), *args], input=stdin,
                          capture_output=True, text=True, timeout=20).returncode


def expect(name, got, want):
    global cases
    cases += 1
    if got != want:
        failures.append("FAIL %s: want exit %d, got %d" % (name, want, got))


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    clean = tmp / "clean.md"
    clean.write_text("It runs in a terminal, so it can edit real files.\n")
    dash = tmp / "dash.md"
    dash.write_text("This sentence has an em dash %s right here.\n" % EM_DASH)
    negation = tmp / "negation.md"
    negation.write_text("Not a chatbot. A colleague that edits real files here.\n")
    fenced = tmp / "fenced.md"
    fenced.write_text("Quoted code:\n\n```\nx = a %s b\n```\n" % EM_DASH)
    missing = tmp / "does-not-exist.md"

    expect("cmg scan: clean file passes", run(CMG, "scan", clean), 0)
    expect("cmg scan: em-dash fails", run(CMG, "scan", dash), 1)
    expect("cmg scan: negation fails", run(CMG, "scan", negation), 1)
    expect("cmg scan: em-dash inside a fence passes", run(CMG, "scan", fenced), 0)
    # A path the job could not read is an unanswered question, and an unanswered
    # question is not a pass.
    expect("cmg scan: unreadable path fails closed", run(CMG, "scan", missing), 1)
    expect("cmg scan: no files passes", run(CMG, "scan"), 0)
    expect("cmg scan: one bad file among good ones fails",
           run(CMG, "scan", clean, dash, fenced), 1)

    body_clean = tmp / "body-clean.md"
    body_clean.write_text("Fixes the parser.\n\nClaude-Session: "
                          "https://claude.ai/code/session_abc\n")
    body_footer = tmp / "body-footer.md"
    body_footer.write_text("Fixes the parser.\n\nGenerated with [Claude Code]"
                           "(https://claude.com/claude-code)\n")
    body_url = tmp / "body-url.md"
    body_url.write_text("See https://claude.ai/code/session_xyz for context.\n")

    expect("attr scan: clean body passes", run(ATTR, "scan", body_clean), 0)
    expect("attr scan: commit trailer alone still passes",
           run(ATTR, "scan", body_clean), 0)
    expect("attr scan: generation footer fails", run(ATTR, "scan", body_footer), 1)
    expect("attr scan: bare session URL fails", run(ATTR, "scan", body_url), 1)
    expect("attr scan: unreadable path fails closed",
           run(ATTR, "scan", missing), 1)
    expect("attr scan: no files passes", run(ATTR, "scan"), 0)

    # A guard that crashes must fail the CI job. The hook path deliberately does
    # the opposite (a crashing guard must never wedge a session), so the two are
    # asserted separately: this is the regression that would silently turn the
    # required check green forever.
    # A guard that crashes must fail the CI job. The hook path deliberately does
    # the opposite (a crashing guard must never wedge a session), so the two are
    # asserted separately: this is the regression that would silently turn the
    # required check green forever.
    #
    # The fault is injected at Path.read_text, which is what scan() actually
    # calls. Patching builtins.open does not reach it, and a probe that fails to
    # provoke a crash tests nothing while looking like it passed.
    probe = subprocess.run(
        [sys.executable, "-c",
         "import pathlib, runpy, sys\n"
         "def boom(self, *a, **k): raise RuntimeError('injected')\n"
         "pathlib.Path.read_text = boom\n"
         "sys.argv = ['claude-md-guard.py', 'scan', %r]\n"
         "runpy.run_path(%r, run_name='__main__')\n" % (str(clean), str(CMG))],
        capture_output=True, text=True, timeout=20)
    cases += 1
    if probe.returncode == 0:
        failures.append("FAIL cmg scan: a crash exited 0, so CI would go green "
                        "on a guard that never ran")

    # The same injection in hook mode must still exit 0: a broken guard is not
    # allowed to take the user's session down with it.
    hook_probe = subprocess.run(
        [sys.executable, "-c",
         "import pathlib, runpy, sys\n"
         "def boom(self, *a, **k): raise RuntimeError('injected')\n"
         "pathlib.Path.read_text = boom\n"
         "sys.argv = ['claude-md-guard.py', 'check']\n"
         "runpy.run_path(%r, run_name='__main__')\n" % str(CMG)],
        input='{"transcript_path": "/nope", "session_id": "s"}',
        capture_output=True, text=True, timeout=20)
    cases += 1
    if hook_probe.returncode != 0:
        failures.append("FAIL cmg check: a crash in hook mode exited %d; the "
                        "hook path must fail open" % hook_probe.returncode)

# require-code-review's CI mode talks to the GitHub API. Load the module and
# replace that one function, so the decision table is tested without a network.
spec = importlib.util.spec_from_file_location("require_code_review", REVIEW)
rcr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rcr)

BIG = "hooks/guard.py 40 10"      # 50 code lines, over TRIVIAL_LINES
SMALL = "hooks/guard.py 3 1"      # 4 code lines
DOCS = "README.md 900 900"        # prose only, never gated


def fake_gh(files="", reviews="", comments=""):
    def gh(*args):
        if "files" in args:
            return files
        if "reviews" in args:
            return reviews
        if "comments" in args:
            return comments
        return ""
    return gh


def review_case(name, want, **kw):
    global cases
    cases += 1
    original = rcr.gh
    rcr.gh = fake_gh(**kw)
    try:
        got, _ = rcr.review_status("1")
    finally:
        rcr.gh = original
    if got != want:
        failures.append("FAIL %s: want %r, got %r" % (name, want, got))


review_case("big diff, no review", "unreviewed", files=BIG)
review_case("big diff, approved", "ok", files=BIG, reviews="APPROVED")
review_case("big diff, changes requested", "ok", files=BIG,
            reviews="CHANGES_REQUESTED")
review_case("big diff, verdict in a comment", "ok", files=BIG,
            comments="PASS. Read the whole diff, nothing blocking.")
review_case("small diff needs no review", "ok", files=SMALL)
review_case("docs-only needs no review", "ok", files=DOCS)
# An empty file list means the lookup failed. The hook lets that through so a
# network blip cannot wedge a local merge; CI must not.
review_case("broken lookup is unknown, never ok", "unknown", files="")

if failures:
    print("\n".join(failures))
    print("\nRESULT: %d failed of %d cases" % (len(failures), cases))
    sys.exit(1)
print("scan-modes: %d cases pass" % cases)
