---
name: instinct-status
description: Show all learned instincts with their confidence levels
---

# Instinct Status Skill

Shows all learned instincts with their confidence scores, grouped by domain.

## Implementation

Run the instinct CLI:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/scripts/instinct-cli.py status
```

If the plugin-root variable in that command is not expanded, replace it with the plugin root: the directory that contains `skills/`, `hooks/` and `agents/`.

## Usage

```
/instinct-status
/instinct-status --domain code-style
/instinct-status --low-confidence
```

## What to Do

1. Read all instinct files from `~/.claude/homunculus/instincts/personal/`
2. Read inherited instincts from `~/.claude/homunculus/instincts/inherited/`
3. Display them grouped by domain with confidence bars

## Flags

- `--domain <name>`: Filter by domain (code-style, testing, git, etc.)
- `--low-confidence`: Show only instincts with confidence < 0.5
- `--high-confidence`: Show only instincts with confidence >= 0.7
- `--source <type>`: Filter by source (session-observation, repo-analysis, inherited)
- `--json`: Output as JSON for programmatic use
