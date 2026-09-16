#!/usr/bin/env python3
"""Prove every recorded defect is caught by a self-check that can fail.

Canonical copy: the yw-workflow plugin, `skills/mutation-gate/mutation_gate.py`. A repo
adopts it by adding `scripts/mutations.json` and copying this file verbatim beside it.
Edit it in the plugin, then re-copy; `diff` against the plugin's file is the drift check.

Why: review rounds kept finding the production code right and the assertion unable to fail.
Each entry breaks a script like a real defect would; its `--demo` must then fail, or this exits 1.

THE RULE FOR ADDING AN ENTRY. An entry is added only when a ticket names the rule as one
that must be provable by mutation, or when a review found an assertion that could not
fail. The entry's `source` cites that ticket or PR. No entry for a rule nobody has seen
break. An entry with no `source` fails `--list` by name.

`mutations.json` is `{"mutations": [...], "retired": [...]}`. An entry is `{script, label,
find, replace, source}`; a retired one adds `retired` (the date) and the run skips it, so a
finished one-shot script's record survives at no cost. `script` is a bare filename beside the
JSON file. `find` occurs exactly once, in production code, outside the script's own `_demo`.

    python3 scripts/mutation_gate.py [--list [--retired]] [--demo] [other.json]
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

DEMO_TIMEOUT_SECONDS = 60

def load(path):
    """(active, retired) from the JSON file. A missing field fails by name."""
    data = json.load(open(path))
    for kind in ("mutations", "retired"):
        for e in data.get(kind, []):
            need = ("script", "label", "find", "replace", "source") + (("retired",) if kind == "retired" else ())
            if missing := sorted({f for f in need if f not in e or (f != "replace" and not e[f])}):
                raise SystemExit(f"{path}: {e.get('script')}: {e.get('label')!r} has no {', '.join(missing)}. "
                                 "Every entry cites the ticket or PR that earned it; a retired one carries its date.")
    return data.get("mutations", []), data.get("retired", [])

def entry_problem(source, find, replace):
    """Why one entry is unusable, or "". `find` is applied once, so it must be unique and in production code."""
    if not find or find == replace:
        return "empty find string" if not find else "mutation changes nothing"
    if (count := source.count(find)) != 1:
        return ("no longer matches any code; retarget or retire it" if count == 0
                else f"its find string occurs {count} times; anchor it to be unique")
    line = source[: source.index(find)].count("\n") + 1
    try:
        demo = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_demo"]
    except SyntaxError:
        demo = []  # the baseline run reports an unparseable file
    if demo and demo[0].body[0].lineno <= line <= demo[0].end_lineno:
        return f"its only match is line {line}, inside that script's own _demo"
    return ""

def check_entries(scripts_dir, entries):
    """Every entry is usable against the live code. Returns the problems."""
    sources, seen, problems = {}, set(), []
    for e in entries:
        src = sources.setdefault(e["script"], open(os.path.join(scripts_dir, e["script"])).read())
        key = (e["script"], e["find"], e["replace"])
        problem = "duplicate of an earlier entry" if key in seen else entry_problem(src, e["find"], e["replace"])
        seen.add(key)
        problems += [f"{e['script']}: {e['label']!r}: {problem}"] if problem else []
    return problems

def run_demo(scripts_dir, script, mutation=None):
    """`script --demo` on a private copy, mutated if asked. True on exit 0 ending `demo ok`; a hang is a kill."""
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "repo", os.path.basename(scripts_dir))
        shutil.copytree(scripts_dir, work, ignore=shutil.ignore_patterns("__pycache__"))
        path = os.path.join(work, script)
        if mutation:
            source = open(path).read()
            open(path, "w").write(source.replace(mutation["find"], mutation["replace"], 1))
        try:
            result = subprocess.run([sys.executable, path, "--demo"], cwd=os.path.dirname(work),
                                    capture_output=True, text=True, timeout=DEMO_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False
    return result.returncode == 0 and result.stdout.strip().endswith("demo ok")

def main(argv):
    if "--demo" in argv:
        return _demo()
    path = next((a for a in argv if not a.startswith("--")), os.path.join("scripts", "mutations.json"))
    active, retired = load(path)
    if "--list" in argv:
        shown, kind = (retired, "retired") if "--retired" in argv else (active, "active")
        for e in shown:
            print(f"{e['script']}: {e['label']} ({e['source']}{', retired ' + e['retired'] if kind == 'retired' else ''})")
        return print(f"\n{len(shown)} {kind} mutations")
    scripts_dir = os.path.dirname(os.path.abspath(path))
    if not active or (problems := check_entries(scripts_dir, active)):
        raise SystemExit("\n".join(problems) if active else "no active mutations: an empty list is not a gate")
    for script in sorted({e["script"] for e in active}):
        if not run_demo(scripts_dir, script):
            raise SystemExit(f"{script} --demo fails BEFORE any mutation. Fix that first: a failing baseline proves nothing.")
    with ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        alive = list(pool.map(lambda e: run_demo(scripts_dir, e["script"], e), active))
    survivors = [f"SURVIVED {e['script']}: {e['label']}" for e, a in zip(active, alive) if a]
    print("\n".join(survivors + [f"{len(active)} mutations, {len(survivors)} survived, {len(retired)} retired and skipped"
                                 + ("" if survivors else "\nok: every recorded defect is caught by a check that can fail")]))
    if survivors:
        raise SystemExit(f"{len(survivors)} mutation(s) survived: the assertions covering them do not exist or cannot fail.")

def _demo():
    """Self-check on fixtures: the entry rules, the source rule, retired, the timeout."""
    global DEMO_TIMEOUT_SECONDS
    assert entry_problem("a = 1\n", "a = 1", "a = 2") == ""
    assert "empty" in entry_problem("a = 1\n", "", "x") and "changes nothing" in entry_problem("a = 1\n", "a = 1", "a = 1")
    assert "no longer matches" in entry_problem("a = 1\n", "b = 1", "b = 2") and "occurs 2 times" in entry_problem("a = 1\na = 1\n", "a = 1", "a = 2")
    src = "X = 1\n\n\ndef main():\n    later = 3\n\n\ndef _demo():\n    assert X == 1\n    fixture = 2\n"
    assert "inside" in entry_problem(src, "fixture = 2", "fixture = 3")
    assert entry_problem(src, "later = 3", "later = 4") == "", "main() after _demo is production"
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(scripts := os.path.join(tmp, "scripts"))
        open(os.path.join(scripts, "s.py"), "w").write("X = 1\n\n\ndef _demo():\n    assert X == 1\n    print('demo ok')\n\n\n_demo()\n")
        good = {"script": "s.py", "label": "x flipped", "find": "X = 1", "replace": "X = 2", "source": "#1"}
        json.dump({"mutations": [good], "retired": [dict(good, label="old", retired="2026-01-01")]},
                  open(path := os.path.join(scripts, "mutations.json"), "w"))
        active, retired = load(path)
        assert [e["label"] for e in active] == ["x flipped"] and [e["label"] for e in retired] == ["old"]
        assert check_entries(scripts, active) == [] and "duplicate" in check_entries(scripts, [good, good])[0]
        assert run_demo(scripts, "s.py") is True and run_demo(scripts, "s.py", good) is False, "a real mutant is killed"
        for broken, word in ((dict(good, source=""), "source"), (dict(good, retired=""), "retired")):
            json.dump({"mutations": [good], "retired": [broken]}, open(path, "w"))
            try:
                load(path)
                raise AssertionError(f"an entry with no {word} must fail by name")
            except SystemExit as exc:
                assert "x flipped" in str(exc) and word in str(exc), exc
        open(os.path.join(scripts, "hangs.py"), "w").write("import time\ntime.sleep(3)\nprint('demo ok')\n")
        real, DEMO_TIMEOUT_SECONDS = DEMO_TIMEOUT_SECONDS, 1
        try:  # the fixture PASSES when given time, so an unbounded run fails this assert
            assert run_demo(scripts, "hangs.py") is False, "a hang counts as killed"
        finally:
            DEMO_TIMEOUT_SECONDS = real
        assert run_demo(scripts, "hangs.py") is True, "the fixture must pass given time, or the bound proved nothing"
    print("demo ok")

if __name__ == "__main__":
    main(sys.argv[1:])
