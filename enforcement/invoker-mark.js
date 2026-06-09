#!/usr/bin/env node
// InvokerAI PostToolUse marker writer.
// Records routing progress (decomposed/spawned) into the per-session token.
// Fail-open: on ANY error, exit 0.

const fs = require('fs');
const os = require('os');
const path = require('path');

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch (e) {
    return '';
  }
}

try {
  const raw = readStdin();
  let input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    process.exit(0);
  }
  if (!input || typeof input !== 'object') process.exit(0);

  const toolName = input.tool_name;
  const toolInput = input.tool_input;
  const sessionId = input.session_id;
  const agentId = input.agent_id;
  const eventName = input.hook_event_name;

  // No session -> nothing to track.
  if (!sessionId) process.exit(0);

  const stateDir = path.join(os.homedir(), '.invoker', 'state');
  const tokenPath = path.join(stateDir, sessionId + '.token');

  function loadToken() {
    const token = { decomposed: false, spawned: false, unlocked: false };
    try {
      const t = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));
      if (t && typeof t === 'object') {
        token.decomposed = !!t.decomposed;
        token.spawned = !!t.spawned;
        token.unlocked = !!t.unlocked;
      }
    } catch (e) {
      // no existing token -> defaults
    }
    return token;
  }
  function saveToken(token) {
    try {
      fs.mkdirSync(stateDir, { recursive: true });
      fs.writeFileSync(tokenPath, JSON.stringify(token));
    } catch (e) {
      // ignore write failure
    }
  }

  // SubagentStart belt: a subagent starting means routing happened this session,
  // so mark spawned/decomposed BEFORE the subagent makes any tool calls. This is
  // what allows subagent edits even if PreToolUse payloads omit agent_id.
  // Runs BEFORE the agent_id guard, since SubagentStart payloads carry agent_id.
  if (eventName === 'SubagentStart') {
    const token = loadToken();
    token.spawned = true;
    token.decomposed = true;
    saveToken(token);
    process.exit(0);
  }

  // Ignore tool calls made INSIDE a subagent (PostToolUse with agent_id present).
  if (agentId) process.exit(0);

  // PostToolUse detection on the main thread.
  const token = loadToken();
  let inputStr = '';
  try {
    inputStr = JSON.stringify(toolInput);
  } catch (e) {
    inputStr = '';
  }
  if (typeof inputStr !== 'string') inputStr = '';

  const name = typeof toolName === 'string' ? toolName : '';

  if (name === 'Task' || name === 'Agent') {
    token.spawned = true;
    token.decomposed = true;
  } else if (name === 'Skill' && /invokerai[:_-]?decompose/i.test(inputStr)) {
    token.decomposed = true;
  } else if (name === 'Skill' && /invokerai[:_-]?spawn/i.test(inputStr)) {
    token.spawned = true;
    token.decomposed = true;
  } else if (/invokerai.*decompose/i.test(name)) {
    token.decomposed = true;
  } else if (/invokerai.*spawn/i.test(name)) {
    token.spawned = true;
    token.decomposed = true;
  }

  saveToken(token);
  process.exit(0);
} catch (e) {
  process.exit(0);
}
