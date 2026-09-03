---
name: task-plan
description: Create a detailed task implementation plan based on a TRD, it should use the task-planner agent, if no TRD is provided guide the user through
allowed-tools: ["AskUserQuestion", "Agent", "Read", "Glob", "Write", "TaskCreate", "TaskUpdate", "TaskList"]
argument-hint: "[path/to/trd.md or path/to/feature-dir/trd.md, or leave blank to find existing TRDs]"
---

# /task-plan - Implementation Plan Generator

Create a detailed, phased implementation plan from a Technical Requirement Document (TRD). Uses the task-planner agent to analyze the TRD and produce an actionable plan with steps, dependencies, risks, and testing strategy.

## Process

### Step 1: Locate or Obtain the TRD

**If the user provided a file path as argument:**
1. Read the file at the provided path
2. Verify it looks like a TRD or requirements document (has sections like Overview, Requirements, Architecture, etc.)
3. If valid, proceed to Step 2
4. If it doesn't exist or isn't a TRD, tell the user and offer alternatives

**If no arguments were provided:**
1. Search the working directory for existing TRD files using Glob with patterns like `*/trd.md`, `**/*/trd.md`, `*-trd.md`, and `**/*-trd.md`
2. **If TRDs are found**, present them to the user using AskUserQuestion and ask which one to use
3. **If no TRDs are found**, tell the user:
   - "No TRD files found in this directory. You can create one by running `/feature-design` first, which will produce a comprehensive Technical Requirement Document."
   - "Alternatively, you can provide a path to any requirements document: `/task-plan path/to/requirements.md`"
   - Then stop — do not try to gather requirements inline

### Step 2: Launch Task Planner Agent

Once you have the TRD content, spawn the `task-planner` agent using the Agent tool:

```
Use the Agent tool with:
- subagent_type: "corner-office:task-planner"
- prompt: Include the FULL TRD content (not just a summary) along with these instructions:
  "Analyze this Technical Requirement Document and create a comprehensive implementation plan.
   The plan should include:
   - An overview summarizing what will be built
   - All implementation phases with ordered steps
   - For each step: the specific files to create/modify, the action to take, dependencies on other steps, and risk level
   - A testing strategy (unit, integration, e2e)
   - Risks and mitigations
   - Success criteria as a checklist

   Also explore the codebase at [working directory path] to understand existing patterns, conventions, and architecture so the plan is grounded in the actual codebase.

   Return the complete plan in markdown format."
```

**Important**: Pass the ENTIRE TRD content to the agent, not a summary. The agent needs the full picture to plan well.

### Step 3: Save and Present the Plan

After the task-planner agent completes:

1. **Extract the plan** from the agent's response
2. **Derive the output path** from the TRD location:
   - If TRD is inside a feature directory (e.g., `webhook-retry/trd.md`), save as `plan.md` in the same directory (`webhook-retry/plan.md`)
   - If TRD is a flat file (e.g., `webhook-retry-trd.md`), save as `webhook-retry-plan.md` in the same directory (strip `-trd` suffix, append `-plan`)
   - For non-TRD inputs, derive a slug from the document title or feature name, then append `-plan`
3. **Write the plan** alongside the TRD using the Write tool
4. **Present a summary** to the user including:
   - Number of implementation phases
   - Total number of steps
   - Key files that will be created or modified
   - Critical risks identified
   - Where the full plan was saved

### Step 4: Offer Task List Creation

After presenting the plan summary, ask the user using AskUserQuestion:

"Would you like me to create a task list from this plan so you can track implementation progress?"

**If yes:**
1. Read the saved plan file
2. Create tasks using TaskCreate for each major phase or step:
   - Use the phase/step name as the task subject
   - Include the step details and file paths in the description
   - Use an appropriate activeForm (e.g., "Implementing webhook handler")
3. Set up dependencies between tasks using TaskUpdate with addBlockedBy where steps depend on each other
4. Show the user the task list with TaskList

**If no:**
- Tell the user they can refer to the saved plan file at any time

## Example Usage

```
/task-plan docs/IN_PROGRESS/webhook-retry/trd.md
/task-plan webhook-retry-trd.md
/task-plan docs/requirements/auth-redesign.md
/task-plan
```

## Notes

- This command is designed to follow `/feature-design` in the workflow: `/feature-design` produces a TRD, then `/task-plan` turns it into an actionable plan
- The task-planner agent explores the actual codebase to ground the plan in reality
- Plans are saved alongside the TRD — as `plan.md` in the feature directory, or as `[name]-plan.md` for flat TRD files
- The agent uses Opus for thorough analysis and planning
- For very large TRDs, the agent may take a minute or two to analyze everything
