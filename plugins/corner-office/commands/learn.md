---
name: learn
description: Extract reusable patterns from the current session
---

# /learn - Extract Reusable Patterns

Analyze the current session and extract any patterns worth saving as skills.

## Trigger

Run `/learn` at any point during a session when you've solved a non-trivial problem.

## What to Extract

Look for:

1. **Error Resolution Patterns**
   - What error occurred?
   - What was the root cause?
   - What fixed it?
   - Is this reusable for similar errors?

2. **Debugging Techniques**
   - Non-obvious debugging steps
   - Tool combinations that worked
   - Diagnostic patterns

3. **Workarounds**
   - Library quirks
   - API limitations
   - Version-specific fixes

4. **Project-Specific Patterns**
   - Codebase conventions discovered
   - Architecture decisions made
   - Integration patterns

## Output Format

Create an instinct file at `~/.claude/homunculus/instincts/personal/[pattern-name].yaml` using YAML frontmatter format:

```yaml
---
id: [kebab-case-pattern-name]
trigger: "[when this pattern applies - a short phrase]"
confidence: [0.5-1.0 based on how proven the pattern is]
domain: [category: e.g. claude-code-plugins, git, testing, go, python, security, workflow, infrastructure]
source: session-observation
---

## Problem
[What problem this solves - be specific]

## Action
[The pattern/technique/workaround - what to do]

## Example
[Code example if applicable]
```

### Field Guidelines

- **id**: Unique kebab-case identifier (matches filename without extension)
- **trigger**: Short phrase describing when this instinct activates (e.g. "when creating Go HTTP handlers")
- **confidence**: Start at 0.5 for new patterns, 0.7 for well-tested, 0.9 for battle-proven
- **domain**: Group related instincts (use existing domains when possible)
- **source**: Always `session-observation` for `/learn` extractions

## Process

1. Review the session for extractable patterns
2. Identify the most valuable/reusable insight
3. Draft the instinct file in YAML frontmatter format
4. Ask user to confirm before saving
5. Save to `~/.claude/homunculus/instincts/personal/[pattern-name].yaml`

## Notes

- Don't extract trivial fixes (typos, simple syntax errors)
- Don't extract one-time issues (specific API outages, etc.)
- Focus on patterns that will save time in future sessions
- Keep instincts focused - one pattern per file
- Use `.yaml` extension - the instinct CLI (`/instinct-status`) only reads `*.yaml` files
