---
name: assemble-team
description: Assemble and spawn a custom team of agent personas using pre-configured coordination patterns (parallel, pipeline, panel, collaborative). Event-driven, token-efficient team creation via TeamCreate + Task tool.
command: true
allowed-tools: ["AskUserQuestion", "Task", "Read", "Write", "Glob", "Grep", "Bash", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
argument-hint: "<pattern> --agents <agent1,agent2,...> --scope <target> | --formula <name> --scope <target> [--agents <+/-override> | --agents-replace <list>] | --list-formulas"
---

# /assemble-team — Custom Team Assembly

Assemble and spawn a team of agent personas using pre-configured coordination patterns. Patterns define HOW agents interact. Which agents to spawn and what they work on are parameters.

## Usage

```
/assemble-team <pattern> --agents <agent1,agent2,...> --scope <target>
```

## Agent Roster

Available agent personas. Each is spawned as a teammate via TeamCreate + Task tool using its `subagent_type`. The agent definition IS the persona — system prompt, tools, and model all come from the agent file.

| Agent | subagent_type | Expertise |
|-------|---------------|-----------|
| backend-architect | corner-office:backend-architect | System design, scalability, APIs, reliability |
| database-reviewer | corner-office:database-reviewer | PostgreSQL, query optimization, schema design |
| developer | corner-office:developer | Full-stack implementation, code reviews |
| go-reviewer | corner-office:go-reviewer | Idiomatic Go, concurrency, error handling |
| product-manager | corner-office:product-manager | Market research, PRDs, competitive analysis |
| python-reviewer | corner-office:python-reviewer | PEP 8, type hints, Pythonic idioms |
| reviewer-tester | corner-office:reviewer-tester | Code review, testing, quality verification |
| security-architect | corner-office:security-architect | Threat models, auth, data protection, compliance |
| security-reviewer | corner-office:security-reviewer | OWASP Top 10, vulnerability detection |
| system-architect | corner-office:system-architect | Cross-repo design, TRD generation |
| task-planner | corner-office:task-planner | Implementation planning, phased breakdown |
| ux-dx-architect | corner-office:ux-dx-architect | API ergonomics, DX, accessibility |

## Patterns

Patterns define coordination models — how agents interact, how tasks flow, how output is produced. Every pattern is fully event-driven.

### parallel

All agents work the same scope independently. Zero cross-talk. Each produces their own report. Lead compiles a combined summary.

**Coordination:**
1. Create team, create one task per agent (all unblocked)
2. Spawn all agents in parallel (single message, multiple Task calls)
3. Each agent works their scope, writes report to `{reports_root}/reports/{agent-name}.md`
4. Each agent marks task complete, sends 1-line status
5. Lead compiles combined summary after all complete

**Task structure:**
- One task per agent: "{agent-name}: Analyze {scope}"
- All tasks unblocked — zero dependencies between agents
- Owner: assigned to the specific agent

**Best for:** Multi-perspective analysis of the same target. Each agent brings their lens without being influenced by others.

---

### pipeline

Sequential chain. Each agent's output becomes the next agent's input. Only one agent alive at a time — maximum token efficiency.

**Coordination:**
1. Create team
2. Spawn agent 1, assign their task
3. Wait for agent 1 to complete and produce output
4. Send shutdown to agent 1, wait for acknowledgment
5. Spawn agent 2 into the same team with agent 1's output as context
6. Repeat until final agent completes
7. Final agent's output is the team deliverable

**Task structure:**
- One task at a time, created when the agent is spawned
- Agent N's task description includes: scope + path to agent N-1's output report
- Each agent writes output to `{reports_root}/reports/{N}-{agent-name}.md`
- Numbered prefix ensures ordering

**Lazy-spawn:** Only one agent exists in the team at any moment. Spawn → work → shutdown → spawn next. Most token-efficient pattern.

**Best for:** Sequential workflows where each stage builds on the previous. Output quality compounds through the chain.

---

### panel

Independent work followed by cross-review and consensus building. Three phases: solo work, cross-review, lead-compiled consensus.

**Coordination:**

Phase 1 — Independent Review:
1. Create team, create one review task per agent (all unblocked)
2. Spawn all agents in parallel
3. Each agent reviews the scope independently
4. Each agent writes findings to `{reports_root}/reports/{agent-name}-findings.md`
5. Each agent marks review task complete, sends 1-line status

Phase 2 — Cross-Review:
6. After ALL Phase 1 tasks complete, create one cross-review task per agent
7. Each cross-review task description lists paths to ALL other agents' findings reports
8. Wake each agent: "Cross-review phase — read other agents' findings, note agreements and disagreements, write cross-review to `{reports_root}/reports/{agent-name}-cross-review.md`"
9. Each agent marks cross-review task complete

Phase 3 — Consensus (lead compiles):
10. Lead reads all findings and cross-review reports
11. Lead compiles consensus report: agreed findings, contested points, final recommendations

**Task structure:**
- Phase 1: one review task per agent (unblocked)
- Phase 2: one cross-review task per agent (blocked by ALL Phase 1 tasks)
- Lead creates Phase 2 tasks after all Phase 1 tasks complete
- No Phase 3 task — lead compiles directly

**Best for:** Multi-perspective review where agents should challenge and build on each other's analysis. Richer output than parallel because of the cross-review phase.

---

### collaborative

Shared task list with dependencies. Agents claim tasks from their queue and coordinate event-driven. Same model as /implement — maximum parallelism with dependency-based ordering.

**Coordination:**
1. Create team and task list
2. Parse scope for actionable work items (if file: extract tasks from structure; if description: ask user for task breakdown via AskUserQuestion)
3. Create tasks with dependencies, assign to agents by expertise
4. Spawn all agents in parallel with their task queues
5. Event-driven: lead reacts to messages, wakes blocked agents on task completion
6. Lead compiles final report after all tasks complete

**Task structure:**
- Multiple tasks with explicit dependencies via TaskUpdate (addBlockedBy/addBlocks)
- Tasks assigned to specific agents by name (owner field)
- Agents use TaskGet to read full task descriptions when claiming
- Dependencies define execution order — tasks run in parallel when no conflicts

**Scope parsing:**
- **Plan file / TRD**: extract phases and steps, create tasks per step, infer dependencies from plan structure
- **Directory / file path**: create analysis tasks scoped to relevant files, assign by agent expertise
- **Description**: ask user to provide task breakdown or generate one and confirm via AskUserQuestion

**Best for:** Complex multi-step work where different agents handle different parts with coordination. The most flexible pattern.

---

## Non-Negotiable Rules (ALL Patterns)

1. **Event-driven coordination.** Lead reacts to agent messages. NEVER poll. NEVER sleep. NEVER loop on TaskList. React → process → wake blocked agents → go idle.
2. **TeamCreate + Task tool.** Teams are created via TeamCreate. Agents are spawned as teammates via Task tool with `team_name` and `name` parameters. They are team members with persistent identity and message passing.
3. **Agent personas.** Each agent is spawned using its `subagent_type` from the roster. The agent definition IS its persona — system prompt, tools, model all come from the agent file.
4. **acceptEdits mode.** ALL agents spawned with `mode: "acceptEdits"`.
5. **Idle protocol.** Agents send ONE status message when blocked/empty, then go SILENT. No periodic updates. Pre-read source while waiting.
6. **Reports to files.** ALL output written to `{reports_root}/reports/`. Agents send 1-line status messages ONLY. Full analysis goes in report files, never in messages.
7. **Trust task descriptions.** Agents read only files mentioned in tasks. No broad codebase exploration unless code doesn't match.
8. **Max 4 agents.** Reject requests exceeding 4 agents.
9. **No git commits.** Agents do not commit. User commits when ready.
10. **Shutdown and cleanup.** After completion: send shutdown requests to all teammates, wait for acknowledgments, TeamDelete.

## Token Efficiency Directives

These apply to ALL patterns and are baked into every agent prompt:

- **Scoped reads only.** Agents read files relevant to their task. No exploratory file browsing.
- **1-line messages.** Status updates are one sentence. Full analysis goes to report files.
- **Pre-read while blocked.** If waiting on a dependency, read source code for upcoming tasks.
- **Pipeline lazy-spawn.** Only one agent alive at a time. Shutdown each before spawning next.
- **No redundant work.** In pipeline, if findings overlap with previous agent's output, focus on NEW insights only.
- **Compact prompts.** Spawn prompts include: 2-3 sentence scope summary, task queue (subjects only), rules. Full details live in TaskGet descriptions.

## Process

### Step 1: Parse Arguments

Extract pattern, agents, and scope from arguments:

- **pattern** (required): `parallel` | `pipeline` | `panel` | `collaborative`
- **--agents** (required): comma-separated list of agent names from the roster
- **--scope** (required): file path, directory, description, or document to work on

If any required argument is missing, ask using AskUserQuestion:
- Missing pattern: show the 4 options with 1-line descriptions
- Missing agents: show the roster, ask which agents to include
- Missing scope: ask what the team should work on

After extracting standard arguments, check for formula flags:

- **`--list-formulas`** (or `--formula-list`): Read all YAML files in `${CLAUDE_PLUGIN_ROOT}/formulas/`, display a table (name, pattern, agents, description), then stop. Do not proceed to team creation.

- **`--formula <name>`**:
  a. Validate formula name: must match `^[a-zA-Z0-9_-]+$`. Reject names containing `/`, `..`, `\`, or spaces with an error.
  b. Formula names MUST NOT match reserved pattern names (`parallel`, `pipeline`, `panel`, `collaborative`). Error if they do.
  c. Read `${CLAUDE_PLUGIN_ROOT}/formulas/{name}.yaml`.
  d. If not found, list available formulas from the `formulas/` directory and ask the user to pick one via AskUserQuestion.
  e. Parse YAML, extract `pattern`, `agents`, `scope_template`, `report_name`.
  f. Set pattern and agent list from formula values.
  g. Apply scope template: replace `{target}` in `scope_template` with the `--scope` value provided by the user.
  h. Sanitize `{target}` for use in `report_name`: replace `/` and `\` with `-`, strip trailing `-` separators.

- **`--formula <name>` + `--agents <tokens>`**: Each agent token MUST carry a `+` or `-` prefix.
  - `+agent-name`: append to the formula's agent list.
  - `-agent-name`: remove from the formula's agent list.
  - Mixed example: `+database-reviewer,-go-reviewer` — process each token by prefix.
  - Bare agent names without a prefix: error with "When using --formula, prefix agents with + to add or - to remove. To replace the entire list, use --agents-replace."

- **`--formula <name>` + `--agents-replace <list>`**: Ignore the formula's agent list entirely. Use this comma-separated list as the complete agent list.

- **Formula shorthand**: If the first argument does not match a reserved pattern name (`parallel`, `pipeline`, `panel`, `collaborative`) and no explicit `--formula` flag is present, check if the first argument matches a known formula name (glob `${CLAUDE_PLUGIN_ROOT}/formulas/{arg}.yaml`). If matched, treat as `--formula <name>`.

- **Mutual exclusion**: `--formula` + an explicit pattern argument = error. Tell the user to use one or the other.

After all overrides are applied, validate the final agent list against the roster before proceeding to Step 2.

### Step 2: Validate

1. **Pattern**: must be one of the four. If not, show options and ask.
2. **Agents**: each name must match the roster. If unrecognized, show roster and ask user to correct.
3. **Agent count**: max 4. If exceeded, tell user the limit and ask which to keep.
4. **Duplicate agents**: allowed (e.g., two developers). Append numeric suffix for team identity: developer-1, developer-2.
5. **Scope**: if a file path, verify it exists via Glob. If a directory, verify it exists. If a description, accept as-is.

### Step 3: Derive Slug

Derive a slug from the pattern and scope for the working directory:
- File scope: `parallel-src-api` (pattern + path segments)
- Description scope: `pipeline-user-auth` (pattern + first 2-3 significant words)
- Keep it short — lowercase, hyphens, no special characters

Used for: team name `{slug}-team` and report paths.

**Determine the working directory for reports:**
- If a feature directory context is provided (e.g., called within a pipeline with `{feature_dir}`), use `{feature_dir}/.assemble-team/` as the reports root.
- Otherwise, use `.assemble-team/{slug}/` at the repo root.

### Step 4: Setup

1. Create reports directory: `mkdir -p {reports_root}/reports` (where `{reports_root}` is either `{feature_dir}/.assemble-team/` or `.assemble-team/{slug}/`)
2. Create team: `TeamCreate with team_name: "{slug}-team"`
3. Prepare scope summary (2-3 sentences describing what the team is working on)

### Step 5: Create Tasks

Create tasks BEFORE spawning agents. Task structure depends on the pattern (see Patterns section).

For all patterns:
- Task subjects are concise: "{agent-name}: {action} {scope}"
- Task descriptions include: full scope details, file paths, expected output path, report filename
- Dependencies set via TaskUpdate where applicable
- Owner set to agent name

### Step 6: Spawn Agents

Spawn agents as teammates into the team via Task tool.

**Agent spawn prompt template:**
```
You are {agent-name} on a {agent-count}-agent team assembled for {scope summary}. Pattern: {pattern}. Teammates: {other-agent-names}. Team lead coordinates.

Working directory: {path}

## Your Task Queue
{list task subjects assigned to this agent}

## Rules (NON-NEGOTIABLE)
1. Work from YOUR queue only. Do not claim other agents' tasks.
2. Write ALL output to report files. Send ONLY 1-line status messages.
3. Read only files relevant to your task. No broad exploration.
4. Idle protocol: if blocked/empty, send ONE message, then go SILENT. Pre-read source while waiting.
5. No git commits.
6. Trust task descriptions — read only mentioned files unless code doesn't match.
7. When done with a task, mark it complete via TaskUpdate and send: "{task subject}: DONE"

Use TaskGet to read full task descriptions. Start by checking TaskList.
```

**Pattern-specific adjustments:**
- **parallel**: spawn ALL agents in a single message (multiple Task calls)
- **pipeline**: spawn ONLY agent 1. Subsequent agents spawned after previous completes. Include previous agent's output path in the prompt.
- **panel**: spawn ALL agents in Phase 1. Phase 2 prompts sent via SendMessage after all Phase 1 tasks complete.
- **collaborative**: spawn ALL agents. Prompts note task dependencies.

**All agents spawned with:**
- `mode: "acceptEdits"`
- `team_name: "{slug}-team"`
- `name: "{agent-name}"` (or `"{agent-name}-1"` for duplicates)
- `subagent_type: "corner-office:{agent-name}"`

### Step 7: Coordinate (Event-Driven)

Same protocol for all patterns:

1. **React to messages only.** After each agent message:
   - Task completion → check TaskList for newly unblocked tasks, wake relevant agents via SendMessage
   - "Queue blocked/empty" → check for stuck dependencies
   - Questions/mismatches → respond with guidance
2. **Wake blocked agents** immediately when their dependencies complete: "Task '{name}' is now unblocked — proceed."
3. **Go idle** after processing. Wait for next message. Do not poll.
4. **Escalate** stuck tasks (3+ fix cycles) to user via AskUserQuestion.

**Pipeline-specific coordination:**
- After agent N completes: read their report, send shutdown request, wait for acknowledgment
- Create task for agent N+1 (include path to agent N's report in description)
- Spawn agent N+1 into the team
- Repeat until chain complete

**Panel Phase 2 trigger:**
- After ALL Phase 1 tasks complete, create Phase 2 cross-review tasks (blocked by nothing since Phase 1 is done)
- Wake all agents: "Cross-review phase. Your cross-review task is ready."

### Step 8: Completion

1. Read all reports from `{reports_root}/reports/`
2. Compile team report to `{reports_root}/team-report.md`
3. Show summary to user in console
4. Send shutdown requests to all remaining teammates
5. Wait for acknowledgments
6. TeamDelete

### Team Report Format

```markdown
# Team Report: {slug}

**Date:** {date}
**Pattern:** {pattern}
**Agents:** {agent list}
**Scope:** {scope}

---

## Summary

{high-level summary of team output}

---

## Per-Agent Output

| Agent | Report |
|-------|--------|
| {agent-name} | `{reports_root}/reports/{report-name}.md` |

---

## Key Findings

{consolidated findings across all agents}

---

## Recommendations

{actionable next steps}
```

## Examples

```
# Multi-language code quality sweep
/assemble-team parallel --agents go-reviewer,python-reviewer,database-reviewer --scope src/

# Requirements → design → planning pipeline
/assemble-team pipeline --agents product-manager,system-architect,task-planner --scope "real-time alerting"

# Architecture review with cross-discussion
/assemble-team panel --agents security-architect,backend-architect --scope api-gateway-trd.md

# Implementation with targeted review
/assemble-team collaborative --agents developer,developer,go-reviewer --scope migration-plan.md

# Deep security analysis chain
/assemble-team pipeline --agents security-reviewer,security-architect --scope src/auth/

# Full-stack review panel
/assemble-team panel --agents go-reviewer,python-reviewer,database-reviewer,security-reviewer --scope src/
```

## Formulas

Formulas are named presets that bundle a pattern, agent list, and scope template into a reusable YAML file. They let you run a repeatable workflow with one argument instead of spelling out the full command each time.

### Discovery

```
# Always start here — see what formulas are available
/assemble-team --list-formulas
```

### Available Formulas

| Name | Pattern | Agents | Use Case |
|------|---------|--------|----------|
| code-review | parallel | go-reviewer, python-reviewer, security-reviewer | Multi-language code quality sweep |
| security-sweep | pipeline | security-reviewer, security-architect | Sequential vulnerability → architecture review |
| design-explore | pipeline | product-manager, system-architect, task-planner | Requirements → design → planning chain |
| full-stack-review | panel | backend-architect, security-architect, ux-dx-architect | Cross-perspective review with challenge phase |

### Formula Usage Examples

```
# Run a formula as-is (two equivalent forms)
/assemble-team --formula code-review --scope src/
/assemble-team code-review --scope src/          # shorthand — formula name as first arg

# Add an agent to a formula
/assemble-team --formula code-review --scope src/ --agents +database-reviewer

# Remove an agent from a formula
/assemble-team --formula full-stack-review --scope api.md --agents -security-architect

# Mix additions and removals
/assemble-team --formula code-review --scope src/ --agents +database-reviewer,-go-reviewer

# Replace the agent list entirely
/assemble-team --formula code-review --scope src/ --agents-replace go-reviewer,python-reviewer

# List all available formulas
/assemble-team --list-formulas
```

### Custom Formulas

Create your own formula by adding a YAML file to `${CLAUDE_PLUGIN_ROOT}/formulas/`:

```yaml
name: my-formula
description: What this formula does
pattern: parallel          # parallel | pipeline | panel | collaborative
agents:
  - go-reviewer
  - security-reviewer
scope_template: "{target}"
report_name: "my-formula-{target}"
```

The `{target}` placeholder is replaced by the `--scope` value at runtime. Formula files must use a name that does not conflict with reserved pattern names (`parallel`, `pipeline`, `panel`, `collaborative`).

**Note:** When used in `report_name`, the `--scope` value (`{target}`) has `/` and `\` replaced with `-` and trailing separators stripped to produce a valid filename.

---

## Notes

- This command complements `/implement` and `/team-review` — it does NOT replace them. Those commands have battle-tested, purpose-built coordination. Use `/assemble-team` when you need a team composition that doesn't fit those molds.
- All coordination uses the same TeamCreate + Task + SendMessage machinery as `/implement`.
- Patterns are interaction models, not use cases. The same pattern works with any combination of agents.
- Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` enabled.
