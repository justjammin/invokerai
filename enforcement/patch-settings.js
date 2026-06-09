#!/usr/bin/env node
// Idempotently wire the InvokerAI enforcement hooks into a Claude Code settings.json.
//
// Adds three hook groups (only if absent):
//   PreToolUse    matcher "Edit|Write|MultiEdit|NotebookEdit|Task|Agent"  -> node <hooksDir>/invoker-gate.js
//   PostToolUse   matcher "Task|Agent|Skill"                              -> node <hooksDir>/invoker-mark.js
//   SubagentStart matcher ""                                              -> node <hooksDir>/invoker-mark.js
//
// Idempotency: a group is considered already present if ANY group under that event
// has ANY hook whose `command` string mentions the target script basename. So re-running
// is a no-op, and pre-existing unrelated groups (lean-ctx, pixel-agents, etc.) are untouched.
//
// Usage:
//   node patch-settings.js [settingsPath] [hooksDir]
//     settingsPath  defaults to ~/.claude/settings.json
//     hooksDir      defaults to ~/.claude/hooks   (where invoker-gate.js / invoker-mark.js live)
//
// Writes a timestamped backup (settings.json.bak.<epoch>) before saving any change.

const fs = require('fs');
const os = require('os');
const path = require('path');

function expandHome(p) {
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

const settingsPath = expandHome(process.argv[2] || '~/.claude/settings.json');
const hooksDir = expandHome(process.argv[3] || '~/.claude/hooks');

const gateCmd = 'node ' + JSON.stringify(path.join(hooksDir, 'invoker-gate.js'));
const markCmd = 'node ' + JSON.stringify(path.join(hooksDir, 'invoker-mark.js'));

// Each desired wiring: event, matcher, command, and the script basename used for dedupe.
const DESIRED = [
  { event: 'PreToolUse',    matcher: 'Edit|Write|MultiEdit|NotebookEdit|Task|Agent', command: gateCmd, script: 'invoker-gate.js' },
  { event: 'PostToolUse',   matcher: 'Task|Agent|Skill',                             command: markCmd, script: 'invoker-mark.js' },
  { event: 'SubagentStart', matcher: '',                                            command: markCmd, script: 'invoker-mark.js' }
];

// Load (tolerate a missing or empty file -> start from {}).
let settings = {};
if (fs.existsSync(settingsPath)) {
  const txt = fs.readFileSync(settingsPath, 'utf8');
  if (txt.trim()) settings = JSON.parse(txt); // throws on malformed JSON -> abort loudly, do not clobber
}
if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
  console.error('Refusing to patch: settings root is not a JSON object: ' + settingsPath);
  process.exit(1);
}
if (!settings.hooks || typeof settings.hooks !== 'object' || Array.isArray(settings.hooks)) {
  settings.hooks = {};
}

// Does any group under this event already reference the script basename?
function alreadyWired(eventArr, scriptBasename) {
  if (!Array.isArray(eventArr)) return false;
  for (const group of eventArr) {
    if (!group || !Array.isArray(group.hooks)) continue;
    for (const h of group.hooks) {
      if (h && typeof h.command === 'string' && h.command.includes(scriptBasename)) return true;
    }
  }
  return false;
}

let added = 0;
const report = [];
for (const d of DESIRED) {
  if (!Array.isArray(settings.hooks[d.event])) settings.hooks[d.event] = [];
  const arr = settings.hooks[d.event];
  if (alreadyWired(arr, d.script)) {
    report.push('  = ' + d.event + ' already wired (' + d.script + ') — skipped');
    continue;
  }
  arr.push({ matcher: d.matcher, hooks: [{ type: 'command', command: d.command }] });
  added++;
  report.push('  + ' + d.event + ' matcher "' + d.matcher + '" -> ' + d.command);
}

if (added === 0) {
  console.log('InvokerAI hooks already present — no changes.');
  process.exit(0);
}

// Back up, then write.
const backup = settingsPath + '.bak.' + Date.now();
if (fs.existsSync(settingsPath)) fs.copyFileSync(settingsPath, backup);
const out = JSON.stringify(settings, null, 2) + '\n';
JSON.parse(out); // validate before writing
fs.writeFileSync(settingsPath, out);

console.log('Patched ' + settingsPath + ' (' + added + ' group(s) added). Backup: ' + (fs.existsSync(backup) ? backup : '(none — new file)'));
report.forEach(l => console.log(l));
