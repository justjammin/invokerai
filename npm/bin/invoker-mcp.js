#!/usr/bin/env node
'use strict';

/**
 * InvokerAI MCP launcher.
 *
 * On first run: finds Python 3.9+, creates ~/.invokerai/venv, pip-installs
 * agent-invoker from PyPI, then exec's the MCP server.
 * Subsequent runs: skips setup, exec's immediately.
 *
 * Flags (consumed here, not passed to server):
 *   --version    print npm package version and exit
 *   --update     force reinstall agent-invoker from PyPI
 */

const { execSync, execFileSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PKG = require('../package.json');
const PYPI_PACKAGE = 'agent-invoker';
const MIN_PYTHON = [3, 9];

const INVOKERAI_DIR = path.join(os.homedir(), '.invokerai');
const VENV_DIR = path.join(INVOKERAI_DIR, 'venv');
const IS_WIN = process.platform === 'win32';
const VENV_PYTHON = IS_WIN
  ? path.join(VENV_DIR, 'Scripts', 'python.exe')
  : path.join(VENV_DIR, 'bin', 'python');
const VENV_PIP = IS_WIN
  ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
  : path.join(VENV_DIR, 'bin', 'pip');

// ---------- helpers ----------------------------------------------------------

function die(msg) {
  process.stderr.write(`invoker-mcp error: ${msg}\n`);
  process.exit(1);
}

function findPython() {
  const candidates = IS_WIN
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];

  for (const cmd of candidates) {
    try {
      const out = execSync(`${cmd} --version`, {
        encoding: 'utf8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      const m = out.match(/Python (\d+)\.(\d+)/);
      if (!m) continue;
      const [maj, min] = [parseInt(m[1]), parseInt(m[2])];
      if (maj > MIN_PYTHON[0] || (maj === MIN_PYTHON[0] && min >= MIN_PYTHON[1])) {
        return cmd;
      }
    } catch (_) {}
  }
  return null;
}

function setupVenv(force = false) {
  const needsInstall = force || !fs.existsSync(VENV_PYTHON);

  if (!needsInstall) return;

  const python = findPython();
  if (!python) {
    die(
      `Python ${MIN_PYTHON.join('.')}+ not found.\n` +
      '  Install from https://python.org or via your package manager.'
    );
  }

  process.stderr.write('InvokerAI: setting up environment (first run)...\n');
  fs.mkdirSync(VENV_DIR, { recursive: true });

  if (!fs.existsSync(VENV_PYTHON)) {
    execSync(`${python} -m venv "${VENV_DIR}"`, { stdio: 'inherit' });
  }

  execFileSync(VENV_PIP, ['install', '--quiet', '--upgrade', 'pip'], {
    stdio: 'inherit',
  });

  const installArgs = force
    ? ['install', '--quiet', '--upgrade', PYPI_PACKAGE]
    : ['install', '--quiet', PYPI_PACKAGE];

  execFileSync(VENV_PIP, installArgs, { stdio: 'inherit' });
  process.stderr.write('InvokerAI: environment ready.\n');
}

// ---------- main -------------------------------------------------------------

const args = process.argv.slice(2);

if (args.includes('--version')) {
  process.stdout.write(`invokerai-mcp ${PKG.version}\n`);
  process.exit(0);
}

const forceUpdate = args.includes('--update');
const serverArgs = args.filter(a => a !== '--update');

setupVenv(forceUpdate);

// Exec the MCP server — stdio passes through so Claude Code / Cursor see it
const child = spawn(VENV_PYTHON, ['-m', 'agent_invoker.mcp_server', ...serverArgs], {
  stdio: 'inherit',
  env: { ...process.env },
});

child.on('error', (err) => die(`failed to start server: ${err.message}`));
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});