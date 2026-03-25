---
name: learned-patterns
description: Auto-extracted patterns from past sessions. Apply these patterns when matching contexts arise - git workflows, Terraform gotchas, and other reusable knowledge.
---

# Learned Patterns

This directory contains patterns extracted from previous sessions using the `/learn` command. Each file documents a specific pattern, workaround, or convention discovered during development.

## How Patterns Are Created

1. During a session, run `/learn` after solving a non-trivial problem
2. The pattern is extracted and saved here as a markdown file
3. Claude Code loads these patterns and applies them when matching contexts arise

## Current Patterns

Check the files in this directory for all learned patterns. Each follows the format:
- **Problem**: What issue was encountered
- **Solution**: How it was resolved
- **When to Use**: Trigger conditions for applying this knowledge
