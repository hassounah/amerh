# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code + Codex plugin marketplace (`amerh`) containing the `corner-office` plugin. The plugin provides continuous learning via session observation hooks, specialized code review agents, and workflow optimization tools.

## Repository Layout

- `.claude-plugin/marketplace.json` — Marketplace registry (lists available plugins)
- `plugins/corner-office/.claude-plugin/plugin.json` — Plugin manifest
- `plugins/corner-office/.codex-plugin/` — Codex manifest (`plugin.json`) and Codex-only MCP config (`mcp.json`); Codex reads this instead of `.claude-plugin/plugin.json`
- `plugins/corner-office/agents/` — Opus-powered specialist agents (markdown with YAML frontmatter)
- `plugins/corner-office/formulas/` — Named preset formulas (YAML) for /assemble-team
- `plugins/corner-office/hooks/hooks.json` — Hook registration (22 events)
- `plugins/corner-office/skills/` — Skills, including the 13 user-invoked pipeline/learning skills (each has `SKILL.md`; Claude-only ones carry `agents/openai.yaml` to disable Codex implicit invocation)

## Key Architecture: Continuous Learning System

The core innovation is an instinct-based learning pipeline:

1. **Hooks** (`hooks.json` → `observe.sh`) capture all tool use as JSONL to `~/.claude/homunculus/observations.jsonl`
2. **Observer** analyzes observations and extracts atomic "instincts" (YAML frontmatter files with id, trigger, confidence 0.3–0.9, domain)
3. **Skills** (`/learn`, `/evolve`, `/instinct-status`, `/instinct-export`, `/instinct-import`) let the user manage instincts
4. **Evolution** clusters related instincts into higher-level skills, commands, or agents

Runtime data lives in `~/.claude/homunculus/` (observations, instincts, evolved artifacts). Observation can be disabled by creating `~/.claude/homunculus/disabled`.

## Running Tests

There is no project venv, so use an ephemeral `uv` environment:

```bash
uv run --no-project --with pytest --with pyyaml python -m pytest \
  plugins/corner-office/scripts/tests/ \
  plugins/corner-office/skills/continuous-learning-v2/scripts/ -q -p no:cacheprovider
```

## Component Authoring Conventions

- **Agents**: Markdown files with YAML frontmatter (`name`, `description`, `tools`, `model`). System prompt is the markdown body.
- **Skills**: Directory with `SKILL.md` entry point. May contain sub-directories for hooks, agents, scripts, config. User-invoked skills keep `allowed-tools`/`argument-hint` in frontmatter; invoked as `/corner-office:<name>` (Claude Code) or `$<name>` (Codex).
- **Hooks**: Registered in `hooks.json` using `${CLAUDE_PLUGIN_ROOT}` for portable paths. Hook scripts receive JSON on stdin. `hooks.json` must contain only `description`/`hooks` top-level keys — Codex rejects unknown keys and drops all hooks.
- **Versions**: Every release sets one plugin version everywhere: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, the corner-office entry in `marketplace.json` (`plugins[].version`), the README version table, `servers/mcp/pyproject.toml` (then `uv lock` in `servers/mcp/`), and the channel server's `pyproject.toml`, `server.py` and `server.ts`. Also bump the marketplace's own `metadata.version`, which has its own numbering.
- **Codex**: Codex does not substitute `${CLAUDE_PLUGIN_ROOT}` in MCP config or skill text.
- **Instinct files**: YAML frontmatter (`id`, `trigger`, `confidence`, `domain`, `source`) followed by markdown body with `## Problem`, `## Action`, `## Example` sections.

## Plugin Installation (for testing)

```bash
# Claude Code
/plugin marketplace add hassounah/amerh
/plugin install corner-office@amerh

# Codex
codex plugin marketplace add hassounah/amerh
codex plugin add corner-office@amerh
```
