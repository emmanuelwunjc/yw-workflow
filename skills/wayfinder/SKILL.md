---
name: wayfinder
description: Chart a body of work too big for one session as a map of decision tickets on GitHub Issues, then resolve them one at a time until the route is clear. Use for a loose idea, a migration, a new project, or any effort where the destination is known and the way there is not. Triggers include "where do I even start", "this is too big", "chart this", "wayfinder".
origin: authored
tags: [planning, github-issues, decisions, multi-session]
version: 1.0.0
---

# Wayfinder

Some work is too big to hold in one session. Charging at it produces a plan
that is stale by the time the session compacts. This skill writes the plan
down where it survives: GitHub Issues on the repo the work lands in.

**It plans. It does not build.** Every ticket resolves a decision. When
nothing is left to decide, the map is done and `/ship-loop` takes over. The
urge to just write the code is the signal you have reached the edge of the
map.

## The map

One issue, labelled `wayfinder:map`. It is an index, so a decision lives in
exactly one place, its own ticket, and the map only gists and links. Body:

```markdown
## Destination
<what "done" looks like: the spec, the decision, the migration. Two lines.>

## Notes
<domain, skills each session should load, standing preferences>

## Decisions so far
- [<ticket title>](url) . <one-line gist of the answer>

## Fog
<in-scope questions too blurry to ticket yet>

## Out of scope
<ruled beyond the destination, with why. Never graduates.>
```

Open tickets are not listed. They are found by query, so the map never goes
stale:

```bash
gh issue list --label wayfinder:ticket --state open --json number,title,assignees,body
```

## Tickets

One child issue per decision, sized to one session. Body is the question and
nothing else. Each carries `wayfinder:ticket` plus one type label:

- `type:research` runs alone. A `/research` subagent reads docs or APIs to
  surface a fact a decision waits on. Fire these in parallel.
- `type:prototype` needs you. Build the cheapest concrete thing that can be
  reacted to, then react to it together.
- `type:grill` needs you. Run `/grill`. This is the default.
- `type:task` unblocks a decision by doing something manual: provisioning
  access, moving data so its shape is visible. The one type that acts, and it
  earns that by unblocking a decision rather than delivering the destination.

**Claim before working.** `gh issue edit <n> --add-assignee @me`, first thing,
so a parallel session skips it. Blocking goes in the body as
`Blocked by: #<n>`, and the frontier is every open, unassigned ticket with no
open blocker.

**Refer to tickets by title, never by bare number.** `#42, #43, #44` is
illegible. Per `~/CLAUDE.md` section 7, gloss every number.

## Fog of war

Do not chart what you cannot see. Beyond the live tickets sits the fog: work
you can tell is coming and cannot yet phrase sharply. It goes in the map's
**Fog** section as prose.

The test is whether you can state the question precisely now. Not whether you
can answer it.

- Sharp enough to state: make it a ticket, even if it is blocked.
- Too blurry: leave it in Fog. Resolving a ticket clears fog ahead of it, and
  a patch graduates into one ticket, several, or none.

Work past the destination is out of scope instead. It gets its own section and
never graduates. If an existing ticket turns out to sit past the destination,
close it and leave a line saying why. A scope boundary is not a step on the
route, so it stays out of Decisions so far.

## Mode 1: chart the map

1. **Name the destination.** Run `/grill` until you can write it in two lines.
   Scope hangs off it, so settle it first.
2. **Grill again, breadth-first.** Fan across the whole space to surface open
   decisions. If this turns up no fog, the work fits in one session. Say so
   and stop. A map for small work is overhead.
3. **Create the map issue**, Destination and Notes filled, Decisions empty,
   fog written down.
4. **Create the tickets you can specify**, then wire `Blocked by:` in a second
   pass, because issues need numbers before they can reference each other.
5. **Fire the research subagents** in parallel on a throwaway `research/<name>`
   branch each. Load `/git-lanes` first: concurrent agents get worktrees.
6. **Stop.** Charting is one session. It resolves nothing.

## Mode 2: work the map

Invoked with a map number. One ticket per session, research excepted.

1. Read the map. The low-resolution view, not every ticket body.
2. Take the ticket the user named, or the first on the frontier. Claim it.
3. Resolve it. Pull the full body of a related closed ticket only when you
   need it. Load whatever `## Notes` names.
4. Post the answer as a comment, close the issue, append one line to
   Decisions so far.
5. Graduate any fog the answer sharpened into new tickets and delete that
   patch from Fog. Rule newly-out-of-scope work out. If the answer invalidates
   other tickets, edit or close them.

Expect concurrent sessions on unblocked tickets. Re-read the map before
editing it.

## Done

The map is done when the frontier is empty and the fog is empty. Hand off to
`/ship-loop` with the map URL. The decisions become the tickets it implements.
