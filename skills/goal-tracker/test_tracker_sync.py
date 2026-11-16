#!/usr/bin/env python3
"""Offline self-check for tracker_sync.py. Run: python3 test_tracker_sync.py

Each case feeds a snapshot of the tracker to a pure function and asserts the
exact API calls. No network. The issue numbers are made up for the cases.
hooks/goal-tracker-selftest.py runs this file, so CI runs it too.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tracker_sync  # noqa: E402

TEMPLATE = HERE / "tracker-layers.yml"
TRACKER = 100
# The layers of the template map file, tracker-layers.yml.
CONFIG = {"slice:core": "Layer: Core", "slice:docs": "Layer: Docs",
          "slice:tests": "Layer: Tests", "slice:release": "Layer: Release",
          "slice:tooling": "Layer: Tooling"}
LAYERS = {"slice:core": 201, "slice:docs": 202, "slice:tests": 203,
          "slice:release": 204, "slice:tooling": 205}


def issue(number, labels, state="open", title=None):
    return {"number": number, "id": 9000 + number, "state": state,
            "title": title or f"Issue {number}", "labels": labels}


def layer_issue(label, state="open"):
    return issue(LAYERS[label], [label], state, CONFIG[label])


def snapshot(**kids):
    """Children of every layer and of the tracker. Keys: l201, ..., t100."""
    children = {n: [] for n in [*LAYERS.values(), TRACKER]}
    for key, value in kids.items():
        children[int(key[1:])] = value
    children[TRACKER] = children[TRACKER] + [layer_issue(lb) for lb in LAYERS]
    return children


STATES = {n: "open" for n in LAYERS.values()}


def sync(issues, children, states=STATES, layers=LAYERS):
    return tracker_sync.sync_plan(issues, children, layers, states, TRACKER, CONFIG)


def add(parent, number):
    return ("POST", f"issues/{parent}/sub_issues",
            {"sub_issue_id": 9000 + number, "replace_parent": True})


def state(layer, value):
    return ("PATCH", f"issues/{layer}", {"state": value})


# Every layer below except the ones a case is about holds one open issue,
# so only the layers under test change state.
def busy(**kids):
    filler = {f"l{n}": [issue(500 + n, [lb])] for lb, n in LAYERS.items()}
    filler.update(kids)
    return snapshot(**filler)


def filler_issues(*skip):
    return [issue(500 + n, [lb]) for lb, n in LAYERS.items() if n not in skip]


def map_file(text):
    """Write text to a temporary map file and return its path."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


# Sync: moves

def test_issue_under_tracker_moves_into_its_layer():
    x = issue(301, ["slice:core", "housekeeping"])
    calls, _ = sync(filler_issues() + [x], busy(t100=[x]))
    assert calls == [add(201, 301)], calls


def test_issue_with_no_parent_moves_into_its_layer():
    calls, _ = sync(filler_issues() + [issue(302, ["slice:tests"])], busy())
    assert calls == [add(203, 302)], calls


def test_consistent_tracker_needs_no_call():
    x = issue(301, ["slice:core"])
    calls, _ = sync(filler_issues(201) + [x], busy(l201=[x]))
    assert calls == [], calls


def test_relabel_moves_layers_and_sets_both_states():
    # 303 was the only open issue in 201. 202 held only closed issues.
    x = issue(303, ["slice:docs"])
    states = {**STATES, 202: "closed"}
    children = busy(l201=[issue(304, ["slice:core"], "closed"), x],
                    l202=[issue(305, ["slice:docs"], "closed")])
    issues = filler_issues(201, 202) + [x, issue(304, ["slice:core"], "closed"),
                                        issue(305, ["slice:docs"], "closed")]
    calls, _ = sync(issues, children, states)
    assert calls == [add(202, 303), state(201, "closed"), state(202, "open")], calls


def test_issue_with_no_slice_label_leaves_its_layer_for_the_tracker():
    closed = issue(304, ["slice:core"], "closed")
    children = busy(l201=[closed, issue(303, ["housekeeping"])])
    calls, _ = sync(filler_issues(201) + [closed], children)
    assert calls == [add(TRACKER, 303), state(201, "closed")], calls


def test_two_slice_labels_are_skipped_with_a_warning():
    x = issue(306, ["slice:docs", "slice:core"])
    calls, warnings = sync(filler_issues() + [x], busy(t100=[x]))
    assert calls == [], calls
    assert any("#306" in w and "slice:docs" in w and "slice:core" in w
               for w in warnings), warnings


def test_label_without_a_layer_is_skipped_with_a_warning():
    layers = {k: v for k, v in LAYERS.items() if k != "slice:release"}
    states = {n: "open" for n in layers.values()}
    x = issue(307, ["slice:release"])
    calls, warnings = sync(filler_issues() + [x], busy(t100=[x]), states, layers)
    assert calls == [], calls
    assert any("#307" in w and "slice:release" in w for w in warnings), warnings


def test_layer_and_tracker_are_never_moved():
    orphan = issue(300, ["slice:core"], title="Layer: Core")  # not under the tracker yet
    tracker = issue(TRACKER, ["slice:core"], title="Goal")
    issues = filler_issues() + [layer_issue(lb) for lb in LAYERS] + [orphan, tracker]
    calls, _ = sync(issues, busy())
    assert calls == [], calls


def test_unlabeled_tracker_child_is_listed_with_the_flag_to_label_it():
    # The general copy proposes no label: it has no words to guess one from.
    x = issue(308, [], "closed", "A figure of the docs")
    calls, warnings = sync(filler_issues(), busy(t100=[x]))
    assert calls == [], calls
    assert any("#308" in w and "--label 308=slice:<part>" in w for w in warnings), warnings
    assert not any("slice:docs" in w for w in warnings), warnings


# Sync: layer state

def test_closed_issue_into_layer_of_closed_issues_closes_it():
    done = issue(305, ["slice:docs"], "closed")
    x = issue(309, ["slice:docs"], "closed")
    calls, _ = sync(filler_issues(202) + [done, x], busy(l202=[done], t100=[x]))
    assert calls == [add(202, 309), state(202, "closed")], calls


def test_closed_layer_with_an_open_issue_reopens():
    x = issue(305, ["slice:docs"])
    states = {**STATES, 202: "closed"}
    calls, _ = sync(filler_issues(202) + [x], busy(l202=[x]), states)
    assert calls == [state(202, "open")], calls


def test_last_issue_closed_closes_the_layer():
    x = issue(303, ["slice:core"], "closed")
    calls, _ = sync(filler_issues(201) + [x], busy(l201=[x]))
    assert calls == [state(201, "closed")], calls


def test_layer_with_no_issues_closes():
    # all() of an empty set is true, so an empty open layer closes at once.
    calls, _ = sync(filler_issues(201), busy(l201=[]))
    assert calls == [state(201, "closed")], calls


# Finding layers

def test_find_layers_matches_titles_under_the_tracker():
    children = [issue(201, [], title="Layer: Core"), issue(301, []),
                issue(205, [], title="Layer: Tooling"), issue(9, [], title="Layer: Posters")]
    assert tracker_sync.find_layers(children, CONFIG) == {
        "slice:core": 201, "slice:tooling": 205}


def test_two_layers_with_one_title_fail():
    children = [issue(201, [], title="Layer: Core"), issue(206, [], title="Layer: Core")]
    try:
        tracker_sync.find_layers(children, CONFIG)
    except ValueError as err:
        assert "#201" in str(err) and "#206" in str(err) and "\n" not in str(err), err
    else:
        raise AssertionError("two children with one layer title must raise ValueError")


# Migration

def test_migration_reuses_attaches_or_creates_each_layer():
    under = [layer_issue("slice:core")]
    orphan = issue(206, ["slice:docs"], title="Layer: Docs")
    wrong_label = issue(207, ["slice:tooling"], title="Layer: Tests")
    labeled = [layer_issue("slice:core"), orphan, issue(301, ["slice:core"]), wrong_label]
    layers, calls, create = tracker_sync.plan_layers(CONFIG, under, labeled, TRACKER)
    assert layers == {"slice:core": 201, "slice:docs": 206}, layers
    assert calls == [add(TRACKER, 206)], calls
    assert create == ["slice:tests", "slice:release", "slice:tooling"], create


def test_label_pairs_parse_and_reject_unknown_labels():
    assert tracker_sync.parse_label_pairs(["301=slice:tooling", "302=slice:docs"], CONFIG) == {
        301: "slice:tooling", 302: "slice:docs"}
    for bad in (["301=slice:posters"], ["three=slice:tooling"], ["301"]):
        try:
            tracker_sync.parse_label_pairs(bad, CONFIG)
        except ValueError as err:
            assert bad[0] in str(err), err
        else:
            raise AssertionError(f"{bad} must raise ValueError")


# The map file

def test_template_names_every_layer_once_the_tracker_is_set():
    text = TEMPLATE.read_text(encoding="utf-8").replace("\ntracker:", "\ntracker: 7", 1)
    tracker, config = tracker_sync.load_config(map_file(text))
    assert tracker == 7, tracker
    assert config == CONFIG, config


def test_template_as_shipped_has_no_tracker_number():
    try:
        tracker_sync.load_config(TEMPLATE)
    except ValueError as err:
        assert "tracker" in str(err), err
    else:
        raise AssertionError("the template must refuse to run until tracker: is set")


def test_tracker_that_is_no_positive_number_is_refused():
    for value in ("0", "-3", "abc"):
        try:
            tracker_sync.load_config(map_file(f'tracker: {value}\n"slice:core": "Layer: Core"\n'))
        except ValueError as err:
            assert "tracker" in str(err), err
        else:
            raise AssertionError(f"tracker: {value} must raise ValueError")


def test_map_file_reads_one_pair_per_line_and_ignores_nesting():
    text = ('tracker: 12\nlayers:\n  "slice:core": "Layer: Core"\n'
            '    slice:release-notes: Layer: Release notes\n')
    tracker, config = tracker_sync.load_config(map_file(text))
    assert tracker == 12, tracker
    assert config == {"slice:core": "Layer: Core",
                      "slice:release-notes": "Layer: Release notes"}, config


def test_a_key_with_no_value_never_takes_the_next_line():
    tracker, config = tracker_sync.load_config(
        map_file("tracker: 5\nslice:core:\nslice:docs: Layer: Docs\n"))
    assert config == {"slice:docs": "Layer: Docs"}, config


def test_map_file_reads_single_quotes():
    tracker, config = tracker_sync.load_config(
        map_file("tracker: '12'\n'slice:core': 'Layer: Core'\n"))
    assert (tracker, config) == (12, {"slice:core": "Layer: Core"}), (tracker, config)


def test_map_file_reads_a_trailing_comment():
    tracker, config = tracker_sync.load_config(
        map_file('tracker: 12  # the top issue\n"slice:core": "Layer: Core" # first\n'
                 "slice:docs: Layer: Docs  # second\n"))
    assert tracker == 12, tracker
    assert config == {"slice:core": "Layer: Core", "slice:docs": "Layer: Docs"}, config


def expect_map_error(text, *words):
    try:
        tracker_sync.load_config(map_file(text))
    except ValueError as err:
        assert all(w in str(err) for w in words), err
    else:
        raise AssertionError(f"{text!r} must raise ValueError")


def test_map_line_that_does_not_parse_stops_with_the_line():
    expect_map_error('tracker: 12\n"slice:core: "Layer: Core"\n', '"slice:core: "Layer: Core"')
    expect_map_error("tracker: 12\n- slice:core\n", "- slice:core")
    expect_map_error("tracker: 12\n'slice:core': \"Layer: Core'\n", "\"Layer: Core'")


def test_map_key_with_no_slice_prefix_stops_with_the_line():
    expect_map_error('tracker: 12\n"core": "Layer: Core"\n', '"core": "Layer: Core"', "slice:")


def test_missing_map_file_stops_with_a_clear_message():
    try:
        tracker_sync.load_config(Path(map_file("")).with_name("no-such-map.yml"))
    except ValueError as err:
        assert "no-such-map.yml" in str(err), err
    else:
        raise AssertionError("a missing map file must raise ValueError")


def test_label_case_that_differs_from_the_map_still_moves():
    x = issue(301, ["Slice:Core"])
    calls, warnings = sync(filler_issues() + [x], busy(t100=[x]))
    assert calls == [add(201, 301)], (calls, warnings)


def test_slice_label_not_in_the_map_warns_that_it_is_not_in_the_map():
    # The script fetches issues by the labels of the map, so this one shows
    # up only as a child. It leaves its layer, with the right warning.
    x = issue(301, ["slice:posters"])
    calls, warnings = sync(filler_issues(), busy(l201=[x, issue(701, ["slice:core"])]))
    assert calls == [add(TRACKER, 301)], calls
    assert any("#301" in w and "slice:posters" in w and "not in the map" in w
               for w in warnings), warnings
    assert not any("has no slice: label" in w for w in warnings), warnings


def test_default_map_file_is_relative_to_the_repo_root():
    assert tracker_sync.DEFAULT_CONFIG == Path(".github/tracker-layers.yml"), \
        tracker_sync.DEFAULT_CONFIG


failed = []
for name, test in list(globals().items()):
    if name.startswith("test_"):
        try:
            test()
        except Exception as err:  # report every case, then fail
            failed.append(name)
            print(f"FAIL {name}: {type(err).__name__}: {str(err)[:200]}")
if failed:
    sys.exit(1)
print("ok: test_tracker_sync")
