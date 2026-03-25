# Git: Always Use Feature Branches in Parapet-Security

**Extracted:** 2026-02-09
**Context:** All Parapet-Security repos have branch protection on main via org ruleset

## Problem
Attempted `git push origin main` directly, which is blocked by branch protection. All repos in the `Parapet-Security` GitHub organization require PRs to merge to main.

## Solution
Always create a feature branch, push it, and open a PR:

```bash
git checkout -b feat/my-feature
git push -u origin feat/my-feature
gh pr create --title "feat: description" --body "..."
```

If you already committed to main locally, create the branch from that commit - git branches are just pointers so the commit comes along:

```bash
git checkout -b feat/my-feature   # branch from current main with the commit
git push -u origin feat/my-feature
```

## When to Use
Every time a commit is ready to push in any Parapet-Security repository. No exceptions.
