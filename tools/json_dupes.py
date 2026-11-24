"""Find keys named twice in one JSON object, at any level.

json.loads keeps the last of two equal keys and says nothing, so a merge
that leaves two "SessionStart" blocks in hooks/hooks.json silently drops
every hook in the first. A merge of the unpushed-branches branch nearly
dropped the handoff shape check this way. `duplicate_keys()` returns one
line per duplicate, and an empty list when there is none.
tools/check-repo.py runs it on hooks/hooks.json.
Self-test: hooks/json-dupes-selftest.py.
"""
import json


def duplicate_keys(text):
    found = []

    def pairs(items):
        keys = [k for k, _ in items]
        found.extend("duplicate key: %s" % k for k in sorted(set(keys)) if keys.count(k) > 1)
        return dict(items)

    json.loads(text, object_pairs_hook=pairs)
    return found
