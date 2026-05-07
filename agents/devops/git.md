---
name: git
tier: 2
domain: devops
description: "Git workflow patterns"
---

# Git

Trunk-based development: feature branches short-lived (<2 days). Use feature flags for incomplete work. No long-lived branches.

Commit messages: imperative mood ("Add feature" not "Added feature"). 72 character subject line. Body explains why, not what.

PR: one concern per PR, reviewable in <30 minutes. Large PRs block review, hide issues.

Never force-push to main/master. Rebase before merge if needed, but don't rewrite history on shared branches.

.gitignore: commit it. Include IDE files (.vscode, .idea), OS files (.DS_Store), and build artifacts.

Tags: semantic versioning for releases (v1.2.3). Signed tags for security-critical releases.

## Don'ts

- Commit secrets (use .env.local, secrets manager)
- Binary files without Git LFS (clones slow, diffs useless)
- `.DS_Store`, IDE files, `node_modules/` without .gitignore
- Merge commits on feature branches (rebase for clean history)
- Commit `package-lock.json` changes without matching `package.json`
