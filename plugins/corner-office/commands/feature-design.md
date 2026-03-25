---
name: feature-design
description: Design a new feature with cross-repository system analysis and produce a Technical Requirement Document (TRD)
command: true
allowed-tools: ["AskUserQuestion", "Task", "Read", "Glob", "Bash"]
argument-hint: "[feature description] [--output-dir path/to/feature/dir]"
---

# /feature-design - Technical Requirement Document Generator

Design a feature by first understanding the full system across all repositories, then producing a comprehensive TRD.

## Process

### Step 1: Gather Feature Requirements

**Parse arguments:** Check if `--output-dir <path>` is present. If so, extract the path and use it as the output directory for the TRD. The remaining arguments are the feature description.

**If the user provided a feature description**, use that as the starting point. Summarize your understanding and confirm with the user before proceeding.

**If no feature description was provided**, walk the user through describing the feature using AskUserQuestion. Ask these questions in sequence (not all at once):

1. **What feature do you want to build?**
   - Get a clear description of the feature
   - Ask follow-up questions if the description is vague

2. **Who is the target user?**
   - End customers, internal admins, API consumers, etc.

3. **What problem does this solve?**
   - Business motivation, user pain point, or technical need

4. **Any constraints or preferences?**
   - Technology preferences, dependencies on other work
   - Specific repos that should or shouldn't be modified

### Step 2: Launch System Architect

Once you have a clear feature description, spawn the `system-architect` agent using the Task tool:

```
Use the Task tool with:
- subagent_type: "corner-office:system-architect"
- prompt: Include the full feature description, target user, problem statement, and any constraints gathered in Step 1. Also include the working directory path so the agent knows where to discover repositories. If --output-dir was provided, include it in the prompt so the agent writes the TRD to that directory.
```

**Important**: Pass ALL context gathered from the user to the agent. The agent needs the complete picture to design well.

### Step 3: Review and Deliver

After the system-architect agent completes:

1. Read the generated TRD file
2. Present a brief summary to the user:
   - Which repos are affected
   - Key architectural decisions made
   - Number of implementation phases
   - Any open questions flagged
3. Tell the user where the TRD file was saved
4. Ask if they want any changes or have questions about the design

## Example Usage

```
/feature-design Add multi-tenant SSO support using SAML 2.0
/feature-design Add a webhook retry mechanism --output-dir docs/IN_PROGRESS/webhook-retry/
/feature-design
```

## Notes

- The system-architect agent will explore ALL repositories in the working directory to understand the full system before designing
- If `--output-dir` is provided, the TRD is saved as `trd.md` in that directory. Otherwise, it is saved as `[feature-name]-trd.md` in the working directory.
- The agent uses Opus for best reasoning quality on complex cross-repo analysis
- For large systems with many repos, discovery may take a few minutes
