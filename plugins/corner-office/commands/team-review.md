---
name: team-review
description: Launch a 3-architect review panel (security, backend, UX/DX) that collaborates as an agent team to produce a comprehensive review
allowed-tools: ["AskUserQuestion", "Agent", "Read", "Write", "Glob", "Grep", "Bash", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
argument-hint: "[what to review: PR #123, path/to/file, 'the auth module', etc.]"
---

# /team-review - Architecture Review Panel

Launch a team of 3 architect agents that review a target autonomously, then discuss findings cross-team, and produce a consolidated review document.

## The Review Team

| Architect | Focus Areas |
|-----------|-------------|
| **security-architect** | Threat modeling, auth, data protection, input validation, secrets, compliance |
| **backend-architect** | System design, scalability, data modeling, API design, reliability, observability |
| **ux-dx-architect** | API ergonomics, error messages, documentation, developer onboarding, UX consistency |

## Process

### Step 1: Identify the Review Target

**If the user provided arguments**, use them to determine the review target.

**If no arguments**, ask the user what they want reviewed using AskUserQuestion:
- A Pull Request (provide PR number or URL)
- A design document or TRD (provide file path)
- An implementation plan (provide file path)
- A codebase or module (provide directory path)
- Something else (describe it)

Once you know the target, determine what the architects need to read. Prepare a clear description of:
- What is being reviewed (specific files, directories, PR diff, document)
- The context (what project, what it does, relevant background)
- The working directory path

### Step 1b: Derive Slug and Feature Directory

Derive a slug from the review target — this is used for the team name and findings filenames:

- If the target file is inside a feature directory (e.g., `webhook-retry/trd.md`), use the parent directory name as the slug: `webhook-retry`. The feature directory is also used as the base for `.review-panel/` and the output review file.
- File path (flat): strip `-trd`, `-plan`, `-report` suffixes and `.md` extension: `webhook-retry-trd.md` → slug = `webhook-retry`
- PR: use `pr-{number}`: `PR #142` → slug = `pr-142`
- Module/directory: use the directory name: `parapetsecurity-worker/` → slug = `parapetsecurity-worker`
- Fallback: lowercase, hyphens, no special characters

**Determine the review panel directory:**
- If `--team-dir` was provided in the arguments (e.g., `--team-dir .03-review-panel`): use `{feature_dir}/{team_dir}/`
- Else if a feature directory exists (target is inside a slug directory): use `{feature_dir}/.review-panel/`
- Otherwise, use `.review-panel/` at the working directory root

### Step 2: Create the Tasks

Create 4 tasks:

- **Task 1: Security Review** — assigned to security-architect
- **Task 2: Backend Review** — assigned to backend-architect
- **Task 3: UX/DX Review** — assigned to ux-dx-architect
- **Task 4: Cross-Cutting Discussion** — unassigned, blocked by Tasks 1-3

### Step 3: Spawn the Architect Teammates

Spawn all 3 architects **in parallel** (single message with 3 Agent tool calls). Pass each a `name` matching its role (`security-architect`, `backend-architect`, `ux-dx-architect`) — they join the session's implicit team and become addressable by that name via `SendMessage`. Subagents inherit the session's permission mode — do not pass a `mode:` parameter, it is ignored. File writes, MCP tools, and Bash are covered by the session mode plus `permissions.allow` rules in project settings.

Each architect gets a prompt with this structure:

```
You are [role] on a 3-architect review panel. Teammates: [other two architects]. Team lead consolidates the final report.

Review target: [WHAT IS BEING REVIEWED — files, document, PR, module]
Context: [PROJECT CONTEXT — what it does, relevant background]
Working directory: [PATH]

## Your Task Queue

1. [Your Review Task] — review the target from your domain perspective
2. Cross-Cutting Discussion — discuss findings with the other architects (blocked until all individual reviews complete)

## Rules (NON-NEGOTIABLE)

1. **Work from YOUR queue only.** Use TaskGet to read full task descriptions.
2. **Write your review to a file.** Write your full review findings to the review panel directory provided in your prompt: `{review_panel_dir}/[role]-findings.md` (e.g., `security-architect-findings.md`). Send ONLY a brief status message (1 line) when done.
3. **Idle protocol.** After completing your review task, send ONE message: "[Role] review complete." Then go SILENT. Pre-read the review target deeper while waiting for the discussion phase. Do NOT send periodic updates.
4. **Discussion phase.** When Cross-Cutting Discussion unblocks, read the other architects' findings from the review panel directory. Then engage in focused discussion via SendMessage with the other architects:
   - Challenge findings you disagree with
   - Identify issues that span multiple domains
   - Flag trade-offs between your domain and others (e.g., security vs UX)
   - Keep messages concise — finding + position + reasoning
5. **End discussion.** After you've raised all cross-cutting concerns and responded to challenges, send ONE message to team lead: "[Role] discussion complete." Then go SILENT.
6. **Trust the target.** Read only the files/docs specified. Do NOT explore the broader codebase unless something doesn't match expectations.

## Review Output Format

Write your findings to `{review_panel_dir}/[role]-findings.md` using this structure:

```markdown
# [Domain] Review: [Target Name]

## Critical (Must Fix)
- [Finding with file:line references where applicable]

## High (Should Fix)
- [Finding]

## Medium (Consider)
- [Finding]

## Low (Nice to Have)
- [Finding]

## Positive Observations
- [What's done well]
```

Start by checking TaskList and claiming your review task.
```

### Step 4: Coordinate (Event-Driven)

**Do NOT poll.** React to agent messages only.

#### After each agent message:

1. **Process the message:**
   - "review complete" → note it, check if all 3 reviews are done
   - "discussion complete" → note it, check if all 3 discussions are done
   - Other → respond only if it's a question or blocker

2. **Trigger discussion phase:**
   When ALL 3 individual review tasks are marked complete, immediately:
   - Mark the Cross-Cutting Discussion task as `in_progress`
   - Send a message to ALL 3 architects: "All reviews in. Discussion phase — read each other's findings in the review panel directory and raise cross-cutting concerns. Message each other directly."

3. **Go idle.** After processing and sending any messages, stop. Wait for the next message. Do not poll.

#### Rules:
- **Do NOT respond to idle notifications** — agents go silent after one message. Responding wastes tokens.
- **Do NOT micromanage** — architects know their domains. Let them work.
- **Do NOT poll TaskList in a loop** — react to messages only.
- **DO trigger the discussion phase** when all reviews are in — this is your primary coordination job.
- **DO let architects talk to each other** — the discussion is peer-to-peer, not facilitated.

### Step 5: Consolidate and Write the Review Document

When all 3 architects have sent "discussion complete":

1. Read all findings files from the review panel directory:
   - `{review_panel_dir}/security-architect-findings.md`
   - `{review_panel_dir}/backend-architect-findings.md`
   - `{review_panel_dir}/ux-dx-architect-findings.md`

2. Review the cross-cutting discussion messages for trade-offs and cross-domain concerns.

3. Write the consolidated review document:
   - If target is inside a feature directory: write as `{feature_dir}/[filename]-review.md` (e.g., `webhook-retry/trd-review.md`)
   - Otherwise: write as `[target-name]-review.md` in the working directory

```markdown
# Architecture Review: [Target Name]

**Date:** [current date]
**Review Panel:** security-architect, backend-architect, ux-dx-architect
**Target:** [what was reviewed]

---

## Executive Summary

[3-5 sentence overview of the review findings, overall assessment, and key recommendations]

**Overall Assessment:** [Ready for Implementation / Needs Revisions / Significant Concerns]

---

## Critical Findings

[Issues that MUST be addressed before proceeding, from any architect]

---

## Security Review

[Consolidated findings from security-architect]

---

## Backend Architecture Review

[Consolidated findings from backend-architect]

---

## UX/DX Review

[Consolidated findings from ux-dx-architect]

---

## Cross-Cutting Concerns

[Issues identified during team discussion that span multiple domains]

---

## Trade-off Decisions

[Where architects disagreed and the recommended balance]

---

## Recommendations Summary

### Must Do (Critical/High)
1. [...]

### Should Do (Medium)
1. [...]

### Nice to Have (Low)
1. [...]

---

## Open Questions

- [ ] [Questions that need input from the author/team]
```

### Step 6: Clean Up

1. Send shutdown requests to all 3 architect teammates
2. Wait for acknowledgments
3. Tell the user where the review document was saved

## Example Usage

```
/team-review PR #142                                    → writes pr-142-review.md, .review-panel/ at root
/team-review the authentication module in parapetsecurity-api
/team-review docs/IN_PROGRESS/webhook-retry/trd.md      → writes webhook-retry/trd-review.md, webhook-retry/.review-panel/
/team-review docs/IN_PROGRESS/webhook-retry/plan.md     → writes webhook-retry/plan-review.md, webhook-retry/.review-panel/
/team-review webhook-retry-trd.md                        → writes webhook-retry-trd-review.md (flat fallback)
```

## Notes

- The review team uses the agent teams feature (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` enabled for the task tools)
- Teams are implicit: spawning a named agent joins the session's single team. There is no team to create or delete.
- Each architect runs as a separate Claude session — see each agent's `model` frontmatter for its tier
- Architects write findings to files, not to messages — keeps message traffic minimal
- Discussion phase is peer-to-peer: architects message each other directly, team lead does not facilitate
- Team lead's only active job: detect all reviews complete → trigger discussion → detect all discussions complete → consolidate
- For large reviews (entire codebase), consider scoping to specific modules or concerns
