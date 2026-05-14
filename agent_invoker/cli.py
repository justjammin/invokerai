from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_SPAWN_TOKEN = Path.home() / ".invokerai" / "spawn_token"


def main() -> None:
    # Peek at argv to decide: subcommand dispatch or bare task routing
    argv = sys.argv[1:]
    known_commands = {"route", "tools", "setup", "migrate", "mcp", "train", "spawn", "confirm", "uninstall", "decompose", "stop", "update", "agents", "log-outcome"}

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


# ── spawn — route + write token (CLI-first primary surface) ──────────────────

def _handle_spawn(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker spawn", add_help=False)
    parser.add_argument("task", nargs="?")
    parser.add_argument("--registry", metavar="PATH")
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--persona", action="store_true", help="Kept for backward compat; persona always included")
    parser.add_argument("--domains", metavar="DOMAINS", help="Comma-separated domains, e.g. backend,testing")
    parser.add_argument("--session-id", metavar="ID", dest="session_id", default=None)
    args = parser.parse_args(argv)

    task_text = args.task
    if not task_text:
        if not sys.stdin.isatty():
            task_text = sys.stdin.read().strip()
    if not task_text:
        print(json.dumps({"error": "task is required"}))
        sys.exit(1)

    domains = [d.strip() for d in args.domains.split(",") if d.strip()] if args.domains else None

    from agent_invoker.core import route
    result = route(task_text, custom_registry=args.registry, log=not args.no_log, domains=domains)

    _SPAWN_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    _SPAWN_TOKEN.write_text(f"{result.spawn_count}:{int(time.time())}")

    sid = args.session_id or "default"
    from agent_invoker.core import append_session_log, update_session
    update_session(sid, result.role, result.routing)
    append_session_log(task_text, result.role, result.confidence, result.routing, domains)

    out: dict = {
        "routing": result.routing,
        "role": result.role,
        "confidence": result.confidence,
        "tools": result.tools,
        "source": result.source,
        "spawn_authorized": True,
        "session_id": sid,
    }
    if result.persona:
        out["persona"] = result.persona
    if result.routing == "orchestrate":
        out["pattern"] = result.pattern
        out["steps"] = result.steps
    print(json.dumps(out, indent=2))


# ── confirm — subagent self-check via CLI ─────────────────────────────────────

def _handle_confirm(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker confirm", add_help=False)
    parser.add_argument("task", nargs="?")
    parser.add_argument("expected_role", nargs="?")
    args = parser.parse_args(argv)

    task_text = args.task
    expected = args.expected_role
    if not task_text or not expected:
        print(json.dumps({"error": "usage: invoker confirm \"task\" \"expected-role\""}))
        sys.exit(1)

    from agent_invoker.core import route
    result = route(task_text, log=False)
    ok = result.role == expected or result.confidence < 50
    out: dict = {
        "ok": ok,
        "expected_role": expected,
        "confirmed_role": result.role if not ok else expected,
        "confidence": result.confidence,
    }
    if not ok and result.persona:
        out["corrected_persona"] = result.persona
    print(json.dumps(out, indent=2))


# ── uninstall — reverse invoker setup ─────────────────────────────────────────

def _handle_uninstall(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker uninstall")
    parser.add_argument("--purge", action="store_true", help="Also delete ~/.invokerai/ (venv, logs, tokens)")
    args = parser.parse_args(argv)

    from agent_invoker.setup_editors import uninstall
    uninstall(purge=args.purge)


# ── decompose — pattern detection + step skeleton ─────────────────────────────

def _handle_decompose(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker decompose", add_help=False)
    parser.add_argument("task", nargs="?")
    parser.add_argument("--registry", metavar="PATH")
    args = parser.parse_args(argv)

    task_text = args.task
    if not task_text:
        if not sys.stdin.isatty():
            task_text = sys.stdin.read().strip()
    if not task_text:
        print(json.dumps({"error": "task is required"}))
        sys.exit(1)

    from agent_invoker.core import decompose
    result = decompose(task_text, custom_registry=args.registry)
    print(json.dumps({
        "pattern": result.pattern,
        "steps": result.steps,
        "domain_roles": [{"domain": d, "role": r} for d, r in result.domain_roles],
    }, indent=2))


# ── stop — kill orphaned invoker-mcp processes ───────────────────────────────

def _handle_stop(_argv: list[str]) -> None:
    import psutil

    killed: list[int] = []
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            cmdline = proc.info["cmdline"] or []
            name = proc.info["name"] or ""
            is_invoker = (
                any("agent_invoker.mcp_server" in part for part in cmdline)
                or "invoker-mcp" in name
            )
            if not is_invoker:
                continue
            if not psutil.pid_exists(proc.ppid()):
                proc.kill()
                killed.append(proc.pid)
                print(f"Killed orphan PID {proc.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not killed:
        print("No orphaned invoker-mcp processes found")


# ── update — reinstall package, rebuild router, run migration ─────────────────

def _handle_update(_argv: list[str]) -> None:
    import importlib.util
    import pathlib
    import subprocess

    pkg_dir = pathlib.Path(__file__).parent.parent

    print("InvokerAI update — reinstalling and migrating...")
    print()

    print("  Step 1: reinstalling package (editable)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(pkg_dir), "--quiet"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR: pip install -e failed:\n{result.stderr}")
        sys.exit(1)
    print("  Package: reinstalled (editable)")

    print("  Step 2: rebuilding router...")
    scripts_dir = pkg_dir / "scripts" / "build_router.py"
    result = subprocess.run(
        [sys.executable, str(scripts_dir), "--phase", "1"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  WARNING: router rebuild failed — regex fallback will be used\n{result.stderr}")
    else:
        print("  Router: rebuilt")

    print("  Step 3: running migration...")
    spec = importlib.util.spec_from_file_location("migrate", pkg_dir / "migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run()

    print()
    print("Update complete. Restart Claude Code / Cursor / Kiro to pick up changes.")


# ── agents — list registry ────────────────────────────────────────────────────

def _handle_agents(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker agents", add_help=False)
    parser.add_argument("--category", metavar="NAME", default=None)
    args = parser.parse_args(argv)

    from agent_invoker.registry.loader import load_registry
    try:
        registry = load_registry()
    except Exception:
        registry = {}
    cat = (args.category or "").lower()
    agents = [
        {"id": a.id, "category": a.category, "description": a.description, "orchestrate": a.orchestrate}
        for a in registry.values()
        if not cat or a.category.lower() == cat
    ]
    agents.sort(key=lambda a: (a["category"], a["id"]))
    print(json.dumps({"agents": agents}, indent=2))


# ── log-outcome — patch session log ──────────────────────────────────────────

def _handle_log_outcome(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="invoker log-outcome", add_help=False)
    parser.add_argument("date")
    parser.add_argument("task_prefix")
    parser.add_argument("corrections", type=int)
    parser.add_argument("accepted", choices=["true", "false", "yes", "no", "1", "0"])
    args = parser.parse_args(argv)

    accepted = args.accepted.lower() in ("true", "yes", "1")
    from agent_invoker.core import patch_session_log_outcome
    result = patch_session_log_outcome(args.date, args.task_prefix, args.corrections, accepted)
    print(json.dumps(result))


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
    elif command == "spawn":
        _handle_spawn(rest)
    elif command == "confirm":
        _handle_confirm(rest)
    elif command == "uninstall":
        _handle_uninstall(rest)
    elif command == "decompose":
        _handle_decompose(rest)
    elif command == "stop":
        _handle_stop(rest)
    elif command == "update":
        _handle_update(rest)
    elif command == "agents":
        _handle_agents(rest)
    elif command == "log-outcome":
        _handle_log_outcome(rest)


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
  invoker spawn "task"                             Route + write spawn token (primary surface, ~100 tok)
  invoker spawn "task" --domains d1,d2             Route with domain hints (domains optional: --domains d1,d2)
  invoker spawn "task" [--session-id ID]           Persist session ledger under named ID
  invoker confirm "task" "expected-role"           Subagent self-check — verify correct specialist
  invoker "task text"                              Route only (no token, no spawn)
  invoker --registry PATH "task text"              Use custom agent registry
  invoker --no-log "task text"                     Skip logging
  invoker --model-info                             Show router phase + status

  invoker decompose "task"                         Detect MAS pattern + generate skeleton steps (orchestrate only)
  invoker agents                                   List all available specialist agents
  invoker agents --category backend                Filter by category
  invoker log-outcome DATE PREFIX CORRECTIONS ACCEPTED  Append outcome metrics to session log

  invoker setup                                    Configure MCP + hooks for Claude Code, Cursor, Kiro, Copilot
  invoker uninstall                                Remove all InvokerAI config (hooks, MCP entries, CLAUDE.md block)
  invoker uninstall --purge                        Also delete ~/.invokerai/ (venv, logs, tokens)
  invoker migrate                                  Upgrade existing setup (purge old hooks, new token gate)
  invoker update                                   Reinstall package, rebuild router, run migration
  invoker mcp                                      Start MCP server (stdio)

  invoker tools add --all TOOL [TOOL...]           Add tools to all agents
  invoker tools add --category NAME TOOL [TOOL...] Add to category
  invoker tools add --agents ID,ID TOOL [TOOL...]  Add to specific agents
  invoker train                                    Build Phase 1 router from labeled examples
  invoker train --phase 2                          Build Phase 2 router (requires 200+ log entries)

  invoker tools remove --all TOOL [TOOL...]        Remove tools
  invoker tools list AGENT_ID                      List tools for agent

  invoker stop                                     Kill orphaned invoker-mcp processes (parent dead)""")


if __name__ == "__main__":
    main()