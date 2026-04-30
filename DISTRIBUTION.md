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