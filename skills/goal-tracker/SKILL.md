---
name: goal-tracker
description: Set up a pinned goal tracker issue whose progress bars update with no hand edits, from layer sub-issues, one slice label per work issue, and a sync script. Use when the owner asks for a "north star tracker", a "pinned tracker", a "progress bar issue", a "goal tracker", or to "track a project to done", or when a backlog serves one goal with a target date and more than one part.
origin: authored
tags: [github-issues, tracker, sub-issues, progress, planning]
version: 1.0.0
---

# Goal tracker

**In one line:** One pinned issue shows how far a goal is, and a script keeps its progress bars current with no hand edits.

Say that line back when you start, so whoever invoked this knows what they got.

The pattern comes from the tracker of edsim-paper, a private repo, read
2026-11-15. The code beside this file is a general copy of its code:

- `tracker_sync.py`: the sync logic.
- `test_tracker_sync.py`: its offline self-check. CI runs it through
  `hooks/goal-tracker-selftest.py`.
- `tracker.yml`: the optional workflow.
- `tracker-layers.yml`: a template of the label-to-layer map.

`docs/DECISIONS.md` (2026-11-15) says why the copy lives here.

## When a repo gets one

Set one up when the work has a goal with a target date and more than one part,
e.g. a release with code, docs and tests. The owner sees the whole goal on one
page.

Skip it for one ticket, or for a short backlog with no date. The open issue
list is enough there.

## How it differs from `lane` issues

Both are GitHub issues. They do different jobs, so keep them apart.

- A `lane` issue (skill `handoff`) tells the next session what to do. Its body
  holds the `Held by:` line and the lane's `## Next`. A session claims one
  with `scripts/lane_claim.py`.
- The tracker tells the owner how far the goal is. No session claims it, and
  no session starts its work from it.

A session starts from a `lane` issue. It reads the tracker body only to pick
the `slice:` label of a new ticket.

## Setup

### 1. Ask the owner first, in one AskUserQuestion call

Ask each question as checkboxes, with the recommended option marked.

- **Do tooling tickets go on the tracker?** Options: yes, as their own
  `Layer: Tooling` (recommended), or no, they stay off.
  Ask once, so the layer list does not change after the build.
- **Is this format right?** Show a draft of the top issue body (step 3) and
  the layer list (step 4). Options: yes, build it (recommended once the draft
  is shown), or change it first. #81, a retro of the edsim-paper session
  that built the tracker three times, asks for this: "Show the owner the
  tracker format before building it".
- **May the repo get the sync workflow?** It spends Actions minutes on five
  issue events (step 8). `~/CLAUDE.md` section 3 says to ask before you add a
  workflow. Options: yes, add it (recommended when issues change often), or
  no, run the script by hand.

### 2. Start from the finished product

List every part that the finished product needs. Then map the open tickets
onto that list, and file a ticket for each part with none. #81 gives the
reason: the first edsim-paper tracker "was built from the open tickets, so
whole paper parts had no ticket". It names the acknowledgments, the data and
code availability statement, one approval per state, the arXiv form fields,
and the owner's read of the draft.

### 3. The top issue

Its body has these parts, each one short:

- **Goal.** One sentence: the goal is met when every sub-issue is closed.
- **Target.** The date, and what comes after it.
- **Done means.** When one item counts as done, e.g. its PR merged after a
  review that passed.
- **Order.** The layers in time order. A new part goes where it happens in
  time.
- **How to add work.** Give each issue one `slice:` label. The sync script
  does the rest.
- **The recount command**, so a reader can check the bars:

      gh api 'repos/<owner>/<repo>/issues/<n>/sub_issues?per_page=100' --paginate --jq '.[] | "\(.number) \(.title) \(.sub_issues_summary.completed)/\(.sub_issues_summary.total)"'

Pin it: `gh issue pin <n>`.

The sync script never closes the top issue. Close it by hand when all its
layers are closed.

### 4. One layer issue per part, and why

GitHub counts only direct sub-issues. This command shows the count that the
top issue's bar uses:

    gh api repos/<owner>/<repo>/issues/<n> --jq .sub_issues_summary

So a part nested under a part is lost from every bar above its parent. #81
gives the second cause of the rebuilds: with the parts nested, "The bar
showed 11 parts and hid the 17 nested ones".

Layers answer this with three levels only: top issue, then layers, then work
issues. The top bar counts the layers. Each layer has its own bar over its
work issues. Never add a fourth level.

The top bar moves only when a whole layer closes. So it can show no progress
while many work issues inside the layers are closed. Read the layer lines of
the recount command for the detail.

Name each layer `Layer: <part>`, e.g. `Layer: Docs`. The script finds the
layers by title.

### 5. One `slice:` label per issue

Give every work issue exactly one `slice:` label, e.g. `slice:docs`. Make
each label before the migration, with a description. The migration uses the
description as the body of the new layer issue.

    gh label create slice:docs --force --description "The user docs"

The script skips an issue with two `slice:` labels and prints a warning. It
moves an issue with no `slice:` label out of a layer, back under the top
issue. It lists each such issue under the top issue, with the flag to label it.

### 6. The label-to-layer map

Copy `tracker-layers.yml` from this folder to `.github/tracker-layers.yml`.
Set `tracker:` to the top issue's number. The script refuses to run while it
is empty. Then write one line per label, with the title of its layer. The map
holds no layer numbers, so the migration can run again safely.

The script reads only the forms in the template: `tracker: <number>`, the
`layers:` line, and each layer as `"slice:<part>": "<title>"` in double
quotes, indented two spaces. `<part>` is lower-case letters, digits and `-`.
A title holds no `"` and no backslash. Comment and blank lines are skipped.
Any other line, or a key given twice, stops the script with its line number.

### 7. The sync script, and the optional workflow

Copy from this folder, once per repo:

- `tracker_sync.py` to `tools/tracker_sync.py`.
- `tracker.yml` to `.github/workflows/tracker.yml`, only if the owner said
  yes in step 1.

The test stays here. It checks the general copy, and it reads the template
beside it. A repo that changes its copy of the script can copy the test too,
and point it at its own map file.

Each `--sync` run puts the whole tracker in order:

- It moves each issue with one `slice:` label under its layer.
- It moves an issue with no `slice:` label back under the top issue.
- It closes each layer whose issues are all closed, and reopens it if not.
  A layer with no issues closes at once: the script asks whether all its
  issues are closed, and that is true of an empty layer.

The workflow is optional. It runs `--sync` on each of its five issue events.
Without it, run the script by hand from the repo root after issues change:

    python3 tools/tracker_sync.py --sync --dry-run
    python3 tools/tracker_sync.py --sync

The first time, make the layers with the migration. Run each step dry first.
The first dry run lists each issue under the top issue that has no `slice:`
label, with the flag to give it one, e.g.
`#<N> under #<T> has no slice: label (give it one: --label <N>=slice:<part>)`.

    python3 tools/tracker_sync.py --migrate --dry-run
    python3 tools/tracker_sync.py --migrate --dry-run --label <N>=slice:<part>
    python3 tools/tracker_sync.py --migrate --label <N>=slice:<part>
    python3 tools/tracker_sync.py --sync --dry-run

Give one `--label` for each issue the first dry run lists. The docstring of
`tools/tracker_sync.py` has the undo steps.

### 8. What it costs

The workflow runs on five issue events: opened, labeled, unlabeled, closed and
reopened. Each one starts a job on `ubuntu-latest`, so each of those events
spends Actions minutes. Ask the owner before you add it (step 1). A run by
hand costs no minutes.

The workflow runs one job at a time. Each run reads the whole tracker, so a
run that GitHub cancels loses nothing.

## Hands off to

- The owner questions of step 1: `/yw-workflow:need-me` is the format.
- A part of the finished product with no ticket: `/yw-workflow:ship-loop`
  says what a ticket needs, and builds each one.
- The next session needs to know what to do: `/yw-workflow:handoff` and its
  `lane` issues. The tracker shows progress, and a lane says what is next.
