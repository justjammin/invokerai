from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    # Peek at argv to decide: subcommand dispatch or bare task routing
    argv = sys.argv[1:]
    known_commands = {"route", "tools", "setup", "migrate", "mcp", "train"}

    if argv and argv[0] in known_commands:
        _dispatch_subcommand(argv)
    else:
        _dispatch_route(argv)


# ── route (default path) ──────────────────────────────────────────────────────

def _dispatch_route(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker", add_help=False)
    parser.add_argument("task", nargs="?")
    parser.add_argument("--registry", metavar="PATH")
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--model-info", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args(argv)

    if args.help:
        _print_help()
        return

    if args.model_info:
        _show_model_info()
        return

    task_text = args.task
    if not task_text:
        if not sys.stdin.isatty():
            task_text = sys.stdin.read().strip()
        if not task_text:
            _print_help()
            sys.exit(1)

    from agent_invoker.core import route
    result = route(task_text, custom_registry=args.registry, log=not args.no_log)
    print(json.dumps({
        "routing": result.routing,
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
    }, indent=2))


# ── tools subcommand ──────────────────────────────────────────────────────────

def _dispatch_subcommand(argv: list[str]) -> None:
    command = argv[0]
    rest = argv[1:]

    if command == "tools":
        _handle_tools(rest)
    elif command == "setup":
        from agent_invoker.setup_editors import run
        run()
    elif command == "migrate":
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "migrate", pathlib.Path(__file__).parent.parent / "migrate.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run()
    elif command == "mcp":
        from agent_invoker.mcp_server import serve
        serve()
    elif command == "train":
        _handle_train(rest)
    elif command == "route":
        _dispatch_route(rest)


def _handle_tools(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker tools")
    sub = parser.add_subparsers(dest="action", required=True)

    p_add = sub.add_parser("add", help="Add tools to agents")
    _add_target_args(p_add)
    p_add.add_argument("tools", nargs="+")
    p_add.add_argument("--agents-dir", metavar="PATH")
    p_add.add_argument("--registry", metavar="PATH")

    p_rm = sub.add_parser("remove", help="Remove tools from agents")
    _add_target_args(p_rm)
    p_rm.add_argument("tools", nargs="+")
    p_rm.add_argument("--agents-dir", metavar="PATH")
    p_rm.add_argument("--registry", metavar="PATH")

    p_ls = sub.add_parser("list", help="List tools for an agent")
    p_ls.add_argument("agent_id")
    p_ls.add_argument("--agents-dir", metavar="PATH")

    args = parser.parse_args(argv)
    from agent_invoker import tools as tm

    agents_dir = Path(args.agents_dir) if getattr(args, "agents_dir", None) else tm.DEFAULT_AGENTS_DIR
    registry = Path(args.registry) if getattr(args, "registry", None) else tm.DEFAULT_REGISTRY

    if args.action == "list":
        result = tm.list_tools(args.agent_id, agents_dir)
        print(json.dumps({args.agent_id: result}, indent=2))
        return

    if getattr(args, "all_agents", False):
        targets = "all"
    elif getattr(args, "category", None):
        targets = args.category
    else:
        targets = [a.strip() for a in args.agents.split(",")]

    if args.action == "add":
        changed = tm.add_tools(targets, args.tools, agents_dir, registry)
    else:
        changed = tm.remove_tools(targets, args.tools, agents_dir, registry)

    print(json.dumps({aid: t for aid, t in changed.items()}, indent=2))
    sys.stderr.write(str(len(changed)) + " agent(s) updated.\n")


# ── helpers ───────────────────────────────────────────────────────────────────

def _add_target_args(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--agents", metavar="IDS", help="Comma-separated agent ids")
    group.add_argument("--category", metavar="NAME", help="Category name")
    group.add_argument("--all", dest="all_agents", action="store_true", help="All agents")


def _handle_train(argv: list[str]) -> None:
    import subprocess
    script = Path(__file__).parent.parent / "scripts" / "build_router.py"
    if not script.exists():
        print(json.dumps({"error": "scripts/build_router.py not found — install from repo source"}))
        sys.exit(1)
    result = subprocess.run([sys.executable, str(script)] + argv)
    sys.exit(result.returncode)


def _show_model_info() -> None:
    import pickle
    pkl = Path.home() / ".invokerai" / "router.pkl"
    log = Path.home() / ".invokerai" / "routing_log.jsonl"
    info: dict = {"router_pkl": str(pkl)}
    if pkl.exists():
        bundle = pickle.load(open(pkl, "rb"))
        info["phase"] = bundle.get("phase", 1)
        info["model"] = bundle.get("model_name", "tfidf")
    else:
        info["phase"] = None
        info["model"] = "none — run: python -m agent_invoker.build"
    info["logged_decisions"] = sum(1 for _ in log.open()) if log.exists() else 0
    print(json.dumps(info, indent=2))


def _print_help() -> None:
    print("""Usage:
  invoker "task text"                              Route a task
  invoker --registry PATH "task text"              Use custom agent registry
  invoker --no-log "task text"                     Skip logging
  invoker --model-info                             Show router phase + status

  invoker setup                                    Configure MCP for Claude Code, Cursor, Kiro, Copilot
  invoker migrate                                  Upgrade existing setup (purge old hooks, new token gate)
  invoker mcp                                      Start MCP server (stdio)

  invoker tools add --all TOOL [TOOL...]           Add tools to all agents
  invoker tools add --category NAME TOOL [TOOL...] Add to category
  invoker tools add --agents ID,ID TOOL [TOOL...]  Add to specific agents
  invoker train                                    Build Phase 1 router from labeled examples
  invoker train --phase 2                          Build Phase 2 router (requires 200+ log entries)

  invoker tools remove --all TOOL [TOOL...]        Remove tools
  invoker tools list AGENT_ID                      List tools for agent""")


if __name__ == "__main__":
    main()