# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code plugin marketplace (`amerh`) containing the `corner-office` plugin. The plugin provides continuous learning via session observation hooks, specialized code review agents, and workflow optimization tools.

## Repository Layout

- `.claude-plugin/marketplace.json` — Marketplace registry (lists available plugins)
- `plugins/corner-office/.claude-plugin/plugin.json` — Plugin manifest
- `plugins/corner-office/agents/` — Opus-powered specialist agents (markdown with YAML frontmatter)
- `plugins/corner-office/commands/` — Slash commands (markdown with YAML frontmatter)
- `plugins/corner-office/formulas/` — Named preset formulas (YAML) for /assemble-team
- `plugins/corner-office/hooks/hooks.json` — Hook registration (PreToolUse/PostToolUse)
- `plugins/corner-office/skills/` — Skill bundles (each has a `SKILL.md` entry point)

## Key Architecture: Continuous Learning System

The core innovation is an instinct-based learning pipeline:

1. **Hooks** (`hooks.json` → `observe.sh`) capture all tool use as JSONL to `~/.claude/homunculus/observations.jsonl`
2. **Observer** analyzes observations and extracts atomic "instincts" (YAML frontmatter files with id, trigger, confidence 0.3–0.9, domain)
3. **Commands** (`/learn`, `/evolve`, `/instinct-status`, `/instinct-export`, `/instinct-import`) let the user manage instincts
4. **Evolution** clusters related instincts into higher-level skills, commands, or agents

Runtime data lives in `~/.claude/homunculus/` (observations, instincts, evolved artifacts). Observation can be disabled by creating `~/.claude/homunculus/disabled`.

## Running Tests

```bash
# Run instinct parser tests (only test suite in the repo)
python -m pytest plugins/corner-office/skills/continuous-learning-v2/scripts/test_parse_instinct.py -v
```

## Component Authoring Conventions

- **Agents**: Markdown files with YAML frontmatter (`name`, `description`, `tools`, `model`). System prompt is the markdown body.
- **Commands**: Markdown files with `command: true` in frontmatter. Invoked via `/command-name`.
- **Skills**: Directory with `SKILL.md` entry point. May contain sub-directories for hooks, agents, scripts, config.
- **Hooks**: Registered in `hooks.json` using `${CLAUDE_PLUGIN_ROOT}` for portable paths. Hook scripts receive JSON on stdin.
- **Instinct files**: YAML frontmatter (`id`, `trigger`, `confidence`, `domain`, `source`) followed by markdown body with `## Problem`, `## Action`, `## Example` sections.

## Plugin Installation (for testing)

```bash
/plugin marketplace add hassounah/amerh
/plugin install corner-office@amerh
```
