#!/usr/bin/env python3
"""Self-test for the negation-then-correction detector in claude-md-guard.py.

A blocking guard is only worth having if it can fail on the right input and
stay quiet on the wrong one. The MUST_TRIP cases are real sentences that
shipped past this guard before it existed; the MUST_NOT_TRIP cases are plain
factual negatives that must never block a turn.

Run: ./hooks/claude-md-guard-selftest.py
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "guard", Path(__file__).with_name("claude-md-guard.py")
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

MUST_TRIP = [
    # one per pattern, plus the forms that shipped past this guard before it
    # existed. Each entry names the pattern it is the unique cover for, so the
    # mutation check below can prove no pattern is dead weight.
    "Not a progress report. What the agents did is your bookkeeping.",      # 0
    "**Not a backlog.** Tickets nobody waits on stay in the tracker.",      # 0
    "Not a review of the whole branch. A read of the diff and nothing more.",  # 0
    "It runs in a terminal. Not a chatbot, but a colleague that edits files.",  # 1
    "Not simply an agent, but an entire team.",                            # 1
    "It's not just X, it's Y.",                                            # 2
    "This is not documentation, it is a contract.",                        # 3
    "It is not a bug; it is a feature.",                                   # 3
    "This isn't about speed, it's about correctness.",                     # 4
    "The skill is not about speed. It is about correctness.",              # 4
    "Less ceremony, more shipping.",                                       # 5
    "Less about ceremony and more about shipping.",                        # 5
    "It is less a framework, more a convention.",                          # 5
]

# Deliberately NOT caught, recorded so the trade is visible rather than
# forgotten. Each needs semantics a regex does not have: separating a restated
# identity ("it enforces it") from a stated consequence ("it flakes 1 in 20")
# would need to know which verb substitutes and which explains. Catching them
# cost a ~49% false-positive rate on ordinary prose, measured twice.
KNOWN_MISSES = [
    # the e.g./i.e. anchor exclusion also covers "p.m." and "U.S.", so a real
    # sentence boundary after one of those is not seen. Fail-open direction.
    "We met at 5 p.m. This is not documentation, it is a contract.",
    # mid-sentence "not X, but Y". Anchoring pattern 1 to sentence start is what
    # keeps "It is not a bug, but the docs describe the old behaviour" out, and
    # the rhetorical form lives at the start of a sentence anyway.
    "This is not a progress report, but a queue of decisions for you.",
    "The hook does not restate the rule, it enforces it.",
    "You don't get a report, you get a decision queue.",
    "This is less risky, more work, and it lands next week.",
]

# Recorded false positives: sentences this WILL wrongly block. Separating
# "but a colleague" (a substituted noun phrase) from "but the team decided"
# (an independent clause) needs a part-of-speech tag, which a regex does not
# have. Written down so the residue is visible rather than believed fixed. The
# cost is bounded: each rule now carries its own block budget, so a wrong
# negation block cannot disable the em-dash rule.
KNOWN_FALSE_POSITIVES = [
    # sentence-initial "Not X, but <independent clause>". The auxiliary
    # blacklist cannot see a lexical verb.
    "Not a full rewrite, but the team decided to redo the parser anyway.",
    "Not a hard requirement, but the reviewer asked for it anyway.",
    "Not an outage, but the error rate doubled for ten minutes.",
    # the imperative opener list is a blacklist, so any verb outside it leaks
    "Careful! Not a safe operation. Take a backup before you run it.",
    'The server replied "this is not a valid token, it is a refresh token".',
]

# Every one of these is ordinary engineering prose. A false positive BLOCKS a
# turn and burns one of two block slots, which then stops the em-dash rule from
# being enforced for the rest of the session, so this list is the load-bearing
# half of the test.
MUST_NOT_TRIP = [
    # round 4 wrote these blind, before reading this list
    "The test is not deterministic, it flakes about 1 in 20 runs.",
    "The cache is not warm, it needs a rebuild before the benchmark means anything.",
    "This does not compile, it errors on line 4 of the generated header.",
    "The lock is not held, it blocks instead of returning EAGAIN.",
    "The migration did not run, it exits early when DATABASE_URL is unset.",
    "The socket is not closed, it leaks a file descriptor per request.",
    "The build is not reproducible, it embeds a timestamp.",
    "The result is not cached, it recomputes on every call.",
    "# The buffer is not resized, it reuses the arena allocation.",
    "Does not mutate the input, it returns a new list.",
    "fix: the retry loop does not reset the backoff, it doubles forever.",
    "We spent less time on docs and more time on tests this sprint.",
    "The rewrite has less code and more tests than the original.",
    "ERROR: config is not readable, it may be owned by root.",
    # copula-completed negatives. The previous list had none, so the branch
    # that survived the last cut was untested against ordinary prose.
    "The path is not absolute; it is resolved relative to CWD.",
    "The tests are not hermetic; they are hitting the real S3 bucket.",
    "The docs are not wrong, they are describing v1 and we shipped v2.",
    "The field is not optional, it is required by the schema.",
    "The job is not idempotent, it is safe to run once only.",
    # imperatives, which are what instructional prose is made of
    "Do not re-read these files; they are loaded at session start.",
    "Do not run migrations by hand; that is what the deploy job is for.",
    "Do not edit the generated file; it is overwritten on every build.",
    # "but" opening an independent clause
    "That is not an issue, but for multi-voice scores it can produce chords.",
    "It is not the fastest path, but it is the one we can debug at 3am.",
    "Not a blocker, but we should fix it before the release.",
    "Not yet.",
    "Not sure.",
    "Not really.",
    "Not found.",
    "Not implemented.",
    "Not started.",
    "Not only did the build pass, but the coverage went up too.",
    "Not only is the parser faster, it is also simpler.",
    "Not this time, because the branch is frozen until review lands.",
    "Not a single test failed.",
    "Not a lot of people know that git worktree exists.",
    "- Not a blocker. Filed as issue #42.",
    "* Not the default. Set FOO=1 to enable it.",
    "> Not a bug.",
    "Less than 5 items, more than 2, so the median is stable.",
    "Not all tests pass yet, so the branch is not ready.",
    "Not every caller needs the guard.",
    "The build is not green.",
    "This does not hardcode the path.",
    "A review is by someone who did not write the change.",
    "It plans. Building starts only once the map is done.",
    "Do not chart what you cannot see.",
    "Never commit straight to main, even solo.",
    "No jargon. No internal names without saying what they are.",
    "An agent reviewing its own work is a self-check.",
    "Green CI is not a review. It proves the tests pass, and that is a "
    "different claim from matching what the issue asked for.",
]

failures = []
for text in MUST_TRIP:
    if guard.find_negation(text) is None:
        failures.append("MISSED (should have tripped): " + text)
for text in MUST_NOT_TRIP:
    hit = guard.find_negation(text)
    if hit is not None:
        failures.append("FALSE POSITIVE on: " + text + "\n    matched: " + repr(hit))

# Code must never be scanned as prose, and prose must never be swallowed as
# code. Every one of these was a real bug that silently switched a rule off or
# blocked a turn over quoted source, so each keeps a case.
FENCE_CASES = [
    ("plain fence is code",
     "```\nNot a store. A pointer to it and nothing more.\n```", False),
    ("tilde fence is code",
     "~~~\nNot a store. A pointer to it and nothing more.\n~~~", False),
    ("blockquoted fence is code",
     "> ```\n> Not a store. A pointer to it and nothing more.\n> ```", False),
    ("a quoted fence INSIDE a plain fence does not close it early",
     "```\n> ```\n> sample\nNot a store. A pointer to it and nothing more.\n```",
     False),
    ("~~~ does not close a ``` fence",
     "```\n~~~\nNot a store. A pointer to it and nothing more.\n```", False),
    ("an unterminated fence gives its prose back rather than hiding it",
     "```py\nx = 1\n\nNot a store. A pointer to it and nothing more.\n", True),
    ("a stray inline backtick does not eat the following lines",
     "Use the `--force flag here.\nNot a store. A pointer to it and nothing more.",
     True),
    # Accepted trade, pinned so a future change to it is deliberate: CommonMark
    # treats "> " inside a code block as literal, so a plain fence whose only
    # closer is quoted never closes, and the unterminated-fence recovery hands
    # its contents back as prose.
    ("a plain fence closed only by a quoted marker falls back to prose",
     "```\nNot a store. A pointer to it and nothing more.\n> ```", True),
    ("blockquoted prose is still prose",
     "> Not a store. A pointer to it and nothing more.", True),
]
for name, text, should_trip in FENCE_CASES:
    if bool(guard.find_negation(guard.prose_only(text))) != should_trip:
        failures.append("FENCE: %s (expected trip=%s)" % (name, should_trip))

# A pattern no case uniquely covers is dead weight that can never make this
# test fail. Disable each in turn and require at least one MUST_TRIP to go dark.
import re as _re
NEVER = _re.compile(r"(?!x)x")
originals = list(guard.NEGATION_PATTERNS)
for i in range(len(originals)):
    guard.NEGATION_PATTERNS = [
        (NEVER, lbl) if j == i else (pat, lbl)
        for j, (pat, lbl) in enumerate(originals)
    ]
    if all(guard.find_negation(t) for t in MUST_TRIP):
        failures.append(
            "PATTERN %d (%s) is uncovered: the suite still passes with it "
            "disabled, so it can never make this test fail." % (i, originals[i][1])
        )
guard.NEGATION_PATTERNS = originals

for text in KNOWN_FALSE_POSITIVES:
    if not guard.find_negation(text):
        print("NOTE: a recorded false positive no longer trips, which is an "
              "improvement: " + text)

for text in KNOWN_MISSES:
    if guard.find_negation(text):
        print("NOTE: a recorded gap is now caught, which is an improvement: " + text)

if failures:
    print("\n".join(failures))
    print("\nRESULT: %d failed of %d cases"
          % (len(failures), len(MUST_TRIP) + len(MUST_NOT_TRIP) + len(FENCE_CASES)))
    sys.exit(1)
print("claude-md-guard: %d cases pass (%d trip, %d stay quiet, %d code-fence), "
      "and all %d patterns are uniquely covered"
      % (len(MUST_TRIP) + len(MUST_NOT_TRIP) + len(FENCE_CASES), len(MUST_TRIP),
         len(MUST_NOT_TRIP), len(FENCE_CASES), len(guard.NEGATION_PATTERNS)))
