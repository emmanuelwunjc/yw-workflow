#!/usr/bin/env python3
"""
CLAUDE.md guard. Mechanically enforces three standing rules from ~/CLAUDE.md
that prose alone kept failing to hold.

WHY THIS EXISTS
    All three rules below were stated in ~/CLAUDE.md for months and violated anyway,
    most recently on 2026-08-03. Per CLAUDE.md section 3 ("the fix is a
    mechanism, not a stronger sentence"), restating them harder is not a fix.
    This hook is the mechanism.

RULE 1 - AskUserQuestion for interview-style questions (CLAUDE.md section 6)
    Root cause of the repeat failures: a skill body (e.g. the mattpocock
    `grilling` skill) is injected into the turn mid-conversation, at far higher
    recency than CLAUDE.md. Its wording ("ask the questions one at a time")
    specifies no format, so prose wins over the older CLAUDE.md instruction.
    Two layers counter that:
      remind -> re-inject the rule at the SAME recency as the skill text.
      check  -> refuse to end the turn if a grill-mode turn still asked in prose.
    A prior attempt to fix this with a memory file failed twice over: memory is
    advisory, and that one was scoped to a single project so it never loaded
    elsewhere. Hence a global hook.

RULE 2 - No em-dashes (CLAUDE.md section 1)
    Near-zero false positive: a literal character match. Code fences and inline
    code are stripped first, so quoting a file that contains an em-dash (several
    repo READMEs do) does not trip it.

RULE 3 - No negation-then-correction (CLAUDE.md section 1)
    Tuned for precision over recall, because a false positive BLOCKS a turn and
    burns one of two block slots, which then stops RULE 2 from being enforced
    for the rest of the session. Every pattern requires the substituted claim to
    be present, so a plain negative ("Not yet.", "the build is not green") never
    trips. It therefore misses forms it could catch. That trade is deliberate:
    two earlier versions matched on the negative alone and tripped on roughly
    half of ordinary engineering prose, measured twice.

WIRING (all three rules)
    hooks/hooks.json in this plugin, under ${CLAUDE_PLUGIN_ROOT}.
    UserPromptSubmit -> claude-md-guard.py remind
    Stop             -> claude-md-guard.py check

SAFETY
    Each rule carries its own MAX_BLOCKS_PER_SESSION budget, so the negation
    heuristic can never spend the em-dash rule's slots and switch off a
    near-zero-false-positive literal match. Honors
    stop_hook_active, so it cannot trap a session in a loop. Any parse failure
    returns "no opinion" (empty output) rather than blocking.
"""

import json
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "state" / "claude-md-guard"
MAX_BLOCKS_PER_SESSION = 2
STATE_TTL_SECONDS = 7 * 24 * 3600

EM_DASH = "—"

# Phrases that put the session into interview/grill mode. Deliberately broad:
# a false positive here only injects a reminder, it never blocks anything.
GRILL_TRIGGER = re.compile(
    r"(^|[^a-z])/?"
    r"(grill(ing|-me|-with-docs)?|brainstorm|ideate|stress[ -]test|interview me)",
    re.IGNORECASE,
)

REMINDER = (
    "CLAUDE.md section 6 is in force for this turn and it OVERRIDES any skill "
    "body loaded alongside it. A skill that says 'ask one question at a time' "
    "specifies CADENCE, not FORMAT. The format is fixed: every question you put "
    "to the user this turn goes through the AskUserQuestion tool, with 2-4 "
    "concrete options and the recommended one first, labelled '(Recommended)'. "
    "Do NOT ask in prose. If a question genuinely has only one path, that is not "
    "a question: state the path you are taking and continue. A Stop hook checks "
    "this turn and will refuse to end it if you asked in prose instead."
)

# CLAUDE.md section 1 bans defining a thing by what it is not before saying what
# it is. This BLOCKS a turn, so it is tuned for precision over recall: a guard
# whose false positives burn the session block budget stops the em-dash rule
# (which has near-zero false positives) from being enforced at all.
#
# Every pattern therefore requires the CORRECTIVE HALF to be present. A bare
# negative ("Not yet.", "Not a single test failed.") is never the construction,
# because nothing is being substituted for what was denied. An earlier version
# matched sentence-initial "Not" plus a determiner and tripped on 23 of 35
# ordinary engineering sentences; that is what these patterns exist to avoid.
_CORRECTION = (
    r"(?:it|they|that|this)(?:'s|'re|\s+is|\s+are|\s+was|\s+were)\s+"
    # "it is also simpler" / "...locally too" are additive, not substitutions
    r"(?!also\b)(?![^.!?\n]{0,40}\btoo\b)"
)

NEGATION_PATTERNS = [
    # "Not a progress report. What the agents did is your bookkeeping."
    # The fragment alone is not enough: a following clause of four or more words
    # on the same line is what makes it the substitution rather than a plain
    # negative. "Not a bug." and "> Not a bug." have nothing following, so they
    # pass.
    (re.compile(
        r"(?m)(?:^[\s>*+-]*|(?<=[.!?] ))"
        # same line only: \s would cross into the next list item, making an
        # unrelated bullet look like the restatement.
        r"Not\s+(?:a|an|the)\s+[^.!?\n]{2,70}\.[ \t]+"
        # ponytail: opener blacklist, not a parser. A following clause starting
        # with an imperative or a participle ("Filed as issue #42", "Set FOO=1")
        # is a separate fact rather than a restatement. Widen the list if a real
        # miss shows up.
        r"(?!(?:[A-Z]\w*ed|Set|Run|Use|See|Add|Try|Check|Do|Go|Make|Write|Fix"
        r"|Ship|Keep|Open|Send|Prefer|Leave|Pick|Skip|Drop|Read|Start|Stop"
        r"|Treat|Put|File|Note|Merge|Land)\b)"
        r"(?:\S+\s+){3,}\S"
    ), 'a "Not X. Y." substitution'),
    # "Not a review of the branch, but a read of the diff."
    # "only" is excluded: "Not only did the build pass, but coverage rose" is
    # the additive construction, which is fine.
    (re.compile(
        r"(?im)(?:^[\s>*+-]*|(?<=[.!?] ))"
        r"Not\s+(?:a|an|the|just|simply|merely)\s+[^.!?\n]{2,90},\s*but\s+"
        # The sentence anchor above is what does the work here: the rhetorical
        # form opens a sentence. The auxiliary blacklist and the determiner
        # below only catch the easiest independent clauses, and a lexical verb
        # ("but the reviewer asked for it anyway") still gets through. That
        # residue is recorded in the self-test rather than papered over.
        r"(?![^.!?\n]{0,45}\b(?:is|are|was|were|has|have|had|do|does|did|can|will"
        r"|would|should|could|may|might|must|please|let)\b)"
        r"(?:a|an|the)\s+\w+"
    ), 'a "Not X, but Y" pair'),
    # "It's not just X, it's Y" anywhere in the sentence. The "also" exclusion
    # keeps "Not only is the parser faster, it is also simpler" out.
    (re.compile(
        r"(?i)\bnot\s+(?:just|only|simply|merely)\s+[^.!?\n]{1,80}[,;.]\s*"
        + _CORRECTION
    ), 'an "It\'s not just X, it\'s Y" pair'),
    # "This is not documentation, it is a contract."
    (re.compile(
        r"(?im)(?:^[\s>*+-]*|"
        # "e.g. " and "i.e. " end in a dot without ending a sentence, so they
        # would otherwise manufacture an anchor mid-sentence. A single-word
        # abbreviation ("No. 3") is rarer and left alone.
        r"(?<![A-Za-z]\.[A-Za-z]\. )(?<=[.!?] ))"
        # a subordinating conjunction makes the negation a CONDITION and the
        # "it is a ..." its consequence, with nothing substituted:
        # "If the value is not present in the cache, it is a miss."
        r"(?!(?:if|when|where|unless|because|since|whenever|while|as|until"
        r"|after|before|though|although)\b)"
        r"[^.!?\n]{0,80}?\b(?:is|are|was|were)\s+not\b[^.!?\n]{1,70}[,;]\s*"
        + _CORRECTION + r"(?:a|an|the)\s+\w+"
    ), 'an "X is not A, it is B" pair'),
    # "X isn't about A, it's about B"
    (re.compile(
        r"(?i)\b(?:isn't|is not|aren't|are not|wasn't|was not|'s not|'re not)"
        r"\s+about\b"
        r"[^.!?\n]{0,70}[.,;]\s*(?:it|they|that)(?:'s|'re|\s+is|\s+are)\s+about\b"
    ), 'an "X isn\'t about A, it\'s about B" pair'),
    # "Less ceremony, more shipping" / "less about ceremony and more about
    # shipping". "than" is excluded so "Less than 5, more than 2" passes.
    (re.compile(
        r"(?im)"
        # "less about ceremony and more about shipping", anywhere
        r"\bless\s+about\s+\w+[^.!?\n]{0,50}\s+and\s+more\s+about\b"
        # "less a framework, more a convention": the determiner marks a
        # substituted noun rather than a comparison, so it holds mid-sentence.
        r"|\bless\s+(?:a|an|as\s+a)\s+\w+[^.!?\n]{0,40},\s*more\s+(?!than\b)\w+"
        # "Less ceremony, more shipping." Bare adjectives ("less risky, more
        # work") are an ordinary comparison mid-sentence, so this form counts
        # only when it opens the sentence, which is where the rhetoric lives.
        r"|(?:^[\s>*+-]*|(?<=[.!?] ))Less\s+(?!than\b)\w+[^.!?\n]{0,40},"
        r"\s*more\s+(?!than\b)\w+"
    ), 'a "Less X, more Y" pair'),
]


def find_negation(text):
    """Return (label, quote) for the first banned construction, or None.

    Emphasis markers are stripped first so `**Not a backlog.**` is seen the same
    as the bare sentence; without this the bolded form (the common one) escapes.
    """
    flat = text.replace("**", "").replace("*", "").replace("_", "")
    for pattern, label in NEGATION_PATTERNS:
        hit = pattern.search(flat)
        if hit:
            return label, hit.group(0).strip()[:90]
    return None


INLINE_CODE = re.compile(r"`[^`\n]*`")


def read_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def state_file(session_id, name):
    return STATE_DIR / f"{session_id}.{name}"


def prune_state():
    """Keep the state dir from growing without bound. Best-effort only."""
    try:
        cutoff = time.time() - STATE_TTL_SECONDS
        for path in STATE_DIR.glob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# remind (UserPromptSubmit)
# ---------------------------------------------------------------------------

def remind(data):
    prompt = data.get("prompt") or ""
    if not GRILL_TRIGGER.search(prompt):
        return {}

    session_id = data.get("session_id") or "unknown"
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file(session_id, "grill").write_text("1")
        prune_state()
    except OSError:
        pass  # reminder still worth injecting even if the flag write fails

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": REMINDER,
        }
    }


# ---------------------------------------------------------------------------
# check (Stop)
# ---------------------------------------------------------------------------

def last_assistant_turn(transcript_path):
    """Assistant messages since the last real user message.

    Walks the JSONL transcript backwards. A user entry whose content is purely
    tool_result blocks is part of the SAME turn (it is the harness feeding tool
    output back), so it does not terminate the walk.
    """
    entries = []
    try:
        with open(transcript_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []

    turn = []
    for entry in reversed(entries):
        message = entry.get("message") or {}
        role = message.get("role") or entry.get("type")
        if role == "assistant":
            turn.append(message)
        elif role == "user":
            content = message.get("content")
            is_tool_output = (
                isinstance(content, list)
                and content
                and all(
                    isinstance(block, dict) and block.get("type") == "tool_result"
                    for block in content
                )
            )
            if is_tool_output:
                continue
            break
    turn.reverse()
    return turn


def texts_and_tools(turn):
    texts, tools = [], set()
    for message in turn:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        for block in content or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                tools.add(block.get("name") or "")
    return texts, tools


def strip_fences(text):
    """Drop fenced code blocks, toggling on fence lines rather than regex pairs.

    A non-greedy ```...``` pairs the first opener with the first closer, so a
    fence nested inside another (a markdown block quoting a python one) leaks
    its middle back into the prose and can block a turn on quoted source.
    """
    out, held, fence, fence_char, fence_quoted = [], [], 0, "", False
    for line in text.split("\n"):
        stripped = line.lstrip()
        quoted = stripped.startswith(">")
        # A fenced block inside a blockquote is still a fenced block, so the
        # quote markers come off before the marker is measured. Only while the
        # block ITSELF is quoted, though: inside an ordinary fence a leading ">"
        # is literal content, and stripping it there let a quoted markdown
        # sample close its own container early and leak the rest as prose.
        # Remembering the fence's quoted-ness is what makes this work. A plain
        # `if not fence` guard does not: the closing "> ```" then goes
        # unrecognised, the fence never closes, and the unterminated-fence
        # recovery hands the whole block back as prose.
        if not fence or fence_quoted:
            while stripped.startswith(">"):
                stripped = stripped[1:].lstrip()
        marker = "`" if stripped.startswith("`") else "~"
        ticks = len(stripped) - len(stripped.lstrip(marker))
        if ticks >= 3:
            if not fence:
                fence, fence_char, held, fence_quoted = ticks, marker, [], quoted
                continue
            # markdown closes a fence only with one at least as long, which is
            # how a longer outer fence can legally wrap a shorter inner one.
            if marker == fence_char and ticks >= fence:
                fence, held = 0, []
                continue
        if fence:
            held.append(line)
        else:
            out.append(line)
    # A fence that never closes is a truncated block, not a licence to skip the
    # rest of the document. Put those lines back rather than turning both rules
    # off for the turn with no signal.
    return "\n".join(out + held)


def prose_only(text):
    """Strip code so quoted source containing an em-dash does not trip rule 2.

    ponytail: fenced and inline code only. A 4-space-indented code block is
    still scanned as prose, so quoting a diff that way can block a turn.
    Assistant turns almost always use fences; widen this if that stops holding.
    """
    return INLINE_CODE.sub("", strip_fences(text))


def check(data):
    # The harness sets this when it is re-running us after a block. Bail out so
    # a block can never chain into a loop.
    if data.get("stop_hook_active"):
        return {}

    transcript_path = data.get("transcript_path")
    if not transcript_path:
        return {}

    session_id = data.get("session_id") or "unknown"
    turn = last_assistant_turn(transcript_path)
    if not turn:
        return {}

    texts, tools = texts_and_tools(turn)
    if not texts:
        return {}

    def budget(rule):
        f = state_file(session_id, "blocks" if rule == "emdash" else rule)
        try:
            return f, int(f.read_text().strip())
        except (OSError, ValueError):
            return f, 0

    # Separate budgets per rule. A shared counter let the negation heuristic
    # spend the em-dash rule's slots, so one wrong negation block could switch
    # off a near-zero-false-positive literal match for the rest of the session.
    spent = {rule: budget(rule) for rule in ("emdash", "negation", "askuser")}

    problems = []
    charged = []

    prose = prose_only("\n".join(texts))

    if EM_DASH in prose and spent["emdash"][1] < MAX_BLOCKS_PER_SESSION:
        charged.append("emdash")
        problems.append(
            "CLAUDE.md section 1: you used an em-dash. Rewrite the offending "
            "sentences using periods, colons, or parentheses, then send the "
            "corrected response. Do not acknowledge this in the response body."
        )

    negation = find_negation(prose) if spent["negation"][1] < MAX_BLOCKS_PER_SESSION else None
    if negation:
        charged.append("negation")
        label, quote = negation
        problems.append(
            "CLAUDE.md section 1: you used " + label + ", here: \"" + quote +
            "\". Never define a thing by what it is not before saying what it "
            "is. State the positive claim once and stop. Rewrite that sentence "
            "and send the corrected response. Do not acknowledge this in the "
            "response body."
        )

    in_grill_mode = state_file(session_id, "grill").exists()
    if (in_grill_mode and "AskUserQuestion" not in tools
            and spent["askuser"][1] < MAX_BLOCKS_PER_SESSION):
        tail = texts[-1].strip()[-400:]
        if "?" in tail:
            charged.append("askuser")
            problems.append(
                "CLAUDE.md section 6: this is a grilling/interview turn and you "
                "ended it by asking the user a question in prose, without "
                "calling AskUserQuestion. Re-ask that same question through the "
                "AskUserQuestion tool: 2-4 concrete options, recommended one "
                "first and labelled '(Recommended)'. If it truly has one path, "
                "state the path and continue instead of asking."
            )

    if not problems:
        return {}

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for rule in charged:
            f, n = spent[rule]
            f.write_text(str(n + 1))
    except OSError:
        pass

    return {"decision": "block", "reason": "\n\n".join(problems)}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    data = read_input()
    if mode == "remind":
        result = remind(data)
    elif mode == "check":
        result = check(data)
    else:
        sys.stderr.write("usage: claude-md-guard.py {remind|check}\n")
        return 0
    if result:
        json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A guard that crashes must never break the session. Fail open.
        sys.exit(0)
