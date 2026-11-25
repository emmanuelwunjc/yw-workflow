"""Read projects.json, the one file that names every project the Orca loop serves.

No loop script names a repo. Each one takes `--project <name>` and reads its
settings through this file.

Which file: PROJECTS_JSON, else $BOT_HOME/projects.json when it exists, else the
sample projects.json beside this script.

    python3 projects.py name [<project>]    the project to use: the one named, or the
                                            only one in the file. Exit 2 when the name
                                            is unknown, or when the file holds two or
                                            more projects and none is named.
    python3 projects.py list                every project name, one per line
    python3 projects.py get <project> <key> one value. A dotted key reads inside an
                                            object, e.g. labels.work. A list prints one
                                            item per line. Exit 2 on an unknown project
                                            or key.
    python3 projects.py top <key>           a value shared by all projects, e.g.
                                            live_terminal_max

A string that starts with "~/" comes back with the home folder in its place.
Python callers: `import projects; projects.project(name)` gives the same values, and
`projects.from_argv(sys.argv[1:])` takes `--project <name>` out of a script's arguments.
Test: bash test-projects.sh
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def path():
    if os.environ.get("PROJECTS_JSON"):
        return os.environ["PROJECTS_JSON"]
    home = os.environ.get("BOT_HOME")
    if home and os.path.exists(os.path.join(home, "projects.json")):
        return os.path.join(home, "projects.json")
    return os.path.join(HERE, "projects.json")


def fail(msg):
    print(f"projects: {msg}", file=sys.stderr)
    sys.exit(2)


def expand(v):
    if isinstance(v, str):
        return os.path.expanduser(v) if v.startswith("~/") else v
    if isinstance(v, list):
        return [expand(x) for x in v]
    if isinstance(v, dict):
        return {k: expand(x) for k, x in v.items()}
    return v


def load():
    try:
        with open(path()) as f:
            return expand(json.load(f))
    except (OSError, ValueError) as e:
        fail(f"cannot read {path()}: {e}")


def name(given=""):
    names = sorted(load().get("projects") or {})
    if given:
        if given not in names:
            fail(f"unknown project {given!r} in {path()} (known: {', '.join(names) or 'none'})")
        return given
    if len(names) == 1:
        return names[0]
    fail(f"{len(names)} projects in {path()}: name one with --project ({', '.join(names)})")


def project(given=""):
    return load()["projects"][name(given)]


def from_argv(argv):
    """Take `--project <name>` out of argv. Returns (project name, the other arguments)."""
    given, rest, i = "", [], 0
    while i < len(argv):
        if argv[i] == "--project" and i + 1 < len(argv):
            given, i = argv[i + 1], i + 2
        elif argv[i].startswith("--project="):
            given, i = argv[i].split("=", 1)[1], i + 1
        else:
            rest, i = rest + [argv[i]], i + 1
    return name(given), rest


def dig(obj, key, where):
    for part in key.split("."):
        if not isinstance(obj, dict) or part not in obj:
            fail(f"no key {key!r} in {where}")
        obj = obj[part]
    return obj


def show(v):
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "name" and len(argv) <= 2:
        print(name(argv[1] if len(argv) == 2 else ""))
    elif cmd == "list" and len(argv) == 1:
        print("\n".join(sorted(load().get("projects") or {})))
    elif cmd == "get" and len(argv) == 3:
        print(show(dig(project(argv[1]), argv[2], f"project {argv[1]}")))
    elif cmd == "top" and len(argv) == 2:
        print(show(dig({k: v for k, v in load().items() if k != "projects"}, argv[1], path())))
    else:
        fail("usage: projects.py name [<project>] | list | get <project> <key> | top <key>")


if __name__ == "__main__":
    main(sys.argv[1:])
