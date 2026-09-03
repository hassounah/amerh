---
name: feature-prd
description: Produce a research-backed Product Requirements Document (PRD) with competitive analysis, user stories, and success metrics. All market claims are sourced via web research. Feeds into /feature-design for technical handoff.
allowed-tools: ["AskUserQuestion", "Agent", "Read", "Glob", "Bash"]
argument-hint: "[feature/product description or leave blank for guided walkthrough]"
---

# /feature-prd - Product Requirements Document Generator

Define what to build and why — with sourced market research, competitive analysis, and clear requirements — before handing off to engineering via /feature-design.

## Process

### Step 1: Gather Product Context

**If the user provided arguments** (a feature/product description), use that as the starting point. Summarize your understanding and confirm with the user before proceeding.

**If no arguments were provided**, walk the user through defining the product need using AskUserQuestion. Ask these questions in sequence (not all at once):

1. **What do you want to build?**
   - Get a clear description of the feature or product
   - Ask follow-up questions if the description is vague

2. **Who is the target user?**
   - End customers, internal teams, developers, enterprise buyers, etc.
   - What context are they in when they need this?

3. **What problem does this solve?**
   - Business motivation, user pain point, or market opportunity
   - How are users solving this today (workarounds, competitors)?

4. **Any known competitors or references?**
   - Products to analyze, benchmarks to meet, standards to follow
   - "Better than X" or "Similar to Y but for Z"

5. **Any constraints?**
   - Budget, platform, regulatory requirements
   - Integration needs, existing commitments

### Step 2: Launch Product Manager

Once you have a clear product context, spawn the `product-manager` agent using the Agent tool:

```
Use the Agent tool with:
- subagent_type: "corner-office:product-manager"
- prompt: Include the full feature description, target user, problem statement, competitive references, and any constraints gathered in Step 1. Include the working directory path so the agent knows where to write the PRD.
```

**Important**: Pass ALL context gathered from the user to the agent. The agent will conduct web research for competitive analysis and market context, so give it every lead — competitor names, reference products, industry terms.

### Step 3: Review and Deliver

After the product-manager agent completes:

1. Read the generated PRD file
2. Present a brief summary to the user:
   - Key competitive findings
   - Number of functional requirements (by priority)
   - Target personas identified
   - Success metrics defined
   - Number of sources cited
3. Tell the user where the PRD file was saved
4. Ask if they want any changes, additional research, or deeper analysis on any section

## Handoff to Engineering

When the PRD is finalized, tell the user:

"PRD complete. To hand off to engineering, run:
  /feature-design [feature-name]-prd.md
This will produce a Technical Requirement Document (TRD) based on the product requirements."

The PRD → TRD handoff is the product-to-engineering boundary. The PRD defines WHAT and WHY. The TRD defines HOW.

## Example Usage

```
/feature-prd Add real-time alerting with Slack and PagerDuty integration
/feature-prd
/feature-prd Build a self-service onboarding flow for enterprise customers
```

## Notes

- The product-manager agent uses WebSearch and WebFetch for real market research
- Every competitive claim in the PRD includes a source with URL
- The PRD is saved as `[feature-name]-prd.md` in the working directory
- The agent uses Opus for best reasoning quality on research and analysis
- Research typically adds 1-2 minutes vs. non-researched specs — worth it for accuracy
