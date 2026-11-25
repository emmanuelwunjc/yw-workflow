"""Read the JSON that audit.sh fetched and report label gaps for one app.

Usage (from audit.sh): python3 scan.py <dir> <project> <region> <app> <legacy,values> <table|fixes>
It reads only the files in <dir>. It runs no command. In fixes mode it prints commands as text.
"""
import collections
import json
import os
import re
import shlex
import sys

KEYS = ("owner", "team", "purpose", "app")
DESC_KINDS = {"scheduler", "sa"}  # no labels: key=value pairs live in the description
PAIR = re.compile(r"\b(owner|team|purpose|app)=([A-Za-z0-9_.-]+)")


def rows(d):
    for kind in ("run-service", "run-job", "scheduler", "bucket", "repo", "topic", "sa"):
        for item in json.load(open(os.path.join(d, kind + ".json"))):
            meta = item.get("metadata", item)
            name = item.get("email") or meta["name"].rsplit("/", 1)[-1]
            desc = item.get("description", "")
            labels = dict(PAIR.findall(desc)) if kind in DESC_KINDS else dict(meta.get("labels") or {})
            if kind == "topic" and "goog-managed-by" in labels:
                continue  # made and labelled by Google
            target = "pubsub" if "pubsubTarget" in item else "app-engine" if "appEngineHttpTarget" in item else "http"
            yield {"kind": kind, "name": name, "desc": desc, "labels": labels, "target": target}


def in_scope(r, app, legacy, hint):
    have = r["labels"].get("app")
    return have == app or have in legacy or (not have and hint in r["name"])


def short(name):
    return name.split("@")[0]  # a service account email prints as its account id


def purpose_from_name(name, project, hint):
    base = name.split("@")[0].replace(project + "-", "")
    return re.sub(r"^%s-" % re.escape(hint), "", base) or base


def main():
    d, project, region, app, legacy, mode = sys.argv[1:]
    legacy = set(filter(None, legacy.split(",")))
    hint = app.split("-")[0]
    mine = [r for r in rows(d) if in_scope(r, app, legacy, hint)]
    common = {k: collections.Counter(r["labels"][k] for r in mine if k in r["labels"]) for k in ("owner", "team")}
    gaps = 0
    if mode == "table":
        print("%-12s %-42s %-16s %s" % ("KIND", "NAME", "APP", "STATUS"))
    for r in mine:
        lab = r["labels"]
        missing = [k for k in KEYS if k not in lab or (k == "app" and lab[k] != app)]
        if not missing:
            if mode == "table":
                print("%-12s %-42s %-16s %s" % (r["kind"], short(r["name"]), lab["app"], "ok"))
            continue
        gaps += 1
        want = {"app": app, "purpose": purpose_from_name(r["name"], project, hint)}
        for k, c in common.items():
            want[k] = c.most_common(1)[0][0] if c else "CHANGE_ME_" + k
        fix = {k: (want[k] if k in missing else lab[k]) for k in KEYS}
        absent = [k for k in KEYS if k not in lab]
        parts = ["missing " + ",".join(absent)] if absent else []
        if lab.get("app") in legacy:
            parts.append("RENAME app=%s" % lab["app"])
        status = " + ".join(parts)
        if mode == "table":
            print("%-12s %-42s %-16s %s (suggest purpose=%s)" % (r["kind"], short(r["name"]), lab.get("app", "-"), status, fix["purpose"]))
        else:
            print_fix(r, fix, project, region)
    if mode == "table":
        print("%d in scope for app=%s, %d with gaps. Legacy values: %s" % (len(mine), app, gaps, ",".join(sorted(legacy)) or "none"))
    return 1 if gaps and mode == "table" else 0


def print_fix(r, fix, project, region):
    pairs = ",".join("%s=%s" % (k, fix[k]) for k in KEYS)
    n, p, loc = shlex.quote(r["name"]), shlex.quote(project), shlex.quote(region)
    if r["kind"] in DESC_KINDS:
        text = PAIR.sub("", r["desc"]).strip(" ,.")
        desc = shlex.quote(("%s. %s" % (text, pairs)) if text else pairs)
    k = r["kind"]
    if k == "run-service":
        print(f"gcloud run services update {n} --region {loc} --update-labels={pairs} --project {p}")
    elif k == "run-job":
        print(f"gcloud run jobs update {n} --region {loc} --update-labels={pairs} --project {p}")
    elif k == "bucket":
        print(f"gcloud storage buckets update gs://{r['name']} --update-labels={pairs} --project {p}")
    elif k == "repo":
        print(f"gcloud artifacts repositories update {n} --location {loc} --update-labels={pairs} --project {p}")
    elif k == "topic":
        print(f"gcloud pubsub topics update {n} --update-labels={pairs} --project {p}")
    elif k == "scheduler":
        print(f"gcloud scheduler jobs update {r['target']} {n} --location {loc} --description={desc} --project {p}")
    elif k == "sa":
        print(f"gcloud iam service-accounts update {n} --description={desc} --project {p}")


if __name__ == "__main__":
    sys.exit(main())
