#!/usr/bin/env node
// InvokerAI PreToolUse enforcement gate.
// Fail-open by design: on ANY error, exit 0 silently so a bug never bricks tools.
//
// Scoped enforcement model (main thread, agent_id absent):
//   EDIT tools  -> denied only when the target is inside the repo the session is
//                  cd'd in (gate_cwd_repo_only). Exempt roots + a .invoker-allow-direct
//                  marker escape. Everything outside the cwd repo is free.
//   SPAWN tools -> never denied. Soft nudge when an invoker specialist (named in the
//                  agent map) is spawned without a decompose marker.

const fs = require('fs');
const os = require('os');
const path = require('path');

function expandHome(p) {
  if (typeof p !== 'string') return p;
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

function deny(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: reason
    }
  }));
  process.exit(0);
}

function ask(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'ask',
      permissionDecisionReason: reason
    }
  }));
  process.exit(0);
}

function nudge(text) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: text
    }
  }));
  process.exit(0);
}

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch (e) {
    return '';
  }
}

// Walk up from a directory to filesystem root, looking for a .git.
// Returns the repo root path, or null if none found.
// Fail-open: any error -> null (do not gate on a detection error).
function gitRepoRoot(dir) {
  try {
    let d = dir;
    while (true) {
      if (fs.existsSync(path.join(d, '.git'))) return d;
      const parent = path.dirname(d);
      if (parent === d) return null; // filesystem root, no repo
      d = parent;
    }
  } catch (e) {
    return null; // fail-open: no repo -> won't gate
  }
}

// Boundary-safe "is target inside root" — avoids /a/b wrongly matching /a/bc.
function isUnder(target, root) {
  if (typeof target !== 'string' || typeof root !== 'string' || !root) return false;
  if (target === root) return true;
  const r = root.endsWith(path.sep) ? root : root + path.sep;
  return target.startsWith(r);
}

try {
  const raw = readStdin();
  let input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    process.exit(0); // unparseable -> fail open
  }
  if (!input || typeof input !== 'object') process.exit(0);

  const toolName = input.tool_name;
  const toolInput = (input.tool_input && typeof input.tool_input === 'object') ? input.tool_input : {};
  const agentId = input.agent_id;
  const sessionId = input.session_id;
  const cwdRaw = input.cwd;

  // 1. Subagent call -> allowed worker. (stays first)
  if (agentId) process.exit(0);

  // 2. Load gate policy. mode off -> allow.
  const policyPath = path.join(os.homedir(), '.invoker', 'gate-policy.json');
  let policy;
  try {
    policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
  } catch (e) {
    process.exit(0); // no policy -> fail open
  }
  if (!policy || typeof policy !== 'object') process.exit(0);
  if (policy.mode === 'off') process.exit(0);

  // 3. Session token. unlocked -> allow.
  let token = { decomposed: false, spawned: false, unlocked: false };
  try {
    const tokenPath = path.join(os.homedir(), '.invoker', 'state', sessionId + '.token');
    const t = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));
    if (t && typeof t === 'object') {
      token.decomposed = !!t.decomposed;
      token.spawned = !!t.spawned;
      token.unlocked = !!t.unlocked;
    }
  } catch (e) {
    // no token -> defaults (all false)
  }
  if (token.unlocked === true) process.exit(0);

  // 4. Tool not gated -> allow.
  const gateTools = Array.isArray(policy.gate_tools) ? policy.gate_tools : [];
  if (!gateTools.includes(toolName)) process.exit(0);

  // ---- Split by tool kind ----

  // A. EDIT TOOLS: Edit | Write | MultiEdit | NotebookEdit
  if (toolName === 'Edit' || toolName === 'Write' || toolName === 'MultiEdit' || toolName === 'NotebookEdit') {
    const base = cwdRaw || process.cwd();
    const targetRaw = toolInput.file_path || toolInput.path || toolInput.notebook_path || cwdRaw || process.cwd();
    let target;
    try { target = path.resolve(base, targetRaw); } catch (e) { target = String(targetRaw || ''); }

    // a) EXEMPT -> ALLOW (exempt_file roots + exempt_marker in any ancestor).
    try {
      const exemptPath = expandHome(policy.exempt_file);
      if (exemptPath) {
        const exemptData = JSON.parse(fs.readFileSync(exemptPath, 'utf8'));
        const entries = (exemptData && Array.isArray(exemptData.exempt)) ? exemptData.exempt : [];
        for (const entry of entries) {
          if (entry && typeof entry.path === 'string' && isUnder(target, entry.path)) process.exit(0);
        }
      }
    } catch (e) { /* continue */ }
    try {
      const marker = policy.exempt_marker;
      if (marker && typeof marker === 'string') {
        let dir = path.dirname(target);
        while (true) {
          if (fs.existsSync(path.join(dir, marker))) process.exit(0);
          const parent = path.dirname(dir);
          if (parent === dir) break;
          dir = parent;
        }
      }
    } catch (e) { /* continue */ }

    // b) Gate ONLY if the target is inside the repo the session is cd'd in.
    if (policy.gate_cwd_repo_only === true) {
      const repoRoot = gitRepoRoot(path.resolve(cwdRaw || process.cwd()));
      if (!repoRoot) process.exit(0);                 // cwd not in a repo -> allow
      if (!isUnder(target, repoRoot)) process.exit(0); // target outside the cwd repo -> allow
      // target IS inside the cwd repo -> apply mode
      if (policy.mode === 'warn') ask('InvokerAI: route this via /invokerai:decompose -> /invokerai:spawn?');
      if (policy.mode === 'always-block') deny('InvokerAI gate: this file is in the active project repo. Main thread is orchestrator-only; spawn a specialist subagent to edit it.');
      if (token.spawned) process.exit(0);
      deny('InvokerAI gate: this file is in the active project repo. Spawn a specialist subagent to edit it.');
    }
    process.exit(0); // gating disabled -> allow
  }

  // B. SPAWN TOOLS: Task | Agent — ensure-not-enforce. Never deny. Nudge when an
  // invoker specialist is spawned without a decompose DAG; otherwise allow silently.
  if (toolName === 'Task' || toolName === 'Agent') {
    try {
      const subagentType = toolInput.subagent_type || toolInput.subagentType || toolInput.agent_type || '';
      if (subagentType && !token.decomposed) {
        const mapData = JSON.parse(fs.readFileSync(expandHome(policy.agent_map), 'utf8'));
        const domains = (mapData && mapData.domains && typeof mapData.domains === 'object') ? mapData.domains : {};
        let isSpecialist = false;
        for (const d of Object.keys(domains)) {
          const list = domains[d];
          if (Array.isArray(list) && list.some(a => a && a.name === subagentType)) { isSpecialist = true; break; }
        }
        if (isSpecialist) {
          nudge('InvokerAI (reminder, not blocking): spawning specialist "' + subagentType + '" with no decompose DAG. For multi-step work, decompose first, then spawn in dependency order. Proceeding anyway.');
        }
      }
    } catch (e) { /* map unreadable -> no nudge */ }
    process.exit(0); // spawns are always allowed
  }

  // default -> allow
  process.exit(0);
} catch (e) {
  process.exit(0); // global fail-open
}
