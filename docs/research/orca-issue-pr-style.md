# How Orca writes issues and PRs

Read on 2026-11-25, against Orca 1.4.274 and the `main` branch of
[stablyai/orca](https://github.com/stablyai/orca). The owner asked what
yw-workflow should copy, and asked that every yw-workflow issue and PR start
with an ELI5 section.

## The short answer

Orca's PR template opens with `## ELI5`. Most Orca PRs keep it: 20 of the
last 30 merged PRs start with that heading. Orca's issues have no fixed
opening. Those filed through the bug form start with its first question,
"Where were you using Orca?". Many others use "What happens", "Expected" and
"Steps", as in issue #49329.
yw-workflow now opens every issue and PR with `## ELI5`. It also takes four
other Orca habits. It skips five, for the reasons below.

## Sources

| Source | What it is |
|---|---|
| [`.github/pull_request_template.md`](https://github.com/stablyai/orca/blob/main/.github/pull_request_template.md) | The PR template. Sections in order: ELI5, What Changed, Why, Linked Issue, Visual Proof, Testing, Performance, Risk, AI Disclosure, Review, Agent skill upstream boundary, Notes, Checklist. |
| [`.github/CONTRIBUTING.md`](https://github.com/stablyai/orca/blob/main/.github/CONTRIBUTING.md), section "Pull Requests" | "Fill in every section", and keep "each PR small and focused on one topic". |
| [`bug_report.yml`](https://github.com/stablyai/orca/blob/main/.github/ISSUE_TEMPLATE/bug_report.yml), [`feature_request.yml`](https://github.com/stablyai/orca/blob/main/.github/ISSUE_TEMPLATE/feature_request.yml), [`config.yml`](https://github.com/stablyai/orca/blob/main/.github/ISSUE_TEMPLATE/config.yml) | Issue forms. A third form, `other.yml`, takes anything else. A bug asks where, which OS, which version, then one free "Details" box with summary and steps. A feature asks for the problem, the proposed solution and alternatives. Blank issues are off. |
| [`.github/workflows/pr-description.yml`](https://github.com/stablyai/orca/blob/main/.github/workflows/pr-description.yml) | The one CI check on the PR body. It checks the Performance section only. Nothing checks ELI5. |
| [PR #49300](https://github.com/stablyai/orca/pull/49300) | A typical merged PR. Its ELI5 is two sentences of plain words. "What Changed" gives a before and an after. "Testing" names which half of the change each test fails without. |
| [PR #49337](https://github.com/stablyai/orca/pull/49337) | One of the PRs with no ELI5. It opens with "Problem" and "Change". |
| [Issue #49329](https://github.com/stablyai/orca/issues/49329) | A typical issue: "What happens", "Expected", "Steps". |
| Built-in bot templates | `orca bot create --offer --template nope` prints the valid template ids, e.g. `pr-review`, `issue-triage`, `release-notes`, `spec-drafts`, `briefing`. Each template loads skills that ship inside the app, in `/Applications/Orca.app/Contents/Resources/orcad-template/orcad-server.js`. The skills about writing: `issue-triage`, `pr-review-checklist`, `release-notes-style`, `spec-format`, `status-brief`, `release-readiness`. |

Recount the PR and issue numbers above with these commands:

```sh
gh pr list -R stablyai/orca --state merged --limit 30 --json body --jq '[.[]|.body|startswith("## ELI5")]|group_by(.)|map({(.[0]|tostring):length})'
gh issue list -R stablyai/orca --state all --limit 30 --json body --jq '[.[]|.body|test("(?m)^#+ What happens")]|group_by(.)|map({(.[0]|tostring):length})'
```

On 2026-11-25 they gave 20 of 30 PRs with ELI5 first, and 5 of 30 issues with
a "What happens" heading.

## What the bot templates tell a bot about writing

- `issue-triage`: ask for every missing detail "once, in one comment". Be
  specific about where to find it ("Which version? Settings → About shows
  it."). A bug needs version, platform, steps, expected and actual result.
- `pr-review-checklist`: "One finding per bullet, most serious first." Each
  finding names file and line, "and says what goes wrong, for whom, and
  when". "three real findings beat ten guesses". End with one line: ready to
  merge, or what must change first.
- `release-notes-style`: "Notes are for the people who use the product, not
  for the people who built it." Three groups: New, Fixed, Changed. For a fix,
  "Say what used to go wrong, not how it was fixed."
- `spec-format`: Problem (two or three sentences), Decision, Scope (in and
  explicitly out), Open questions with who can answer each.
- `status-brief`: under ten lines. Changed, Blocked, Needs a decision. "Lead
  with the part that needs action."

## What yw-workflow adopts

1. **`## ELI5` first, in every issue and PR.** Orca's own template does this,
   and the owner asked for it. Two or three plain sentences: what it is and
   why it matters. No file names. Orca's template asks for it, but a third
   of its recent PRs drop it, and nothing checks it. So the yw-workflow
   skills that write issues and PR bodies name it too. A CI check that fails
   a PR body with no ELI5 is ticket #346.
2. **What changed as a before and an after.** From Orca's "What Changed"
   section and PR #49300. The reader sees the difference without the diff.
3. **Why, with the alternatives you rejected.** From Orca's "Why" section.
   It matches the "considered and rejected" rule in `ship-loop` step 5.
4. **Risk, with how to back it out.** From Orca's "Risk" section: what could
   break, for whom, and whether a plain revert undoes it.
5. **Testing names what fails without the change.** From Orca's testing
   checkbox ("Every added test fails without this change") and PR #49300.
   It is the same rule as yw-workflow's failing probe first.

The issue template gets ELI5 and a Problem section above the four existing
parts. Problem holds the text that had no heading before. Orca's bug form
asks for expected and actual results. The yw-workflow Reproduction part
already asks for "the wrong output", so it needs no new heading.

## What yw-workflow skips, and why

- **Visual Proof.** yw-workflow ships skills, hooks and scripts, with no UI.
- **Performance as a required section.** Orca is an app with hot paths. Most
  yw-workflow changes are prose and small scripts, so the line would read
  "None, because it is a doc" almost every time. Risk covers the rare case.
- **AI Disclosure.** `~/CLAUDE.md` section 6 forbids AI attribution in
  anything people read, and `hooks/no-ai-attribution.py` enforces it.
- **The checklist of boxes.** Ticked boxes are self-certification. In
  yw-workflow, the independent review (`fresh-eye`) and CI do that work,
  and a ticked box adds nothing a reader can check.
- **Issue forms (`.yml`) and `blank_issues_enabled: false`.** Most
  yw-workflow tickets are filed by agents with `gh issue create --body`,
  which applies no template or form. A form would help only the web page,
  and the skill text is what agents read. The Markdown template stays.

## Where the change lives

- `.github/ISSUE_TEMPLATE/ticket.md` and `.github/pull_request_template.md`.
- `skills/ship-loop/SKILL.md` step 1 (the six ticket parts) and step 6 (the
  PR body). `tools/ticket_parts.py` keeps step 1 and the issue template in
  step.
- `skills/pm`, `skills/handoff`, `skills/fresh-eye`, `skills/goal-tracker`,
  `orca/loop/worker-rules.txt`, and `docs/agents/issue-tracker.md` (which
  `mattpocock-skills:to-tickets` reads) point at those two places.
- A CI check that fails a PR body with no ELI5 is ticket #346.
