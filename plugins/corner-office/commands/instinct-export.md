---
name: instinct-export
description: Export instincts for sharing with teammates or other projects
---

# Instinct Export Command

Exports instincts to a shareable format. Perfect for:
- Sharing with teammates
- Transferring to a new machine
- Contributing to project conventions

## Implementation

Run the instinct CLI:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/scripts/instinct-cli.py export [--output FILE] [--domain DOMAIN] [--min-confidence N]
```

## Usage

```
/instinct-export                           # Export all personal instincts
/instinct-export --domain testing          # Export only testing instincts
/instinct-export --min-confidence 0.7      # Only export high-confidence instincts
/instinct-export --output team-instincts.yaml
```

## Privacy Considerations

Exports include:
- Trigger patterns
- Actions
- Confidence scores
- Domains
- Observation counts

Exports do NOT include:
- Actual code snippets
- File paths
- Session transcripts
- Personal identifiers

## Flags

- `--domain <name>`: Export only specified domain
- `--min-confidence <n>`: Minimum confidence threshold (default: 0.3)
- `--output <file>`: Output file path (default: instincts-export-YYYYMMDD.yaml)
- `--format <yaml|json|md>`: Output format (default: yaml)
- `--include-evidence`: Include evidence text (default: excluded)
