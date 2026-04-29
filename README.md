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
python install.py
```

Or pip (once published to PyPI):

```bash
pip install agent-invoker
```

---

## MCP server setup

After installing via npm or Homebrew, add this to your editor's MCP config:

```json
{
  "mcpServers": {
    "invokerai": {
      "command": "invoker-mcp"
    }
  }
}
```

Or run the automated setup to configure every editor at once:

```bash
invoker setup
```

For local development before publishing, point at the venv directly:

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