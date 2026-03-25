# corner-office

Personal developer toolkit for Claude Code. Provides a full engineering pipeline — from product requirements through design, planning, implementation, and review — plus continuous learning, security review, and workflow optimization.

## Quick Start

```bash
/plugin marketplace add ~/.claude/plugins/repos/amer-plugins
/plugin install corner-office@amer-plugins
```

## Rix — Persistent Dev Manager

Rix (`/rix`) is the centerpiece of corner-office. It's a persistent dev manager that owns the engineering pipeline end to end — selecting the right workflow for each task, driving it through quality gates, and remembering context across sessions.

### Three Pipelines

Rix automatically selects one of three pipelines based on task scope:

**Direct** — Rix does it personally. No delegation, no docs, no gates.
- For: typo fixes, config tweaks, single-field additions, small doc edits
- Flow: understand → do the work → done

**Light** — One design pass, one implementation, one review.
- For: renames, flag additions, simple bug fixes, single-file refactors
- Flow: `/feature-design` → `/implement` → `/team-review` → done

**Full (3-Gate)** — Rigorous pipeline with design, plan, and implementation each reviewed by a 3-architect panel. No gate advances with unresolved critical or high findings.
- For: multi-component features, new patterns, cross-cutting changes, high-risk work
- Flow:
  ```
  Gate 1: /feature-design → /team-review → fix findings
  Gate 2: /task-plan      → /team-review → fix findings
  Gate 3: /implement      → /team-review → fix findings → ship
  ```

When scope is ambiguous, Rix asks — never guesses, never switches pipelines mid-feature.

### Persistent Memory

Rix maintains project memory in `.rix/` at the git root, surviving across sessions:

```
.rix/
├── memory.md          # Project context, decisions log, backlog, learned conventions
├── active-pipeline.md # Current pipeline state (created on start, deleted on ship)
└── history.md         # Shipped features log
```

On every startup, Rix reads its memory, loads the most recent handoff document (replacing manual `/seance`), scans for orphaned pipeline docs, reconciles state, and picks up where it left off. Decisions, conventions, and backlog items persist automatically.

### Document Management

All pipeline documents are organized under a configurable `docs_root`:

```
{docs_root}/
├── TODO/           # Queued feature requests
├── IN_PROGRESS/    # Active pipeline docs (TRDs, plans, reports, reviews)
└── DONE/           # Completed feature bundles (moved here after shipping)
```

## Custom Team Assembly

`/assemble-team` lets you compose any team from the 12-agent roster using pre-configured coordination patterns. Patterns define the interaction model — agents and scope are parameters.

```bash
/assemble-team <pattern> --agents <agent1,agent2,...> --scope <target>
```

**Four coordination patterns:**

| Pattern | How It Works | Example |
|---------|-------------|---------|
| **parallel** | All agents work independently, zero cross-talk, combined summary | `/assemble-team parallel --agents go-reviewer,python-reviewer --scope src/` |
| **pipeline** | Sequential chain, each output feeds the next, lazy-spawn one at a time | `/assemble-team pipeline --agents product-manager,system-architect,task-planner --scope "alerting"` |
| **panel** | Independent review → cross-review → consensus | `/assemble-team panel --agents security-architect,backend-architect --scope trd.md` |
| **collaborative** | Shared task list with dependencies, event-driven coordination | `/assemble-team collaborative --agents developer,developer,go-reviewer --scope plan.md` |

**Key properties:**
- All patterns are fully event-driven — same coordination model as `/implement`
- Agents are spawned as teammates via TeamCreate + Task tool with persistent identity and message passing
- Max 4 agents, idle protocol enforced, reports written to files (1-line status messages only)
- Pipeline pattern lazy-spawns one agent at a time for maximum token efficiency
- Complements `/implement` and `/team-review` — does NOT replace them

## The Pipeline Commands

The individual commands that Rix orchestrates — also usable standalone:

## Components

### Commands (13)

**Pipeline Orchestration:**
- `/rix` - Persistent Dev Manager with memory — orchestrates the full pipeline through 3 quality gates
- `/feature-prd` - Produce a research-backed Product Requirements Document with competitive analysis and sourced market claims
- `/feature-design` - Design a feature with cross-repo system analysis and produce a Technical Requirement Document (TRD)
- `/task-plan` - Create a detailed implementation plan from a TRD
- `/implement` - Launch an autonomous implementation team (default: 2 devs cross-review, `--full-team`: 2 devs + 2 reviewer-testers)
- `/team-review` - Launch a 3-architect review panel (security, backend, UX/DX)
- `/assemble-team` - Assemble a custom team of agent personas with pre-configured coordination patterns and composable YAML formulas (`--formula`, `--list-formulas`, `+/-` agent overrides)
- `/seance` - Recover context from handoff documents after compaction or session restart (`--list` to browse history)

**Learning System:**
- `/learn` - Extract reusable patterns from current session
- `/evolve` - Cluster related instincts into skills, commands, or agents
- `/instinct-status` - Show all learned instincts with confidence levels
- `/instinct-export` - Export instincts for sharing
- `/instinct-import` - Import instincts from external sources

### Agents (12)

**Implementation Team** (spawned by `/implement`):
- **developer** - Full-stack developer: implements code, performs peer reviews with language-specific specialist spawning (Sonnet)
- **reviewer-tester** - Dedicated reviewer+tester for `--full-team` mode: reviews all changes, verifies quality >85% coverage (Sonnet)

**Review Panel** (spawned by `/team-review`):
- **security-architect** - Security architecture: threat modeling, auth, data protection, compliance (Opus)
- **backend-architect** - Backend/systems architecture: scalability, data modeling, API design, reliability (Opus)
- **ux-dx-architect** - UX/DX architecture: API ergonomics, error messages, docs, onboarding (Opus)

**Design & Planning:**
- **system-architect** - Cross-repo system architect that explores all repositories and produces TRDs (Opus)
- **product-manager** - Market research and competitive analysis to produce structured PRDs with sourced claims (Opus)
- **task-planner** - Expert planning specialist for complex features and refactoring (Opus)

**Code Quality:**
- **database-reviewer** - PostgreSQL specialist: query optimization, schema design, security (Opus)
- **go-reviewer** - Go code reviewer: idiomatic Go, concurrency, error handling (Opus)
- **python-reviewer** - Python code reviewer: PEP 8, type hints, security (Opus)
- **security-reviewer** - OWASP Top 10 vulnerability detection and remediation (Opus)

### MCP Servers (2)

- **sql-database** — SQL query and execution tools for PostgreSQL and SQLite. Two tools with separate permission levels:
  - `sql_query` — Read-only (SELECT, EXPLAIN, PRAGMA, SHOW, DESCRIBE). Safe to auto-approve.
  - `sql_execute` — Write operations (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE). Should require user approval.
  - Named connections from `~/.claude/sql-connections.json` with `${ENV_VAR}` interpolation
  - Per-query connect/disconnect, keyword-based SQL validation, 500-row result limit

- **corner-office-channel** — Two-way channel server bridging Claude Code sessions and external applications. MCP stdio transport to Claude Code, WebSocket transport to connected clients.
  - **Chat relay** — Client messages forwarded to Claude as `<channel>` events; Claude replies via `reply` and `edit_message` tools
  - **Permission relay** — Claude Code tool-approval dialogs (Bash, Write, Edit) forwarded to connected clients via WebSocket. Users can approve/deny remotely — first response (terminal or client) wins. Requires Claude Code v2.1.81+.
  - Token-based WebSocket auth, localhost-only binding, pending request tracking for replay prevention
  - Activity events (`emit_activity`) let clients detect when permissions are resolved from the terminal side

### Formulas (4)

Composable YAML presets for `/assemble-team`. Use `--formula <name>` to load, override agents with `+agent`, `-agent`, or `--agents-replace`:

- **code-review** — Parallel code quality sweep (go-reviewer, python-reviewer, security-reviewer)
- **security-sweep** — Deep security panel (security-architect, security-reviewer, backend-architect)
- **design-explore** — Pipeline from PRD to TRD (product-manager, system-architect)
- **full-stack-review** — Full architecture panel (security-architect, backend-architect, ux-dx-architect)

### Skills (5)
- **continuous-learning-v2** - Instinct-based learning system with hooks, confidence scoring, and evolution
- **strategic-compact** - Suggests manual context compaction at logical workflow boundaries
- **security-checklist** - Comprehensive security checklist and patterns for code review
- **serena-integration** - MCP tool discovery and semantic code navigation via Serena
- **learned/** - Auto-extracted patterns from past sessions

### Hooks (20 events)

**Activity tracking** — `emit_activity` hooks on all 20 event types forward every Claude session event to connected clients via the channel server. This gives any consuming application full visibility into session activity (tool use, agent spawning, task completion, permission requests, etc.).

**Specialized hooks** (on top of activity tracking):
- **PreToolUse** - Strategic compact suggestions on Edit/Write
- **PostToolUse** - Refresh session registration card on pipeline file writes
- **UserPromptSubmit** - Generates a handoff document before `/clear` wipes context
- **SessionStart** - Loads previous context, detects package manager, auto-starts Rix if project uses it
- **SessionEnd** - Persists session state and evaluates session for extractable patterns
- **PreCompact** - Captures structured handoff document before context compaction
- **Stop** - Checks for leftover `console.log` in modified files

## Data Storage

Runtime data lives in `~/.claude/homunculus/`:
```
~/.claude/homunculus/
├── observations.jsonl        # Session observation log
├── observations.archive/     # Archived observations
├── handoffs/                    # Structured handoff docs from PreCompact, SessionEnd, and /clear
├── instincts/
│   ├── personal/             # Auto-learned instincts
│   └── inherited/            # Imported from others
└── evolved/
    ├── agents/
    ├── skills/
    └── commands/
```

The `/rix` dev manager stores its persistent memory in `.rix/` at the project root:
```
.rix/
├── memory.md          # Project context, decisions, backlog, conventions
├── pipelines/         # Per-feature pipeline cards + lock files (multi-session)
└── history.md         # Shipped features log
```

## Disabling Observation Hooks

To temporarily disable the learning observer:
```bash
touch ~/.claude/homunculus/disabled
```

Remove it to re-enable:
```bash
rm ~/.claude/homunculus/disabled
```

## Attribution

The continuous learning system (instinct-based observation, confidence scoring, evolution pipeline) and several code review agents originated from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) by Affaan M. This plugin builds on that foundation with autonomous implementation teams, architecture review panels, and workflow optimizations developed through real-world usage.

The structured handoff/recovery system (`/seance`, PreCompact handoff capture), composable workflow formulas, and stall detection concepts were inspired by [Gastown](https://github.com/steveyegge/gastown) by Steve Yegge.
