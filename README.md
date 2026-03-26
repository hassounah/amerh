# amer-plugins

Personal Claude Code plugin marketplace by Amer Hassounah.

## Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| **[corner-office](#corner-office)** | 1.32.2 | Persistent dev manager (Rix) with 3-pipeline system, continuous learning, code review agents, architecture review panel, autonomous implementation teams, SQL database tools, composable workflow formulas, and channel server with permission relay |

## Installation

```bash
# Add the marketplace
/plugin marketplace add hassounah/amerh

# Install a plugin
/plugin install corner-office@amerh
```

---

## corner-office

Personal developer toolkit with a persistent dev manager that runs your engineering pipeline end to end.

### Rix — Persistent Dev Manager (`/rix`)

Rix is the centerpiece. It selects the right pipeline, drives it through quality gates, and remembers context across sessions via persistent memory (`.rix/`).

**Three Pipelines** — auto-selected based on scope:

| Pipeline | When | Flow |
|----------|------|------|
| **Direct** | Trivial: typo fix, config tweak | Rix does it personally — no delegation |
| **Light** | Small: rename, flag, simple bug fix | Design → Implement → Review |
| **Full (3-Gate)** | Complex: multi-component, new patterns | Design Review → Plan Review → Impl Review |

**Persistent Memory** — `.rix/memory.md` stores project context, decisions, backlog, and learned conventions. `.rix/history.md` tracks shipped features. Rix reads memory on startup, reconciles state, and picks up where it left off.

**Document Management** — all pipeline docs (TRDs, plans, reports, reviews) flow through `TODO/` → `IN_PROGRESS/` → `DONE/` under a configurable docs root.

### Custom Team Assembly (`/assemble-team`)

Assemble and spawn a team of any agent personas from the 12-agent roster using pre-configured coordination patterns. Patterns define HOW agents interact — which agents and what they work on are parameters you provide.

```
/assemble-team <pattern> --agents <agent1,agent2,...> --scope <target>
```

| Pattern | Coordination |
|---------|-------------|
| **parallel** | All agents work the same scope independently — zero cross-talk |
| **pipeline** | Sequential chain — each agent's output feeds the next (lazy-spawn, one alive at a time) |
| **panel** | Independent work → cross-review → consensus |
| **collaborative** | Shared task list with dependencies — same event-driven model as `/implement` |

All patterns are event-driven, use TeamCreate + Task tool for spawning teammates, enforce idle protocol, and cap at 4 agents. Complements `/implement` and `/team-review` without replacing them.

### Pipeline Commands

| Command | Description |
|---------|-------------|
| `/rix` | Persistent Dev Manager — orchestrates the full pipeline with memory |
| `/feature-prd` | Research-backed Product Requirements Document with sourced market claims |
| `/feature-design` | Cross-repo system analysis → Technical Requirement Document (TRD) |
| `/task-plan` | Phased implementation plan from a TRD |
| `/implement` | Autonomous implementation team (2 devs or `--full-team`: 2 devs + 2 reviewer-testers) |
| `/team-review` | 3-architect review panel (security, backend, UX/DX) |
| `/assemble-team` | Custom team assembly with coordination patterns and composable YAML formulas |
| `/seance` | Recover context from handoff documents after compaction or session restart |

### Learning Commands

| Command | Description |
|---------|-------------|
| `/learn` | Extract reusable patterns from current session |
| `/evolve` | Cluster related instincts into skills/commands/agents |
| `/instinct-status` | Show all learned instincts with confidence levels |
| `/instinct-export` / `/instinct-import` | Share instincts across projects |

### Agents (12)

**Implementation Team** (via `/implement`):
- **developer** — Full-stack dev with language-specific specialist spawning
- **reviewer-tester** — Dedicated reviewer+tester for `--full-team` mode

**Review Panel** (via `/team-review`):
- **security-architect** — Threat modeling, auth, data protection, compliance
- **backend-architect** — Scalability, data modeling, API design, reliability
- **ux-dx-architect** — API ergonomics, error messages, docs, onboarding

**Design & Planning:**
- **system-architect** — Cross-repo exploration and TRD generation
- **product-manager** — Market research and PRD generation
- **task-planner** — Implementation planning from TRDs

**Code Quality:**
- **go-reviewer**, **python-reviewer**, **database-reviewer**, **security-reviewer**

### MCP Servers (2)

- **sql-database** — SQL query and execution tools for PostgreSQL and SQLite
  - `sql_query` — Read-only queries (auto-approve safe)
  - `sql_execute` — Write operations (require user approval)
  - Named connections from `~/.claude/sql-connections.json` with `${ENV_VAR}` interpolation

- **corner-office-channel** — Two-way channel server bridging Claude Code sessions and external applications
  - Chat relay: client messages → Claude, Claude replies → client
  - Permission relay: tool-approval dialogs forwarded to connected clients for remote approve/deny (v2.1.81+)
  - Token-based WebSocket auth, localhost-only, pending request tracking

### Skills (5)

- **continuous-learning-v2** — Instinct-based learning with hooks, confidence scoring, and evolution
- **strategic-compact** — Context compaction at logical workflow boundaries
- **security-checklist** — Security checklist and patterns
- **serena-integration** — MCP tool discovery and semantic code navigation
- **learned** — Auto-extracted patterns from past sessions

### Formulas (4)

Composable YAML presets for `/assemble-team` — override agents with `+agent`, `-agent`, or `--agents-replace`:
- **code-review** — Parallel code quality sweep (go-reviewer, python-reviewer, security-reviewer)
- **security-sweep** — Deep security panel (security-architect, security-reviewer, backend-architect)
- **design-explore** — Pipeline from PRD to TRD (product-manager, system-architect)
- **full-stack-review** — Full architecture panel (security-architect, backend-architect, ux-dx-architect)

### Hooks (20 events)

`emit_activity` hooks on all 20 event types write session events to `~/.corner-office/events/` as JSONL. **Disabled by default** — events only flow when `~/.corner-office/events/enabled` exists. The Corner Office app manages this flag via its hook install/uninstall mechanism. Specialized hooks on 7 core events handle strategic compaction, session start/end, handoff capture, registration card refresh, and code quality checks.

---

## Structure

```
amerh/
├── .claude-plugin/
│   └── marketplace.json
└── plugins/
    └── corner-office/
        ├── .claude-plugin/
        │   └── plugin.json
        ├── .mcp.json         # MCP server registrations
        ├── agents/           # 12 agents
        ├── commands/         # 13 commands
        ├── formulas/         # 4 YAML workflow formulas
        ├── hooks/            # Learning observer + handoff capture
        ├── servers/
        │   ├── channel/      # Channel server (chat + permission relay)
        │   └── mcp/          # SQL database MCP server
        └── skills/           # 5 skills
```

## Attribution

The continuous learning system (instinct-based observation, confidence scoring, evolution pipeline) and several code review agents in `corner-office` originated from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) by Affaan M. This plugin builds on that foundation with autonomous implementation teams, architecture review panels, and workflow optimizations developed through real-world usage.

The structured handoff/recovery system (`/seance`, PreCompact handoff capture), composable workflow formulas, and stall detection concepts were inspired by [Gastown](https://github.com/steveyegge/gastown) by Steve Yegge.
