#!/usr/bin/env python3
"""
InvokerAI installer.

Installs the agent-invoker package and builds the initial router.pkl.

Usage:
    python install.py
    python install.py --no-build   # skip router.pkl generation
    python install.py --dev        # install in editable mode
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 9)
INVOKERAI_DIR = Path.home() / ".invokerai"
CLAUDE_AGENTS_DIR = Path.home() / ".claude" / "agents"
LOCAL_AGENTS_DIR = Path(__file__).parent / "agents"


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        print(f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required (got {sys.version})")
        sys.exit(1)


def check_pip() -> None:
    if shutil.which("pip") is None and shutil.which("pip3") is None:
        print("Error: pip not found. Install pip first.")
        sys.exit(1)


def pip_install(editable: bool = False) -> None:
    pkg_dir = Path(__file__).parent

    # Prefer an active venv; fall back to --user if no venv detected
    in_venv = sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in __import__("os").environ
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"]

    if editable:
        cmd += ["-e", str(pkg_dir)]
    else:
        cmd += [str(pkg_dir)]

    if not in_venv:
        cmd += ["--user"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Retry without --user for PEP 668 externally managed envs
        if "--user" in cmd:
            cmd.remove("--user")
            result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("pip install failed — try inside a venv:")
        print("  python3 -m venv .venv && source .venv/bin/activate && python install.py")
        print(result.stderr)
        sys.exit(1)
    print("  Package: agent-invoker installed")


def install_agents() -> None:
    if not LOCAL_AGENTS_DIR.exists():
        return
    CLAUDE_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(LOCAL_AGENTS_DIR.glob("*.md"))
    for f in files:
        shutil.copy2(f, CLAUDE_AGENTS_DIR / f.name)
    print(f"  Agents:  {len(files)} agent files → {CLAUDE_AGENTS_DIR}")


def _setup_editors() -> None:
    from agent_invoker.setup_editors import run
    pkg_dir = Path(__file__).parent
    run(pkg_dir=pkg_dir)


def build_router() -> None:
    scripts_dir = Path(__file__).parent / "scripts" / "build_router.py"
    result = subprocess.run(
        [sys.executable, str(scripts_dir), "--phase", "1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Warning: router.pkl build failed — regex fallback will be used")
        print(result.stderr)
        return
    print(f"  Router:  {INVOKERAI_DIR / 'router.pkl'}")


def verify() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agent_invoker.cli", "--model-info"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Warning: verification failed — check installation manually")
        return
    print("  Verify:  OK")


def print_summary() -> None:
    print()
    print("InvokerAI installed.")
    print()
    print("  invoker \"fix the null check in auth\"")
    print("  invoker --model-info")
    print("  invoker --registry ./my-agents.json \"deploy the api\"")
    print()
    print("Phase 2 (neural embeddings, ~420MB download):")
    print("  pip install agent-invoker[embeddings]")
    print("  python scripts/build_router.py --phase 2")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Install InvokerAI")
    parser.add_argument("--no-build", action="store_true", help="Skip router.pkl generation")
    parser.add_argument("--dev", action="store_true", help="Install in editable mode")
    args = parser.parse_args()

    print("Installing InvokerAI...")
    print()

    check_python()
    check_pip()
    pip_install(editable=args.dev)
    install_agents()

    if not args.no_build:
        build_router()

    _setup_editors()
    verify()
    print_summary()


if __name__ == "__main__":
    main()