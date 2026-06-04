# invokerai-skills

InvokerAI agent routing brain delivered as Claude Code Skills.

## What It Does

Three sub-skills orchestrate multi-agent execution:

- **invokerai:setup** — Scan your installed agents and build a domain→agent mapping (`~/.invoker/agent-map.json`). Run once or when agents change.
- **invokerai:decompose** — Break a task into a directed acyclic graph (DAG) of ordered steps with dependencies and parallelism flags.
- **invokerai:spawn** — Execute the DAG: select agents from the mapping, spawn them in dependency order, track via BEADS (if available), confirm completion.

## Install

```bash
npx invokerai-skills
```

This copies the skill definitions to `~/.claude/skills/invokerai*`. Requires `~/.claude` to exist.

### Options

- `--user` — Symlink full skill directories into `~/.claude/skills` and `~/.cursor/skills`
- `--project` — Symlink full skill directories into `./.claude/skills` and `./.cursor/skills` (current working directory)
- `--claude-only` — With `--user`/`--project`, install to Claude Code only
- `--cursor-only` — With `--user`/`--project`, install to Cursor only
- `-h, --help` — Print help

### Examples

```bash
# Install to ~/.claude/skills (default)
npx invokerai-skills

# Symlink into ~/.claude/skills and ~/.cursor/skills
npx invokerai-skills --user

# Symlink into project-local ./.claude/skills and ./.cursor/skills
npx invokerai-skills --project

# Symlink to ~/.claude only
npx invokerai-skills --user --claude-only
```

## Quick Start

### 1. Install

```bash
npx invokerai-skills
```

### 2. Set up agent mapping

```
/invokerai:setup
```

Run once to scan your installed agents and build `~/.invoker/agent-map.json`.

### 3. Decompose a task

```
/invokerai:decompose
Task: <your task description>
Domains: <space-separated list: backend, frontend, testing, etc.>
```

Get back a DAG with ordered steps and dependencies.

### 4. Execute the DAG

```
/invokerai:spawn
```

Spawn agents in order, track via BEADS (optional), confirm completion.

## Domain Decision Guide

Pass only domains where real work exists:

| Domain | Add when | Skip when |
|--------|----------|-----------|
| `architecture` | New subsystem design, cross-cutting redesign | Bug fix, additive feature, impl path obvious |
| `backend` | Server routes, APIs, business logic, auth middleware | Pure UI work, DB-only schema changes |
| `frontend` | UI components, styling, client-side state, rendering | Server-only work, no user-facing changes |
| `database` | Schema changes, migrations, query optimization | No DB reads/writes in the task |
| `devops` | CI/CD pipelines, Dockerfiles, infra config, deploy | App code changes only |
| `security` | Auth flows, permissions, secrets, input validation, CVE fixes | Feature work, no trust boundary changes |
| `ml` | Model training, inference, embeddings, vector search | Standard CRUD, no ML components |
| `testing` | Writing/fixing tests, test infra, coverage gaps | Impl work where tests are a side effect |
| `documentation` | API docs, READMEs, changelogs, docstrings, user guides | Code-only changes, no public surface |
| `mobile` | iOS/Android native code, React Native, Flutter | Web-only work |
| `data` | ETL pipelines, data transforms, analytics, reporting | App features with no data pipeline |
| `code-review` | Reviewing a diff/PR, auditing quality/security | Active implementation (review ≠ build) |

**Domain precision is critical:** wrong domains → phantom steps → wasted agents.
- Pass only domains where real work exists.
- When unsure, under-specify — gaps will surface in decompose.
- Never add a domain speculatively.

## Files

- `install.js` — Installation script (Node.js, no dependencies)
- `skill/` — Skill definitions (4 skills: invoicerai, invoicerai-setup, invoicerai-decompose, invoicerai-spawn)
- `package.json` — NPM package metadata
- `LICENSE` — MIT

## License

MIT — see LICENSE
