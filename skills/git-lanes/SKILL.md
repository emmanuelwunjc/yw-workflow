---
name: git-lanes
description: Old name of skill git-worktrees, renamed on 2026-11-24 (#228, from twenty #672). Use when a rule file or a brief still says "git-lanes". Load `yw-workflow:git-worktrees` instead.
origin: authored
tags: [git, worktree, renamed]
version: 2.0.0
---

# Git lanes (renamed)

**In one line:** Sends you to skill `git-worktrees`, the new name of this skill.

Say that line back when you start, so whoever invoked this knows what they
got.

Load `/yw-workflow:git-worktrees` now and follow it. The owner retired the
word "lane" on 2026-11-23 in twenty #672: one worktree and branch per agent
is a worktree. This file stays so an old `CLAUDE.md` or brief that names
`git-lanes` still finds the rule. Delete it when `grep -rn git-lanes` over
the repos that use this plugin prints nothing.
