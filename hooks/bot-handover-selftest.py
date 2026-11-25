#!/usr/bin/env python3
"""Self-test for bot-handover.py (issue #336).

Each "box N" case checks acceptance box N of #336. The fixtures (the temp
bot home, the transcript and the stub `orca`) are in bot_handover_testkit.py.

Run: ./hooks/bot-handover-selftest.py
"""
import time

from bot_handover_testkit import (HOUR, LIMIT, NEAR, T0, Env, asks_file,
                                  asks_new_chat, check, finish, load_hook)

# Box 1: near the limit, chat old enough: notice to write the handoff.
e = Env(NEAR, chat_age_hours=5)
text = e.run()
check("box 1: near the limit asks for the handoff file and pointer",
      asks_file(text) and "MEMORY.md" in text, repr(text))
check("box 1: below the limit, no word of a wind-down notice",
      "wind-down" not in text, repr(text))
check("box 1: the stub orca was asked with --all --json",
      e.calls.exists()
      and e.calls.read_text().split() == ["bot", "chats", "--all", "--json"])

# Box 5: without a fresh, named handoff file, new-chat is never asked for.
e = Env(NEAR, chat_age_hours=5)
e.handoff(age_hours=6)          # older than the chat: the last one
check("box 5: only an old handoff file, no new-chat", asks_file(e.run()))
e = Env(NEAR, chat_age_hours=5)
e.handoff(pointer=False)        # fresh, but MEMORY.md does not name it
check("box 5: fresh file without a MEMORY.md pointer, no new-chat",
      asks_file(e.run()))
e = Env(NEAR, chat_age_hours=5)
e.handoff(name="handoff-cutover-ready.md")  # a living doc, not a dated handoff
check("box 5: an undated handoff doc is no handoff", asks_file(e.run()))
e = Env(NEAR, chat_age_hours=5)
(e.bot / "MEMORY.md").unlink()
e.handoff(pointer=False)
check("box 5: no MEMORY.md, no new-chat", asks_file(e.run()))

# Box 1 again: with a fresh file and its pointer, run new-chat.
e = Env(NEAR, chat_age_hours=5)
e.handoff()
check("box 1: fresh handoff and pointer asks for new-chat",
      asks_new_chat(e.run()))
e = Env(NEAR, chat_age_hours=5)
e.handoff(name="handoff-2026-11-25a.md", age_hours=2)
e.handoff(name="handoff-2026-11-25b.md", age_hours=1)
check("box 1: of two fresh files, the newest is named",
      asks_new_chat(e.run(), "handoff-2026-11-25b.md"))

# The same, in the same turn: PostToolBatch says it once per chat.
e = Env(NEAR, chat_age_hours=5)
e.handoff()
first = e.run(event="PostToolBatch")
second = e.run(event="PostToolBatch")
check("PostToolBatch asks for new-chat once the handoff exists",
      asks_new_chat(first), repr(first))
check("PostToolBatch does not repeat it", second is None, repr(second))
check("PostToolBatch asks orca once per chat", e.orca_calls() == 1,
      e.orca_calls())
check("UserPromptSubmit still repeats it each turn", asks_new_chat(e.run()))
e = Env(NEAR, chat_age_hours=5)
text = e.run(event="PostToolBatch")
check("PostToolBatch says nothing before the handoff exists", text is None,
      repr(text))
check("PostToolBatch in stage 1 asks orca nothing", e.orca_calls() == 0)

# Box 2: after new-chat ran, Orca marks this chat closed: nothing more.
e = Env(LIMIT + 50000, chat_age_hours=5, chat="replaced")
e.handoff()
check("box 2: silent in the chat new-chat replaced", e.run() is None)
check("box 2: silent on PostToolBatch too",
      e.run(event="PostToolBatch") is None)
for chat in ("replaced", "side"):
    e.set_chat(chat)
    e.run(event="PostToolBatch")
    check("a %s chat on PostToolBatch writes no state" % chat,
          not (e.home / ".claude" / "state" / "bot-handover" / "s1").exists())
e.set_chat("closed_home")
check("box 2: silent in a closed chat still marked home", e.run() is None)

# Box 3: near the limit inside 4 hours: held back.
e = Env(NEAR, chat_age_hours=3)
e.handoff()
check("box 3: near the limit inside 4 hours is held", e.run() is None)

# Box 4: at or past the limit inside 4 hours: the limit wins.
for tokens in (LIMIT, LIMIT + 200000):
    e = Env(tokens, chat_age_hours=1)
    text = e.run()
    check("box 4: at %dk inside 4 hours asks for the handoff" % (tokens // 1000),
          asks_file(text) and "limit wins" in text, repr(text))
    check("box 4: at %dk the notice says which notice to follow"
          % (tokens // 1000), "wind-down notice" in text, repr(text))
    e.handoff()
    check("box 4: at %dk with a handoff asks for new-chat" % (tokens // 1000),
          asks_new_chat(e.run()))

e = Env(NEAR - 20000, chat_age_hours=10)
check("under the near line is silent", e.run() is None)

# Box 6: only an Orca bot Home Chat.
e = Env(LIMIT + 50000, chat_age_hours=5)
check("box 6: a worker in a worktree is silent",
      e.run(cwd=e.tmp / "worktree") is None)
check("box 6: the owner's session in a repo is silent",
      e.run(cwd=e.home / "code" / "repo") is None)
check("box 6: a subfolder of a bot home is silent",
      e.run(cwd=e.bot / "skills") is None)
check("box 6: a subagent is silent", e.run(agent_id="a1") is None)
for where in (e.bot / "skills" / "x", e.tmp / "elsewhere" / "twenty"):
    where.mkdir(parents=True)  # below a bot home, and outside ~/.orca/bots
    (where / "bot.json").write_text("{}")
    check("box 6: a bot.json at %s is silent" % where, e.run(cwd=where) is None)
e.set_chat("side")
check("box 6: a side chat of the bot (e.g. a sweep run) is silent",
      e.run() is None)
(e.bot / "bot.json").unlink()
e.set_chat("home")
check("box 6: a bots folder with no bot.json is silent", e.run() is None)

e = Env(LIMIT + 50000, chat_age_hours=5, chat="fail")
text = e.run()
check("a failed orca bot chats still gives the notice, marked unsure",
      asks_file(text) and "could not ask" in text, repr(text))
check("the unsure line tells the bot how to check its own row",
      'act on this notice only when that row is home' in text
      and '"${ORCA_CLI_COMMAND:-orca}" bot chats --json' in text, repr(text))
e.set_chat("no_self")
text = e.run()
check("no chat marked self still gives the notice, marked unsure",
      asks_file(text) and "could not ask" in text, repr(text))
e.set_chat("home", extra_rows=[{"id": "x2", "home": False, "self": True,
                                "closed": False}])
text = e.run()
check("two chats marked self give the notice, marked unsure",
      asks_file(text) and "could not ask" in text, repr(text))
e.set_chat("home", hang=True)
began = time.time()
text = e.run(hook_attrs={"CHATS_TIMEOUT": 1})
check("a hung orca is cut off at CHATS_TIMEOUT, marked unsure",
      time.time() - began < 4 and text is not None and "could not ask" in text,
      repr(text))
e = Env(LIMIT + 50000, chat_age_hours=5)
text = e.run()
check("a working orca bot chats gives no unsure line",
      text is not None and "could not ask" not in text, repr(text))

for hours, held in ((3, True), (5, False)):
    e = Env(NEAR, chat_age_hours=0, start_stamp=time.strftime(
        "%Y-%m-%dT%H:%M:%S+02:00", time.gmtime(T0 - (hours - 2) * HOUR)))
    check("a +02:00 stamp %d hours ago" % hours, (e.run() is None) == held)

# Config: every value is read, and a bad one falls back to the default.
e = Env(LIMIT + 50000, chat_age_hours=5)
e.config("[rules]\nbot_handover = false\n")
check("config: bot_handover = false is silent", e.run() is None)
e = Env(200000, chat_age_hours=5)
e.config("[bot_handover]\nnear_percent = 60\n")
check("config: near_percent = 60 gives a notice at 200k", e.run() is not None)
e = Env(NEAR, chat_age_hours=1)
e.config("[bot_handover]\nmin_hours = 0\n")
check("config: min_hours = 0 lifts the age guard", e.run() is not None)
e = Env(NEAR, chat_age_hours=1)
e.config("[bot_handover]\nmin_hours = -1\n")
check("config: min_hours = -1 falls back to 4", e.run() is None)
e = Env(NEAR, chat_age_hours=5)
e.config("[bot_handover]\nnear_percent = 100\n")
check("config: near_percent = 100 holds 250k", e.run() is None)
e = Env(NEAR, chat_age_hours=5)
e.config("[bot_handover]\nmin_hours = 6\n")
check("config: min_hours = 6 holds a 5-hour-old chat", e.run() is None)
e = Env(NEAR, chat_age_hours=5)
e.config('[bot_handover]\nhandoff_glob = "memory/ho-*.md"\n')
e.handoff(name="ho-1.md")
check("config: handoff_glob finds its own files",
      asks_new_chat(e.run(), "ho-1.md"))
for bad in ('near_percent = "x"', "near_percent = true", "near_percent = 120",
            'handoff_glob = "/etc/*"', 'handoff_glob = ""', "min_hours = -1"):
    e = Env(NEAR, chat_age_hours=5)
    e.config("[bot_handover]\n%s\n" % bad)
    e.handoff()
    check("config: bad %s falls back to the defaults" % bad,
          asks_new_chat(e.run()))
e = Env(NEAR, chat_age_hours=5)
e.config("[context_handoff]\nfirst_percent = 20\n")  # 200k on 1M
text = e.run()
check("config: the limit is context_handoff first_percent of the window",
      text is not None and "limit wins" in text, repr(text))
for tokens, wins in ((60000, True), (59000, False)):  # 200k window: 60k
    e = Env(tokens, chat_age_hours=5, model="claude-haiku-5-5")
    text = e.run()
    check("a 200k-window model at %dk: limit %s" % (tokens // 1000, wins),
          text is not None and ("limit wins" in text) == wins, repr(text))
e = Env(70000, chat_age_hours=1)
e.config('[context_handoff]\nwindows = { "claude-opus" = 200000 }\n')
text = e.run()
check("config: a windows table moves the limit (opus at 200k: 60k)",
      text is not None and "limit wins" in text, repr(text))

check("bad input prints nothing", load_hook().main("not json", T0) == "")

hook = load_hook()
check("a hung orca stalls a turn 10 s at most", 0 < hook.CHATS_TIMEOUT <= 10)
check("the hook's fallback defaults match handrail_config",
      hook.DEFAULTS == hook.handrail_config.VALUE_DEFAULTS["bot_handover"])
finish()
