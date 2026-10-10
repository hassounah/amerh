---
name: implement
description: Launch an implementation team that autonomously implements a plan through a 2-gate quality pipeline. Default (2 devs, cross-review) or --full-team (2 devs + 2 reviewer-testers).
allowed-tools: ["AskUserQuestion", "Agent", "Read", "Write", "Glob", "Grep", "Bash", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
argument-hint: "[--full-team] [path/to/plan-file.md]"
---

# /implement - Implementation Team (v7)

## Modes

### Default: 2-Dev Pipeline (recommended)

- **Team**: dev-1, dev-2
- **Pipeline**: implement → review+verify (2 gates, merged)
- **Assignment**: dev-1 implements odd steps and review+verifies even steps; dev-2 does the inverse
- **Best for**: Most implementations. ~40-50% fewer tokens than full-team.

### --full-team: 4-Agent Pipeline

- **Team**: dev-1, dev-2, reviewer-tester-1, reviewer-tester-2
- **Pipeline**: implement → review+verify by dedicated reviewers (2 gates)
- **Assignment**: dev-1 and dev-2 implement full-time; reviewer-tester-1 and reviewer-tester-2 split all review+verify (odd/even)
- **Best for**: Large implementations (20+ steps) where devs should stay focused on implementation.

## Optimizations (both modes)

These are baked into all prompts and task structures:

1. **Idle protocol**: Agents send ONE "blocked/empty" message, then go SILENT. No periodic updates. Pre-read source code while waiting.
2. **Threshold reviewer subagents**: <200 lines changed = review code directly. ≥200 lines = spawn specialist (go-reviewer, python-reviewer, database-reviewer, ux-dx-architect) via the Agent tool (`subagent_type: go-reviewer` etc).
3. **Per-step dependency flow**: No artificial phase gates. Steps flow based on explicit plan dependencies + file conflict detection (function-level when line numbers available, file-level fallback). Steps that don't conflict run in parallel even across phases.
4. **Reduced prompts**: Agents get a brief feature overview + their task queue (subjects only). Full step details live in TaskList descriptions, read via TaskGet when claiming a task.
5. **Event-driven coordination**: Team lead reacts to agent messages instead of polling. After every task completion, immediately checks for and notifies agents of unblocked tasks.
6. **Trivial step batching**: Steps with <20 lines, single file, no complex logic are batched 2-3 together into one implement + one review+verify task.
7. **Scoped test commands**: Each task includes a narrowed test scope (e.g., `go test ./internal/security/...`) instead of running full suite. Full suite only in the Final task.
8. **Trust task descriptions**: Agents read only the files mentioned in task descriptions. No broad codebase exploration unless code doesn't match expectations.
9. **No commits**: Agents focus on implementation/review only. No git commits — the user commits when ready.

## Process

### Step 1: Parse Arguments

Parse the user's arguments:

- **`--full-team` flag**: If present, use 4-agent mode. Otherwise, default 2-dev mode.
- **Plan file path**: Everything that isn't `--full-team` is the plan file path.

Examples:
- `/implement feature-plan.md` → default mode, specified plan
- `/implement --full-team feature-plan.md` → full-team mode, specified plan
- `/implement --full-team` → full-team mode, search for plans
- `/implement` → default mode, search for plans

### Step 2: Locate the Plan

**If a plan file path was provided:**
1. Read the file at the provided path
2. Verify it looks like an implementation plan (has phases, steps, tasks)
3. If valid, proceed to Step 3
4. If not found or not a plan, tell the user and suggest running `/task-plan` first

**If no plan path provided:**
1. Search for plan files using Glob: `*/plan.md`, `**/*/plan.md`, `*-plan.md`, and `**/*-plan.md`
2. If plans found, present them using AskUserQuestion and ask which one to use
3. If no plans found, tell the user: "No plan files found. Run `/task-plan` first." Then stop.

### Step 2b: Derive Slug and Feature Directory

Derive a slug and feature directory from the plan file path:

- If the plan is inside a feature directory (e.g., `docs/IN_PROGRESS/webhook-retry/plan.md`), use the parent directory name as slug (`webhook-retry`) and the parent directory as `{feature_dir}`
- Flat file fallback: strip the `-plan` suffix and `.md` extension: `dashboard-branding-refresh-plan.md` → slug = `dashboard-branding-refresh`. In this case, `{feature_dir}` is the directory containing the plan file.

The slug is used for the team name. The feature directory is used for the team work dir, task list, and report output.

### Step 2c: Determine Team Work Directory

Check if `--team-dir` was provided in the arguments:
- If provided (e.g., `--team-dir .02-impl-team`): use `{feature_dir}/{team_dir}/` as the team work directory
- If not provided: default to `{feature_dir}/{team_dir}/`

Use this team work directory everywhere that previously referenced `.impl-team/` — reports, final-report, retrospective.

### Step 3: Parse Plan, Detect Conflicts, Create Tasks

#### 3a: Extract Steps

Read the plan and extract implementation steps. Expected format (from `/task-plan`):

```markdown
## Implementation Steps

### Phase 1: [Phase Name]
1. **[Step Name]** (File: path/to/file)
   - Action: Specific action to take
   - Why: Reason for this step
   - Dependencies: None / Requires step X
   - Risk: Low/Medium/High
```

Number steps sequentially across all phases (Step 1, Step 2, ... Step N).

**Best-effort parsing**: If the format doesn't match exactly, extract work items from numbered lists, headers, bullet points, or any structured breakdown. Preserve any stated dependencies.

#### 3b: Detect File Conflicts

For each step, note which files it modifies and which line ranges/functions it affects (if the plan provides line numbers).

**Function-level granularity** (when line numbers are available):
- If Step A modifies `file.go` at lines 100-150 and Step B modifies `file.go` at lines 500-550, they can run in parallel — different functions, no overlap
- Only create a file conflict dependency if the line ranges overlap or are within 50 lines of each other
- If a step adds code to a file without specific line numbers, treat it as a full-file conflict

**File-level fallback** (when no line numbers):
- If Step A and Step B both modify the same file(s) and A comes before B in the plan, then Step B's **Implement** task must be blocked by Step A's **Review+Verify** task

In both cases:
- This ensures changes to the same code region complete their full pipeline before another step modifies that region
- Add these as implicit dependencies alongside any explicit dependencies from the plan

This provides finer-grained parallelism than both phase gates and simple file-level conflict detection.

#### 3c: Create Tasks

**For each step**, create TWO tasks:

1. **"Implement: [Step Name]"**
   - Description: Include all step details from the plan — action, file paths, why, context, acceptance criteria
   - Owner: alternate dev-1 (odd) / dev-2 (even)
   - Dependencies: explicit plan dependencies + file conflict dependencies (blocked by the Review+Verify task of any conflicting earlier step)

2. **"Review+Verify: [Step Name]"**
   - Description: "Review and verify '[Step Name]'. Check code quality, run tests, verify >85% coverage, write integration tests, check acceptance criteria. If change ≥200 lines, spawn reviewer subagent. Write report to `{feature_dir}/{team_dir}/reports/review-[step-name].md`."
   - **Default mode**: owner is the OTHER developer (dev-1 implemented → dev-2 reviews; vice versa)
   - **Full-team mode**: owner is reviewer-tester-1 (odd steps) / reviewer-tester-2 (even steps)
   - Blocked by: the corresponding "Implement" task

#### 3d: Batch Trivial Steps

Before creating tasks, identify trivial steps — those estimated at <20 lines changed, targeting a single file, with no complex logic changes (e.g., adding entries to an array, renaming a field, adding env vars).

Batch 2-3 adjacent trivial steps into a single combined task:
- Create ONE "Implement: [Step X + Step Y + Step Z]" task instead of three separate ones
- Create ONE "Review+Verify: [Step X + Step Y + Step Z]" task
- Include all step details in the combined task description
- Dependencies: combine all dependencies from the individual steps
- Owner assignment: follows the same odd/even pattern as regular tasks

This reduces overhead for small changes that would otherwise each go through the full pipeline with separate test runs.

#### 3e: Write Task List to Disk

After creating all tasks, write a markdown checklist to the feature directory: `{feature_dir}/task-list.md`.

```markdown
# Task List: [feature-name]

- [ ] Implement: Step 1 - [name]
- [ ] Review+Verify: Step 1 - [name]
- [ ] Implement: Step 2 - [name]
- [ ] Review+Verify: Step 2 - [name]
...
- [ ] Final: Run full test suites
```

This file is the on-disk progress checkpoint. If the session dies or context compacts mid-implementation, the resumed session reads this file to determine what's done vs pending — preventing redundant re-assignments.

**Write this file BEFORE spawning the team** so it exists from the start.

#### 3f: Include Test Scope

For each task, determine the narrowest test scope based on the affected files:

- Go: If changes are in `internal/security/`, test scope is `go test ./internal/security/...` not `go test ./...`
- Python: If changes are in `app/auth/`, test scope is `pytest app/auth/` not `pytest`
- Node: If changes are in `src/components/`, test scope is `npx jest src/components/` not `npm test`

Include the scoped test command in the task description:
```
Test scope: go test ./internal/security/...
Full suite: go test ./... (only for Final task)
```

Agents use the scoped test command for self-checks and review verification. The full test suite runs only in the Final task.

After ALL steps, create one final task:

3. **"Final: Run full test suites"**
   - Description: "Run complete test suites (`go test -race ./...`, `pytest -v`, etc.) and linters across all affected repositories. Write report to `{feature_dir}/{team_dir}/final-report.md`. IMPORTANT: The report MUST include a Review Reports table listing EVERY review report file from `{feature_dir}/{team_dir}/reports/`. Glob the directory and list all paths — do not omit any."
   - **Default mode**: owner is dev-1
   - **Full-team mode**: owner is reviewer-tester-1
   - Blocked by: ALL "Review+Verify" tasks

**Assignment patterns:**

Default mode (interleaved):
```
dev-1 queue: Implement 1 → Review+Verify 2 → Implement 3 → Review+Verify 4 → ... → Final
dev-2 queue: Implement 2 → Review+Verify 1 → Implement 4 → Review+Verify 3 → ...
```

Full-team mode (separated):
```
dev-1 queue:             Implement 1 → Implement 3 → Implement 5 → ...
dev-2 queue:             Implement 2 → Implement 4 → Implement 6 → ...
reviewer-tester-1 queue: Review+Verify 1 → Review+Verify 3 → Review+Verify 5 → ... → Final
reviewer-tester-2 queue: Review+Verify 2 → Review+Verify 4 → Review+Verify 6 → ...
```

### Step 4: Spawn Agents

1. Create the reports directory: `mkdir -p {feature_dir}/{team_dir}/reports`
2. Prepare a **brief feature overview** (2-3 sentences summarizing what the plan implements). This goes in every agent prompt instead of the full plan content.

3. Spawn agents **in parallel** (single message with 2 or 4 Agent tool calls). Pass each agent a `name` (`dev-1`, `dev-2`, ...) — they join the session's implicit team and become addressable by that name via `SendMessage`.

#### Default mode — spawn 2 agents

**Dev-1 prompt (default mode):**
```
You are dev-1 on a 2-dev implementation team. Your teammate is dev-2 (peer developer). Team lead coordinates.

Feature overview: [2-3 SENTENCE SUMMARY OF WHAT'S BEING BUILT]

Working directory: [PATH]

## Your Task Queue (work in this order)

[LIST TASK SUBJECTS ASSIGNED TO DEV-1, e.g.:
1. Implement: Step 1 - Add rate limiter middleware
2. Review+Verify: Step 2 - Add circuit breaker to HTTP client
3. Implement: Step 3 - Add health check endpoint
4. Review+Verify: Step 4 - Add graceful shutdown handler
...]

## Rules (NON-NEGOTIABLE)

1. **Work from YOUR queue only.** Do not claim dev-2's tasks.
2. **Review+Verify before next Implement.** After completing any Implement task, you MUST complete all unblocked Review+Verify tasks in your queue before starting the next Implement.
3. **Never review your own code.** You only review+verify code implemented by dev-2.
4. **Self-check before handoff.** Run linter, tests (use scoped test command from task description), verify >85% coverage on every implementation before marking complete.
5. **Threshold reviewer subagents.** For Review+Verify tasks: if the change is ≥200 lines, spawn the appropriate specialist reviewer (go-reviewer for .go, python-reviewer for .py, database-reviewer for SQL, ux-dx-architect for frontend) via the Agent tool (`subagent_type: go-reviewer` etc). If <200 lines, review the code directly yourself.
6. **Write reports to files.** Write full review+verify reports to `{feature_dir}/{team_dir}/reports/review-[step-name].md`. Send ONLY brief status messages (1 line).
7. **Plan-reality mismatches: STOP and message team lead.**
8. **Idle protocol.** If your queue is empty or fully blocked, send ONE message: "Queue empty" or "Queue blocked". Then go SILENT. Pre-read source code for upcoming tasks while waiting. Do NOT send periodic status updates. You will be messaged when work is available.
9. **No git commits.** Do NOT create git commits. Focus on implementation and review only. The user will commit when ready.
10. **Trust task descriptions.** Task descriptions include exact file paths, line numbers, and code context. Read only the files mentioned. Do NOT explore the broader codebase unless the code doesn't match.

## Review+Verify Checklist

When working a Review+Verify task:
1. Use TaskGet to read the full task description
2. Read changed files (check git diff or read directly) — read only the files mentioned, do not explore broadly
3. Count lines changed — if ≥200, spawn reviewer subagent; if <200, review directly
4. Check for bugs, security issues, code quality
5. Run tests using the **scoped test command from the task description** (NOT full suite)
6. Check coverage >85% on changed code
7. Write integration tests (happy path + key error paths)
8. Check acceptance criteria from the task description
9. Write full report to `{feature_dir}/{team_dir}/reports/review-[step-name].md`
10. APPROVED: mark task complete, send "Review+Verify [task]: APPROVED"
11. BLOCKED: create Fix task for implementer, send "Review+Verify [task]: BLOCKED — [count] issues. See report."

## Final Task

Your queue includes the Final task (blocked until all Review+Verify complete):
- Run complete test suites (`go test -race ./...`, `pytest -v`, etc.) and linters across all affected repositories
- Write report to `{feature_dir}/{team_dir}/final-report.md`
- The report MUST include a Review Reports table listing EVERY review report file from `{feature_dir}/{team_dir}/reports/` — glob the directory and list all paths, do not omit any

Use TaskGet to read full task descriptions when claiming tasks. Start by checking TaskList and claiming your first task.
```

**Dev-2 prompt (default mode):**
Same structure as Dev-1 but:
- Role is "dev-2"
- Queue contains dev-2's tasks (even implements, odd review+verifies)
- Reviews dev-1's code
- Owner set to "dev-2"

#### Full-team mode — spawn 4 agents

**Dev-1 prompt (full-team mode):**
```
You are dev-1 on a 4-agent implementation team. Teammates: dev-2 (peer developer), reviewer-tester-1 and reviewer-tester-2 (handle all reviews). Team lead coordinates.

Feature overview: [2-3 SENTENCE SUMMARY]

Working directory: [PATH]

## Your Task Queue

[LIST IMPLEMENT-ONLY TASKS, e.g.:
1. Implement: Step 1 - Add rate limiter middleware
2. Implement: Step 3 - Add health check endpoint
3. Implement: Step 5 - Add metrics collector
...]

## Rules (NON-NEGOTIABLE)

1. **Work from YOUR queue only.** Do not claim dev-2's or reviewer-tester's tasks.
2. **Self-check before handoff.** Run linter, tests (use scoped test command from task description), verify >85% coverage on every implementation before marking complete.
3. **Plan-reality mismatches: STOP and message team lead.**
4. **Idle protocol.** If queue empty or blocked, send ONE message: "Queue empty/blocked". Then go SILENT. Pre-read source code for upcoming tasks. You will be messaged when work is available.
5. **No git commits.** Do NOT create git commits. Focus on implementation only. The user will commit when ready.
6. **Trust task descriptions.** Task descriptions include exact file paths, line numbers, and code context. Read only the files mentioned. Do NOT explore the broader codebase unless the code doesn't match.

Use TaskGet to read full task descriptions. Start by checking TaskList.
```

**Dev-2 prompt (full-team mode):**
Same as Dev-1 full-team but with dev-2's queue (even implements).

**Reviewer-tester-1 prompt (full-team mode):**
```
You are reviewer-tester-1 on a 4-agent implementation team. Teammates: dev-1, dev-2 (developers), reviewer-tester-2 (peer reviewer). Team lead coordinates.

Feature overview: [2-3 SENTENCE SUMMARY]

Working directory: [PATH]

## Your Task Queue

[LIST ODD REVIEW+VERIFY TASKS + FINAL TASK, e.g.:
1. Review+Verify: Step 1 - Add rate limiter middleware
2. Review+Verify: Step 3 - Add health check endpoint
3. Review+Verify: Step 5 - Add metrics collector
...
N. Final: Run full test suites
]

## Rules (NON-NEGOTIABLE)

1. **Work from YOUR queue only.**
2. **Threshold reviewer subagents.** If change ≥200 lines, spawn specialist reviewer (go-reviewer, python-reviewer, database-reviewer, ux-dx-architect) via the Agent tool (`subagent_type: go-reviewer` etc). If <200 lines, review directly.
3. **Write reports to files.** Write all reports to `{feature_dir}/{team_dir}/reports/review-[step-name].md`. Send ONLY brief status messages (1 line).
4. **Pre-read while waiting.** Read source code for upcoming tasks while blocked. This is your highest-value use of wait time.
5. **Idle protocol.** If queue fully blocked, send ONE message: "Queue blocked". Then go SILENT. Pre-read code. You will be messaged when work is available.
6. **No git commits.** Do NOT create git commits. Focus on review and verification only. The user will commit when ready.
7. **Trust task descriptions.** Task descriptions include exact file paths, line numbers, and code context. Read only the files mentioned initially. Do NOT explore the broader codebase unless the code doesn't match.

## Review+Verify Checklist

For each Review+Verify task:
1. Use TaskGet to read the full task description
2. Read changed files (check git diff or read directly) — read only the files mentioned, do not explore broadly
3. Count lines changed — if ≥200, spawn reviewer subagent; if <200, review directly
4. Check for bugs, security issues, code quality
5. Run tests using the **scoped test command from the task description** (NOT full suite)
6. Check coverage >85% on changed code
7. Write integration tests (happy path + key error paths)
8. Check acceptance criteria from the task description
9. Write full report to `{feature_dir}/{team_dir}/reports/review-[step-name].md`
10. APPROVED: mark task complete, send "Review+Verify [task]: APPROVED"
11. BLOCKED: create Fix task for implementer, send "Review+Verify [task]: BLOCKED — [count] issues. See report."

For the Final task:
1. Run complete test suites with -race flag across all affected repos
2. Run linters (go vet, ruff check, eslint)
3. Check for cross-step regressions
4. List ALL review report paths from `{feature_dir}/{team_dir}/reports/` in the Review Reports table — glob the directory, do not rely on memory
5. Write report to `{feature_dir}/{team_dir}/final-report.md`

Use TaskGet to read full task descriptions. Start by checking TaskList. Pre-read plan while waiting for first tasks to unblock.
```

**Reviewer-tester-2 prompt (full-team mode):**
Same structure as reviewer-tester-1 but:
- Role is "reviewer-tester-2"
- Queue contains even Review+Verify tasks (Step 2, Step 4, Step 6, ...)
- Does NOT own the Final task
- Owner set to "reviewer-tester-2"

### Step 5: Coordinate (Event-Driven)

**Do NOT poll.** Do not loop on `TaskList` or `sleep`. React to agent messages only.

#### After each agent message:

1. **Process the message:**
   - Task completion → update the on-disk task list (`{feature_dir}/task-list.md` — change `- [ ]` to `- [x]` for the completed task), then proceed to step 2
   - "Queue empty" → check for unassigned work, assign if available
   - "Queue blocked" → check for stuck dependencies (3+ fix cycles → escalate to user via AskUserQuestion)
   - Plan-reality mismatch → review and respond with guidance

2. **Wake up blocked agents:**
   After any task completion, immediately run TaskList to check if any tasks just unblocked. If a newly unblocked task has an assigned owner (another agent), send them a message: "Task '[task name]' is now unblocked — proceed."

   This eliminates 60-90 seconds of dead time per dependency chain step. Over a typical run with 5 dependency chains, that's ~8 minutes of saved wall-clock time.

3. **Go idle.** After processing and sending any wake-up messages, stop. Wait for the next agent message. Do not poll.

#### Rules:
- **Do NOT respond to idle messages** — agents go silent after one message. Responding wastes tokens.
- **Do NOT micromanage** — pre-assigned queues and dependencies handle orchestration.
- **Do NOT poll TaskList in a loop** — react to messages only.
- **DO wake up blocked agents** after every task completion — this is your primary coordination job.
- **DO escalate stuck tasks** (3+ fix cycles) to the user via AskUserQuestion.
- **DO run stall detection** after every message — check all agents with in-progress tasks against the cycle threshold (Step 5b).

### Step 5b: Stall Detection

**State** (maintained by the team lead across all messages):
- `cycle_count` — integer, starts at 0, incremented after every message processed
- Per-agent `last_heard_cycle` — set to 0 at spawn, updated when a message arrives from that agent
- Per-agent `nudge_count` — set to 0 at spawn
- `STALL_THRESHOLD` = 10 cycles

**Detection:** After processing each agent message:
1. Increment `cycle_count`
2. Update `last_heard_cycle` for the sender to `cycle_count`
3. For every agent with an in-progress task, check if `cycle_count - last_heard_cycle >= STALL_THRESHOLD`

**Nudge 1** (nudge_count == 0): Send via SendMessage:
> "Status check: you were assigned '{task_name}'. Please reply with a brief progress update or describe any blocker."

Increment `nudge_count` to 1. Reset `last_heard_cycle` to `cycle_count`.

**Nudge 2** (nudge_count == 1): Send via SendMessage:
> "Second request for status on '{task_name}'. If you do not respond, this task will be escalated to the user."

Increment `nudge_count` to 2. Reset `last_heard_cycle` to `cycle_count`.

**Escalation** (nudge_count >= 2): AskUserQuestion with prompt:
> "Agent '{agent_name}' has not responded since '{task_name}' was assigned. Two status requests went unanswered. Options: (a) Nudge again (b) Kill and reassign (c) Skip and continue"

- **(a) Nudge again** — reset `nudge_count` to 1, send another nudge message
- **(b) Kill and reassign** — shutdown agent via TaskStop, reassign task to another available agent. **Disable option (b) if no other agent is available** — show only (a) and (c) in that case.
- **(c) Skip and continue** — mark task as `- [~] Skipped` in `task-list.md`, unblock any tasks that were waiting on this one

**On agent response after nudge:** Reset `nudge_count` to 0, update `last_heard_cycle`, process the message normally.

### Step 6: Completion

When all Review+Verify tasks AND the Final task are complete:

1. **Run retrospective.** Broadcast to all agents:
   > "Retrospective time. Before we wrap up, share your honest feedback: (1) What went well? (2) What didn't go well? (3) What could we do better next time to improve throughput and quality? Be specific — name concrete moments, bottlenecks, or patterns."

   Wait for all agents to respond. Compile their responses into `{feature_dir}/{team_dir}/retrospective.md` with each agent's name and their feedback verbatim. Include a "Themes" section at the end summarizing common observations across agents.

2. **Read report files** from `{feature_dir}/{team_dir}/reports/` and `{feature_dir}/{team_dir}/final-report.md`

3. **Compile the implementation report**. Write it in the feature directory:
   - If plan is inside a feature directory (e.g., `webhook-retry/plan.md`), write `{feature_dir}/report.md`
   - Flat file fallback: if plan was `feature-plan.md`, write `feature-report.md` (strip `-plan` suffix, append `-report`)

4. **Show summary** to the user in console output

5. **Clean up:**
   - Send shutdown requests to all teammates
   - Wait for acknowledgments

### Report Format

```markdown
# Implementation Report: [Feature Name]

**Date:** [current date]
**Plan:** [plan file path]
**Mode:** default / full-team
**Team:** [agent names]

---

## Summary

- **Steps:** [count]
- **Implemented:** [count]
- **Review+Verified:** [count] ([fix cycles] fix cycles)
- **Final test suite:** PASS / FAIL
- **Total tests:** [count], **Failures:** [count]

---

## Per-Step Results

| Step | Implementer | Reviewer | Result | Fix Cycles |
|------|-------------|----------|--------|------------|
| [Step Name] | dev-1 | dev-2 | APPROVED | 0 |
| [Step Name] | dev-2 | dev-1 | APPROVED | 1 |

---

## Review Reports

| Step | Report |
|------|--------|
| [Step Name] | `{feature_dir}/{team_dir}/reports/review-[step-name].md` |
| ... | (list ALL — glob `{feature_dir}/{team_dir}/reports/` to ensure completeness) |

---

## Review Findings

[Summary of issues found and how they were resolved]

---

## Test Results

[Final test suite output — pass/fail, coverage summary]

---

## Files Changed

[List of all files created or modified]

---

## Plan-Reality Mismatches

[Discrepancies discovered and how they were resolved]

---

## Stall Events

| Agent | Task | Nudges | Resolution |
|-------|------|--------|------------|
| {agent} | {task} | {count} | {responded / reassigned / skipped} |

Include this section only if at least one stall occurred. If no stalls occurred, omit this section entirely from the report.

---

## Retrospective

**Themes:** [common observations across agents]

| Agent | Went Well | Didn't Go Well | Suggestions |
|-------|-----------|----------------|-------------|
| [agent] | [feedback] | [feedback] | [feedback] |

Full retrospective: `{feature_dir}/{team_dir}/retrospective.md`
```

## Example Usage

```
/implement docs/IN_PROGRESS/webhook-retry/plan.md
/implement --full-team docs/IN_PROGRESS/multi-tenant-sso/plan.md
/implement webhook-retry-plan.md
/implement --full-team
/implement
```

## Notes

- Completes the workflow pipeline: `/feature-design` → `/task-plan` → `/implement`
- **v7 changes**: Aligned with the current Claude Code tool API — `Task` tool renamed to `Agent`, `TeamCreate`/`TeamDelete` removed (teams are implicit; spawning a named agent joins the session team), spawn-time `mode:` parameter dropped (ignored — subagents inherit the session mode).
- **v6 changes**: Full-team mode upgraded to 4 agents (2 devs + 2 reviewer-testers) — eliminates dev idle time from single reviewer bottleneck. Added cross-team retrospective after Final task — agents share what went well, what didn't, and improvement suggestions.
- **v5 changes**: Replaced `bypassPermissions` with `acceptEdits` mode. (Superseded in v7: the spawn-time `mode:` parameter is ignored by current Claude Code — subagents inherit the session mode.)
- **v4 changes**: Event-driven team lead coordination (react to messages, don't poll). Agent wake-up on task unblock (team lead notifies agents when their tasks unblock). Trivial step batching (combine <20-line single-file steps into one task). Function-level file conflict detection (parallel steps that touch different functions in the same file). Pre-computed test scope per task (scoped `go test` instead of `./...`). Trust-task-descriptions directive (agents read only mentioned files, skip broad exploration).
- **v3 changes**: Merged review+verify into one gate (2-gate pipeline). Default mode uses 2 devs instead of 3 agents (~40-50% token savings). Per-step dependency flow replaces phase gates. Threshold reviewer subagent spawning (200 line threshold). Idle protocol eliminates chatter. Reduced prompts cut spawn cost.
- The team runs fully autonomously unless a developer discovers a plan-reality mismatch
- Per-step file conflict detection provides finer-grained parallelism than phase gates
- Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` enabled (for the `TaskCreate`/`TaskList`/`TaskGet`/`TaskUpdate` task tools)
- Teams are implicit: a session has exactly one team, and spawning a named agent joins it. There is no team to create or delete.
