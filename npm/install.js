#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

// List of skills to install
const SKILLS = [
  { id: 'invokerai', skillDir: 'invokerai', src: 'invokerai/SKILL.md' },
  { id: 'invokerai-setup', skillDir: 'invokerai-setup', src: 'invokerai-setup/SKILL.md' },
  { id: 'invokerai-decompose', skillDir: 'invokerai-decompose', src: 'invokerai-decompose/SKILL.md' },
  { id: 'invokerai-spawn', skillDir: 'invokerai-spawn', src: 'invokerai-spawn/SKILL.md' }
];

function printHelp() {
  console.log(`
invokerai-skills — Install InvokerAI agent routing brain

Usage:
  invokerai-skills [OPTIONS]

Options:
  (no flags)        Copy SKILL.md files to ~/.claude/skills/<id>/
  --user            Symlink full skill directories into ~/.claude/skills and ~/.cursor/skills
  --project         Symlink full skill directories into ./.claude/skills and ./.cursor/skills (cwd)
  --claude-only     With --user/--project, install to Claude Code only
  --cursor-only     With --user/--project, install to Cursor only
  -h, --help        Print this help

Examples:
  invokerai-skills                 # Install to ~/.claude/skills (default)
  invokerai-skills --user          # Symlink into ~/.claude/skills and ~/.cursor/skills
  invokerai-skills --project       # Symlink into ./.claude/skills and ./.cursor/skills
  invokerai-skills --user --claude-only  # Symlink to ~/.claude/skills only
`);
}

function getHomeDir() {
  return os.homedir();
}

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function copyFile(src, dest) {
  ensureDir(path.dirname(dest));
  fs.copyFileSync(src, dest);
}

function symlink(target, link) {
  ensureDir(path.dirname(link));
  // Remove existing symlink or file
  if (fs.existsSync(link) || fs.lstatSync(link)) {
    try {
      fs.unlinkSync(link);
    } catch (e) {
      // ignore
    }
  }
  fs.symlinkSync(target, link, 'dir');
}

function installToClaude() {
  const claudeDir = path.join(getHomeDir(), '.claude');

  if (!fs.existsSync(claudeDir)) {
    console.error(`Error: ~/.claude does not exist. Please create it first.`);
    process.exit(1);
  }

  const skillsDir = path.join(claudeDir, 'skills');
  ensureDir(skillsDir);

  const scriptDir = path.dirname(require.main.filename);
  const pkgSkillDir = path.join(scriptDir, 'skill');

  for (const skill of SKILLS) {
    const srcFile = path.join(pkgSkillDir, skill.src);
    const destDir = path.join(skillsDir, skill.id);
    const destFile = path.join(destDir, 'SKILL.md');

    ensureDir(destDir);
    copyFile(srcFile, destFile);
    console.log(`✓ Installed ${skill.id} to ~/.claude/skills/${skill.id}/SKILL.md`);
  }

  console.log(`\nNext: run /invokerai:setup to build your agent map.`);
}

function symlinkToUser(claudeOnly, cursorOnly) {
  const homeDir = getHomeDir();
  const claudeDir = path.join(homeDir, '.claude');
  const cursorDir = path.join(homeDir, '.cursor');

  if (!fs.existsSync(claudeDir) && !claudeOnly) {
    console.error(`Error: ~/.claude does not exist. Please create it first.`);
    process.exit(1);
  }

  const scriptDir = path.dirname(require.main.filename);
  const pkgSkillDir = path.join(scriptDir, 'skill');

  for (const skill of SKILLS) {
    const srcDir = path.join(pkgSkillDir, skill.skillDir);

    if (!claudeOnly) {
      const claudeSkillsDir = path.join(claudeDir, 'skills');
      ensureDir(claudeSkillsDir);
      const claudeLink = path.join(claudeSkillsDir, skill.id);
      symlink(srcDir, claudeLink);
      console.log(`✓ Symlinked ${skill.id} to ~/.claude/skills/${skill.id}`);
    }

    if (!cursorOnly) {
      const cursorSkillsDir = path.join(cursorDir, 'skills');
      ensureDir(cursorSkillsDir);
      const cursorLink = path.join(cursorSkillsDir, skill.id);
      symlink(srcDir, cursorLink);
      console.log(`✓ Symlinked ${skill.id} to ~/.cursor/skills/${skill.id}`);
    }
  }

  console.log(`\nNext: run /invokerai:setup to build your agent map.`);
}

function symlinkToProject(claudeOnly, cursorOnly) {
  const cwd = process.cwd();
  const claudeDir = path.join(cwd, '.claude');
  const cursorDir = path.join(cwd, '.cursor');

  const scriptDir = path.dirname(require.main.filename);
  const pkgSkillDir = path.join(scriptDir, 'skill');

  for (const skill of SKILLS) {
    const srcDir = path.join(pkgSkillDir, skill.skillDir);

    if (!claudeOnly) {
      const claudeSkillsDir = path.join(claudeDir, 'skills');
      ensureDir(claudeSkillsDir);
      const claudeLink = path.join(claudeSkillsDir, skill.id);
      symlink(srcDir, claudeLink);
      console.log(`✓ Symlinked ${skill.id} to .claude/skills/${skill.id}`);
    }

    if (!cursorOnly) {
      const cursorSkillsDir = path.join(cursorDir, 'skills');
      ensureDir(cursorSkillsDir);
      const cursorLink = path.join(cursorSkillsDir, skill.id);
      symlink(srcDir, cursorLink);
      console.log(`✓ Symlinked ${skill.id} to .cursor/skills/${skill.id}`);
    }
  }

  console.log(`\nNext: run /invokerai:setup to build your agent map.`);
}

function main() {
  const args = process.argv.slice(2);

  if (args.includes('-h') || args.includes('--help')) {
    printHelp();
    process.exit(0);
  }

  const isUser = args.includes('--user');
  const isProject = args.includes('--project');
  const claudeOnly = args.includes('--claude-only');
  const cursorOnly = args.includes('--cursor-only');

  if (isUser && isProject) {
    console.error('Error: --user and --project are mutually exclusive.');
    process.exit(1);
  }

  if (claudeOnly && cursorOnly) {
    console.error('Error: --claude-only and --cursor-only are mutually exclusive.');
    process.exit(1);
  }

  if (isUser) {
    symlinkToUser(claudeOnly, cursorOnly);
  } else if (isProject) {
    symlinkToProject(claudeOnly, cursorOnly);
  } else {
    installToClaude();
  }
}

main();
