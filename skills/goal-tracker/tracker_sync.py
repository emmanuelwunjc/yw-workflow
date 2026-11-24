"""Keep a goal tracker issue in layers, one layer per slice: label.

The tracker (the top issue) has one layer issue per part as its direct
sub-issues, e.g. "Layer: Docs". Every work issue is a sub-issue of the layer
that matches its slice: label. The map file (default .github/tracker-layers.yml,
or --config) holds the tracker's issue number and maps each label to its layer
title. The script finds the layers at run time: the sub-issues of the tracker
with those titles.

--sync puts the whole tracker in order, whatever event started it, so an event
that GitHub drops costs nothing: the next run fixes it.
.github/workflows/tracker.yml, which is optional, runs it on five issue
events: opened, labeled, unlabeled, closed and reopened. Each run:

  - moves each issue with one slice: label under its layer,
  - moves an issue with no slice: label out of its layer, back under the tracker,
  - skips an issue with two or more slice: labels, with a warning line,
  - closes each layer whose issues are all closed, and reopens it if not.
  Layer issues (known by title) and the tracker itself are never moved.
  Before the migration (no layers under the tracker) it does nothing.

Then it lists each open issue of the repo that no tracker can see, one line
each: "#N has no slice: label (title)". It skips an issue with any slice:
label, the tracker, a layer (by title), and an issue with an exempt label:
tracker, or a label in the exempt: list of the map file. The list is a
warning and the exit code stays 0. With --strict the exit code is 1 while the
list has a line, so a CI step or a weekly check fails on it.

Stdlib and the gh CLI only. Its self-check is test_tracker_sync.py in
skills/goal-tracker/ of yw-workflow, the general copy of this file.
Run it from the repo root, so the default map file path resolves.

  python3 tools/tracker_sync.py --sync --dry-run      # prints every API call

Migration: makes each missing layer, labels the issues you name, then syncs.
A layer that exists, under the tracker or not, is used again, so a rerun after
a crash creates no duplicate. Make each slice: label first: a new layer takes
its label's description as its body. Children of the tracker with no slice:
label are listed, each with the --label flag to give it one.

  python3 tools/tracker_sync.py --migrate --dry-run       # lists the unlabeled
  python3 tools/tracker_sync.py --migrate --dry-run \\
      --label N=slice:<part> --label M=slice:<part>       # prints every API call
  python3 tools/tracker_sync.py --migrate --label ...     # makes them

Undo: move each child back under the tracker T with the same endpoint, e.g.
  gh api -X POST repos/OWNER/REPO/issues/T/sub_issues -F sub_issue_id=ID -F replace_parent=true
where ID is the child's numeric id (gh api repos/OWNER/REPO/issues/N --jq .id).
Then close the layer issues and retitle them, so the script stops finding them.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_CONFIG = Path(".github/tracker-layers.yml")
# The map file is read line by line, in exactly these forms, and any other line
# stops the script. It never guesses at YAML. A blank line or a # comment line
# is skipped. A leading BOM and a \r before each line end are removed.
TRACKER_LINE = re.compile(r"tracker: ([1-9][0-9]*)")
HEADING_LINE = "layers:"
EXEMPT_LINE = "exempt:"
EXEMPT_ITEM = re.compile(r'  - "([^"\\\x00-\x1f\x7f]+)"')
LAYER_LINE = re.compile(r'  "(slice:[a-z0-9-]+)": "([^"\\\x00-\x1f\x7f]+)"')
ACCEPTED = ('Write tracker: <number of the top issue>, then layers:, then each layer as '
            '"slice:<part>": "<title>" in double quotes, indented two spaces. '
            'An optional exempt: line takes - "<label>" lines, indented two spaces.')
SLICE = "slice:"
# Labels of issues that serve the work but are no work item, so no tracker lists them.
# "lane" left this list when lane issues retired (#228, from twenty #672).
DEFAULT_EXEMPT = ("tracker",)


def slices_of(labels):
    """The slice: labels in a list of label names, in lower case, sorted."""
    return sorted(name.lower() for name in labels if name.lower().startswith(SLICE))


def load_config(path):
    """Return (tracker number, {slice label: layer title}, [exempt labels]) from the map file.

    Raises ValueError for a missing file, a line in any form but the accepted
    ones (see ACCEPTED), a key given twice, or no tracker line.
    """
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")  # drops a BOM, keeps each \r
    except OSError as err:
        raise ValueError(f"{path}: cannot read the map file ({err.strerror}).") from err
    tracker, entries, exempt, seen, section = None, {}, [], {}, None
    for number, line in enumerate(text.split("\n"), 1):
        line = line.removesuffix("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tracker_match, layer_match = TRACKER_LINE.fullmatch(line), LAYER_LINE.fullmatch(line)
        item_match = EXEMPT_ITEM.fullmatch(line)
        if tracker_match:
            key, tracker, section = "tracker", int(tracker_match[1]), None
        elif line in (HEADING_LINE, EXEMPT_LINE):
            key = section = line
        elif layer_match and section == HEADING_LINE:
            key = layer_match[1]
            entries[key] = layer_match[2]
        elif item_match and section == EXEMPT_LINE:
            key = item_match[1]
            exempt.append(key)
        else:
            raise ValueError(f"{path} line {number}: cannot read {line!r}. {ACCEPTED}")
        if key in seen:
            raise ValueError(f"{path} line {number}: {key} is already on line {seen[key]}. "
                             "Keep one.")
        seen[key] = number
    if tracker is None:
        raise ValueError(f"{path}: no tracker line. {ACCEPTED}")
    return tracker, entries, exempt


def one_per_title(issues, title):
    """Return the one issue with this title, or None. Raises ValueError for two."""
    found = [i for i in issues if i["title"] == title]
    if len(found) > 1:
        numbers = ", ".join(f"#{i['number']}" for i in found)
        raise ValueError(f'{numbers} are all titled "{title}". Retitle or close all but one.')
    return found[0] if found else None


def find_layers(children, config):
    """Return {slice label: layer number} for the tracker's children titled as a layer."""
    found = {label: one_per_title(children, title) for label, title in config.items()}
    return {label: layer["number"] for label, layer in found.items() if layer}


def plan_layers(config, children, labeled, tracker):
    """Return (layers found, calls to attach orphan layers, labels whose layer to create).

    children: the tracker's sub-issues. labeled: every issue with a slice: label.
    """
    layers, calls, create = find_layers(children, config), [], []
    for label, title in config.items():
        if label in layers:  # already exists under the tracker
            continue
        orphan = one_per_title([i for i in labeled if label in slices_of(i["labels"])], title)
        if orphan:  # made by a run that crashed before it linked it
            layers[label] = orphan["number"]
            calls.append(add_call(tracker, orphan["id"]))
        else:
            create.append(label)
    return layers, calls, create


def parse_label_pairs(pairs, config):
    """Turn ["301=slice:tooling", ...] into {301: "slice:tooling"}. Raises ValueError."""
    labels = {}
    for pair in pairs:
        match = re.fullmatch(r"(\d+)=(\S+)", pair)
        if not match or match[2] not in config:
            raise ValueError(f"--label {pair}: give N=label, with a label from the map file")
        labels[int(match[1])] = match[2]
    return labels


def add_call(parent, issue_id):
    return ("POST", f"issues/{parent}/sub_issues",
            {"sub_issue_id": issue_id, "replace_parent": True})


def sync_plan(issues, children, layers, layer_states, tracker, config):
    """Return (API calls, warning lines) that put the tracker in order.

    issues: every issue with a slice: label (number, id, state, title, labels).
    children: {layer or tracker number: [its sub-issues]}.
    layers: {slice label: layer number}. layer_states: {layer number: state}.
    """
    calls, warnings = [], []
    parent_of = {kid["number"]: p for p, kids in children.items() for kid in kids}
    members = {layer: {kid["number"]: kid["state"] for kid in children[layer]}
               for layer in layers.values()}
    labeled = {i["number"] for i in issues}

    def move(item, target):
        calls.append(add_call(target, item["id"]))
        members.get(parent_of.get(item["number"]), {}).pop(item["number"], None)
        if target in members:
            members[target][item["number"]] = item["state"]

    for item in issues:
        number = item["number"]
        if number == tracker or item["title"] in config.values():  # layers are found by title
            continue
        slices = slices_of(item["labels"])
        if len(slices) > 1:
            warnings.append(f"#{number} skipped: {len(slices)} slice labels "
                            f"({', '.join(slices)}). Keep one.")
        elif slices[0] not in layers:
            warnings.append(f"#{number} skipped: #{tracker} has no layer for {slices[0]}.")
        elif parent_of.get(number) != layers[slices[0]]:
            move(item, layers[slices[0]])

    def unmapped(kid):  # issues are fetched by the labels of the map, so a kid can hold another
        names = slices_of(kid["labels"])
        return names and (f"#{kid['number']} has {', '.join(names)}, which is not in the "
                          "map file. Add it to the map, or relabel the issue.")

    for layer in layers.values():
        for kid in children[layer]:
            if kid["number"] not in labeled:
                move(kid, tracker)
                if unmapped(kid):
                    warnings.append(unmapped(kid))
    for kid in children.get(tracker, []):
        if kid["number"] not in labeled and kid["number"] not in layers.values():
            warnings.append(unmapped(kid) or
                            f"#{kid['number']} under #{tracker} has no slice: label "
                            f"(give it one: --label {kid['number']}=slice:<part>)")

    for layer, states in members.items():
        want = "closed" if all(s == "closed" for s in states.values()) else "open"
        if want != layer_states[layer]:
            calls.append(("PATCH", f"issues/{layer}", {"state": want}))
    return calls, warnings


def unlabeled(open_issues, tracker, config, exempt):
    """Return one line per open issue that no tracker can see.

    Skipped: an issue with any slice: label, the tracker, a layer (by title),
    and an issue with a label in DEFAULT_EXEMPT or exempt. Case is ignored.
    """
    skip = {name.lower() for name in (*DEFAULT_EXEMPT, *exempt)}
    return [f"#{i['number']} has no slice: label ({i['title']})" for i in open_issues
            if i["number"] != tracker and i["title"] not in config.values()
            and not slices_of(i["labels"])
            and not skip & {name.lower() for name in i["labels"]}]


# The part below talks to GitHub. The test does not cover it: the gh calls,
# and the order of steps in sync and migrate.

def gh(*args):
    done = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip())
    return done.stdout


def run(repo, call, dry_run, note=""):
    method, path, fields = call
    args = ["-X", method, f"repos/{repo}/{path}"]
    for key, value in fields.items():
        if isinstance(value, list):
            args += [arg for item in value for arg in ("-f", f"{key}[]={item}")]
        elif isinstance(value, str):
            args += ["-f", f"{key}={value}"]
        else:
            args += ["-F", f"{key}={json.dumps(value)}"]
    if dry_run:
        print(f"would run: {shlex.join(['gh', 'api', *args])}{note}")
        return {}
    return json.loads(gh(*args) or "{}")


ROW = ".[] | select(.pull_request == null) | {number, id, state, title, labels: [.labels[].name]}"


def rows(path):
    return [json.loads(line) for line in gh("--paginate", path, "--jq", ROW).splitlines()]


def children_of(repo, number):
    if isinstance(number, str):  # a layer the dry-run has not created
        return []
    return rows(f"repos/{repo}/issues/{number}/sub_issues?per_page=100")


def labeled_issues(repo, config):
    """Every issue (any state) with a configured slice: label, by REST for the numeric id."""
    seen = {}
    for label in config:
        for item in rows(f"repos/{repo}/issues?labels={label}&state=all&per_page=100"):
            seen[item["number"]] = item
    return list(seen.values())


def sync(repo, config, tracker, layers, tracker_kids, issues, dry_run, new=()):
    # A layer is a child of the tracker, an orphan the migration found among the
    # labeled issues, or new. tracker_kids is read before the orphans are linked.
    states = {k["number"]: k["state"] for k in [*issues, *tracker_kids]}
    states.update({layer: "open" for layer in new})
    children = {layer: children_of(repo, layer) for layer in layers.values()}
    children[tracker] = tracker_kids
    calls, warnings = sync_plan(issues, children, layers, states, tracker, config)
    number_of = {i["id"]: i["number"] for kids in [issues, *children.values()] for i in kids}
    for call in calls:
        moved = call[2].get("sub_issue_id")
        run(repo, call, dry_run, f"  # moves #{number_of[moved]}" if moved else "")
    print("\n".join(warnings + [f"{len(calls)} calls"]))


def migrate(repo, config, tracker, extra, dry_run):
    tracker_kids = children_of(repo, tracker)
    by_number = {k["number"]: k for k in tracker_kids}
    missing = sorted(set(extra) - set(by_number))
    if missing:
        raise ValueError(f"--label names issues that are not under #{tracker}: {missing}")
    issues = labeled_issues(repo, config)
    layers, calls, create = plan_layers(config, tracker_kids, issues, tracker)
    for call in calls:
        run(repo, call, dry_run, "  # links a layer made by a crashed run")
    for label in create:
        what = gh(f"repos/{repo}/labels/{label}", "--jq", ".description").strip()
        body = (f"{what}. Every issue labeled `{label}` is a sub-issue here. "
                "tools/tracker_sync.py keeps this list up to date, so nobody edits it by hand.")
        made = run(repo, ("POST", "issues", {"title": config[label], "body": body,
                                             "labels": [label]}), dry_run)
        layers[label] = made.get("number", f"<new {config[label]}>")
        run(repo, add_call(tracker, made.get("id", f"<id of new {config[label]}>")), dry_run)
    for number, label in extra.items():
        run(repo, ("POST", f"issues/{number}/labels", {"labels": [label]}), dry_run)
        issues.append(dict(by_number[number], labels=by_number[number]["labels"] + [label]))
    new = [layers[label] for label in create]
    sync(repo, config, tracker, layers, tracker_kids, issues, dry_run, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sync", action="store_true", help="put the whole tracker in order")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"the label-to-layer map (default {DEFAULT_CONFIG})")
    parser.add_argument("--strict", action="store_true",
                        help="with --sync: exit 1 while an open issue has no slice: label")
    parser.add_argument("--label", action="append", default=[], metavar="N=slice:x",
                        help="with --migrate: add this slice label to issue N, then move it")
    args = parser.parse_args()
    if args.sync == args.migrate or (args.label and not args.migrate) or (
            args.strict and not args.sync):
        parser.error("give --sync [--strict], or --migrate [--label N=slice:x ...], "
                     "with optional --dry-run")
    repo = os.environ.get("GITHUB_REPOSITORY") or subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True, text=True, check=True).stdout.strip()
    try:
        tracker, config, exempt = load_config(args.config)
        if args.migrate:
            migrate(repo, config, tracker, parse_label_pairs(args.label, config), args.dry_run)
            return 0
        tracker_kids = children_of(repo, tracker)
        layers = find_layers(tracker_kids, config)
        if layers:
            sync(repo, config, tracker, layers, tracker_kids, labeled_issues(repo, config),
                 args.dry_run)
        else:
            print(f"#{tracker} has no layer issues yet, run --migrate first. Nothing synced.")
        lost = unlabeled(rows(f"repos/{repo}/issues?state=open&per_page=100"),
                         tracker, config, exempt)
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    if lost:
        print("\n".join(lost))
    return 1 if lost and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
