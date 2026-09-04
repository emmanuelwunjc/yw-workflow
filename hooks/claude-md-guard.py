#!/usr/bin/env python3
"""
CLAUDE.md guard. Mechanically enforces two standing rules from ~/CLAUDE.md that
prose alone kept failing to hold.

WHY THIS EXISTS
    Both rules below were stated in ~/CLAUDE.md for months and violated anyway,
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

WIRING (~/.claude/settings.json)
    UserPromptSubmit -> claude-md-guard.py remind
    Stop             -> claude-md-guard.py check

SAFETY
    Never blocks more than MAX_BLOCKS_PER_SESSION times per session, and honors
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

FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]*`")


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


def prose_only(text):
    """Strip code so quoted source containing an em-dash does not trip rule 2."""
    return INLINE_CODE.sub("", FENCED_CODE.sub("", text))


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

    blocks_file = state_file(session_id, "blocks")
    try:
        blocked_so_far = int(blocks_file.read_text().strip())
    except (OSError, ValueError):
        blocked_so_far = 0
    if blocked_so_far >= MAX_BLOCKS_PER_SESSION:
        return {}

    problems = []

    if EM_DASH in prose_only("\n".join(texts)):
        problems.append(
            "CLAUDE.md section 1: you used an em-dash. Rewrite the offending "
            "sentences using periods, colons, or parentheses, then send the "
            "corrected response. Do not acknowledge this in the response body."
        )

    in_grill_mode = state_file(session_id, "grill").exists()
    if in_grill_mode and "AskUserQuestion" not in tools:
        tail = texts[-1].strip()[-400:]
        if "?" in tail:
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
        blocks_file.write_text(str(blocked_so_far + 1))
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
