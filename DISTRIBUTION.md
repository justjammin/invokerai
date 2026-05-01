# InvokerAI Distribution Guide

Three distribution channels. `invoker setup` detects which one you used and writes
the correct MCP config automatically — you never need to edit it by hand.

## How setup detects your install

`invoker setup` runs `_mcp_entry()` in this priority order:

| Priority | Install method | Config written |
|----------|---------------|----------------|
| 1 | **Homebrew** | `{"command": "/opt/homebrew/bin/invoker-mcp"}` — absolute path, immune to PATH changes |
| 2 | **npm** (nvm / fnm / volta / system) | `{"command": "/absolute/path/to/invoker-mcp"}` — searched across all node version managers |
| 3 | **invoker-mcp on current PATH** | `{"command": "invoker-mcp"}` — only if already resolvable |
| 4 | **From source / pip editable** | `{"command": "/path/to/python", "args": ["-m", "agent_invoker.mcp_server"]}` |

> **Why absolute paths matter:** npm installs are tied to the active Node version.
> If you use nvm and switch versions — or if Claude Code starts with a different PATH
> than your shell — `invoker-mcp` becomes invisible. Using the absolute path bypasses
> this entirely. Homebrew and the Python fallback are always stable regardless of shell state.

---

## Channel 1 — npm (Mac / Linux / Windows)

**Package:** `invokerai-mcp` on npmjs.com  
**Source:** `npm/` directory  

The npm package is a thin Node.js launcher. On first run it:
1. Finds Python 3.9+ on the host
2. Creates `~/.invokerai/venv`
3. `pip install agent-invoker` from PyPI into that venv
4. Execs `python -m agent_invoker.mcp_server` (stdio passes through)

Subsequent runs skip setup and exec immediately.

### Prerequisites

- Node.js 16+
- Python 3.9+

### User install

```bash
npm install -g invokerai-mcp
```

### Update agent-invoker without reinstalling npm package

```bash
invoker-mcp --update
```

### Publish to npm

```bash
# 1. Bump version in npm/package.json to match agent-invoker version
# 2. From repo root:
cd npm
npm publish --access public
```

> **Important:** Publish `agent-invoker` to PyPI first (see below).  
> The npm launcher pulls it from PyPI on first run.

---

## Channel 2 — Homebrew tap (Mac / Linux)

**Tap:** `brew tap justjammin/invokerai`  
**Formula:** `homebrew/Formula/invokerai.rb`  
**Source:** `homebrew/` directory  

Homebrew installs a fully isolated Python virtualenv + all deps.  
No system Python, no venv setup on first run — install is complete immediately.

### User install

```bash
brew tap justjammin/invokerai
brew install invokerai
```

### Publish steps

#### Step 1 — publish agent-invoker to PyPI

```bash
# In repo root
pip install build twine
python -m build
twine upload dist/*
```

This gives you a PyPI URL like:
```
https://files.pythonhosted.org/packages/source/a/agent-invoker/agent_invoker-0.1.0.tar.gz
```

#### Step 2 — get sha256 + resource hashes

```bash
# Creates a skeleton formula with real sha256
brew create https://files.pythonhosted.org/packages/source/a/agent-invoker/agent_invoker-0.1.0.tar.gz

# Generates resource blocks with sha256 for all dependencies
brew update-python-resources invokerai --print-only
```

#### Step 3 — update formula

Replace `PLACEHOLDER` values in `homebrew/Formula/invokerai.rb` with real URLs + sha256 hashes.

#### Step 4 — create the tap repo

```bash
# Homebrew taps must live in a repo named homebrew-<tapname>
# Create: github.com/justjammin/homebrew-invokerai
# Copy formula there:
mkdir -p ~/homebrew-invokerai/Formula
cp homebrew/Formula/invokerai.rb ~/homebrew-invokerai/Formula/
cd ~/homebrew-invokerai
git init && git add . && git commit -m "add invokerai formula"
git remote add origin git@github.com:justjammin/homebrew-invokerai.git
git push -u origin main
```

#### Step 5 — test the tap

```bash
brew tap justjammin/invokerai
brew install invokerai
brew test invokerai
```

---

## Version sync

Keep versions in sync across all three places:

| File | Field |
|------|-------|
| `pyproject.toml` | `version` |
| `npm/package.json` | `version` |
| `homebrew/Formula/invokerai.rb` | `url` (version in filename) |

---

## Current MCP config (before npm/brew publish)

While iterating locally, point directly at the venv Python:

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/you/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/invokerai"
      }
    }
  }
}
```

Or install editable into a venv you control:

```bash
python3 -m venv ~/.invokerai/venv
~/.invokerai/venv/bin/pip install -e /path/to/invokerai
```

Then MCP config:

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "/Users/you/.invokerai/venv/bin/python",
      "args": ["-m", "agent_invoker.mcp_server"]
    }
  }
}
```

# InvokerAI

When you're building with AI agents, one of the first things you hit is: *which agent handles this?* InvokerAI answers that question. Give it a task in plain text and it returns the right specialist, the routing decision, and the tools to hand that agent.

No API calls. No cloud dependency. Everything runs locally.

Extracted from [LENA](https://github.com/justjammin/lena), the AI orchestrator for Claude Code.

---

## Install

### npm (Mac / Linux / Windows)

Requires Node 16+ and Python 3.9+.

```bash
npm install -g invokerai-mcp
```

On first run the launcher creates `~/.invokerai/venv`, pip-installs `agent-invoker` from PyPI, then starts the MCP server. Subsequent runs skip setup entirely.

Update the Python package without reinstalling the npm wrapper:

```bash
invoker-mcp --update
```

### Homebrew (Mac / Linux)

```bash
brew tap justjammin/invokerai
brew install invokerai
```

Fully isolated — ships its own Python venv. No system Python changes.

### From source

```bash
git clone https://github.com/justjammin/invokerai
cd invokerai
pip install -e .
 invoker setup
python install.py
```

Or pip (once published to PyPI):

```bash
pip install agent-invoker
```

---

## MCP server setup

Run the automated setup to configure every editor at once:

```bash
invoker setup
```

**Claude Code:** add to `~/.claude.json` (not `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "invoker-mcp"
    }
  }
}
```

**Other editors:** add the same block to your editor's MCP config file.


See [`DISTRIBUTION.md`](DISTRIBUTION.md) for the full PyPI → npm → Homebrew publish playbook.

---

## How it works

```python
from agent_invoker import route

result = route("fix the null check in auth middleware")

print(result.routing)    # "direct"
print(result.role)       # "debugger"
print(result.confidence) # 91
print(result.tools)      # ["Read", "Bash", "Grep", "Edit"]
```

Same thing from the terminal:

```bash
invoker "fix the null check in auth middleware"
```

```json
{
  "routing": "direct",
  "role": "debugger",
  "confidence": 91,
  "tools": ["Read", "Bash", "Grep", "Edit"],
  "source": "ml-phase1"
}
```

Three things come back:

- **routing** — `direct` means one agent can handle it. `orchestrate` means it needs coordination.
- **role** — the specialist to use.
- **tools** — pass this list to the agent so it has what it needs.

---

## Custom agents

InvokerAI ships with 64 curated agents. You can bring your own and they'll override defaults on `id` collision:

```bash
invoker --registry ./my-agents.json "task text"
invoker --registry ./agents/ "task text"        # loads every *.json in the dir
```

```python
result = route("task text", custom_registry="./my-agents.json")
```

Registry format:

```json
{
  "version": "1.0",
  "agents": [
    {
      "id": "my-agent",
      "category": "backend",
      "description": "Does X for Y use case",
      "domains": ["backend"],
      "triggers": ["keyword1", "keyword2"],
      "tools": ["Read", "Write", "Bash"],
      "orchestrate": false
    }
  ]
}
```

---

## Routing model

InvokerAI improves over time. It ships in two phases:

| Phase       | Model                                         | What it takes                            |
|-------------|-----------------------------------------------|------------------------------------------|
| 1 (default) | TF-IDF + KNeighborsClassifier                 | Nothing — works on install               |
| 2           | `all-mpnet-base-v2` + RandomForestClassifier  | ~200 logged decisions + one download     |

Phase 2 is a meaningful accuracy bump. When you're ready:

```bash
pip install agent-invoker[embeddings]   # sentence-transformers + torch (CPU)
python scripts/build_router.py --phase 2
```

That downloads `all-mpnet-base-v2` (~420MB) once to `~/.cache/huggingface/`. Fully local after that, no ongoing downloads or API calls.

---

## Logging

Every routing decision is logged to `~/.invokerai/routing_log.jsonl`. That's what powers Phase 2 training over time.

```bash
invoker --model-info       # show current phase, model, and decision count
invoker --no-log "task"    # skip logging for a specific call
```

Once you hit 200 decisions, InvokerAI will print a reminder to stderr. When you're ready, one command handles it:

```bash
invoker train
```

That installs the embeddings extras and builds the Phase 2 router in one shot. Options if you need them:

```bash
invoker train --skip-install    # skip pip, just rebuild the router
invoker train --phase 1         # rebuild Phase 1 instead
```

---

## Editor setup

Run this once and InvokerAI configures itself as an MCP server for every editor you have installed:

```bash
invoker setup
```

Covers Claude Code, Cursor, VS Code, Windsurf, Zed, GitHub Copilot, Cline, Roo Code, Gemini CLI, OpenCode, Amazon Q, JetBrains, Continue, Amp, and more. It also injects a `CLAUDE.md` node so the routing tool surfaces automatically inside Claude Code.

---

## Framework integration

```python
# Drop it into a LangGraph node
from agent_invoker import route

def routing_node(state):
    result = route(state["task"])
    return {"agent": result.role, "tools": result.tools}
```

---

## License

MIT — [Jamin Echols](https://github.com/justjammin)