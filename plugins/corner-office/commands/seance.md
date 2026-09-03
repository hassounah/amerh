---
name: seance
description: Recover context from past handoff documents after compaction or session restart. Auto-loads the most recent handoff or browse history with --list.
allowed-tools: ["Read", "Glob", "AskUserQuestion"]
argument-hint: "[--list]"
---

# /seance — Context Recovery from Handoffs

Recover working context from handoff documents created by the PreCompact hook during context compaction or session restart.

## Process

### Step 1: Parse Arguments

Check the arguments for the `--list` flag.

### Step 2: Locate Handoff Files

1. Check if `.rix/active-pipeline.md` exists in the current working directory or any parent directory.
   - If found, read it and extract the `Feature dir` field from `- **Feature dir**: <path>` lines.
   - If a Feature dir is found, glob `{feature_dir}/handoffs/handoff-*.md` to find feature-specific handoffs.

2. Always also glob `~/.claude/homunculus/handoffs/handoff-*.md` for global handoffs.

3. Combine all results. Sort by filename descending (newest first — filenames use `YYYY-MM-DD_HHMMSS` format).

### Step 3: Display or Auto-Load

**If `--list` flag is present:**
1. Display all handoffs as a numbered list. For each, show:
   - Number and filename (timestamp extracted from name)
   - Feature name (parsed from `# Handoff:` header line in the file)
   - Working directory and git branch (parsed from `## Working Directory` and `## Git Branch` sections in the file)
   - Format: `1. 2026-03-07_143022 — Feature Name (~/my-project, branch: main)`
2. Use AskUserQuestion to ask the user: "Which handoff would you like to load? (enter number)"
3. Read and display the selected handoff in full.

**If no flag (default — auto-load most recent):**
1. Read the most recent handoff file.
2. Display a structured summary:
   - **Pipeline State** section contents
   - **Task Progress** (completed vs pending counts and pending task list)
   - **Working Directory** and **Git Branch**
3. Output: "Context recovered from handoff at {timestamp}. Read the key files listed above to fully restore working context."

**If no handoff files found:**
Tell the user: "No handoff files found. Handoffs are created automatically when Claude compacts context. They are stored in `{feature_dir}/handoffs/` (if an active pipeline is detected) or `~/.claude/homunculus/handoffs/` (global fallback)."

### Step 4: Cross-Reference Pipeline Context

If the loaded handoff references an active pipeline (Pipeline State section is present and non-empty):
1. Check if `.rix/memory.md` exists.
2. If found, read it to load additional project context.
3. Summarize any relevant context from memory.md alongside the handoff summary.
