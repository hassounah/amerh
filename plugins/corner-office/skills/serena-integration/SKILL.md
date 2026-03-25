---
name: serena-integration
description: Use this skill when navigating large codebases, finding symbol definitions, tracing references, performing structural code analysis, or discovering and using MCP server tools via ToolSearch. Teaches agents how to use Serena MCP tools effectively for code intelligence tasks that go beyond file-level search.
---

# Serena Integration Skill

Serena is a language-server-powered MCP tool suite that understands code structure — symbols, references, definitions — across the entire codebase. Use it when you need semantic code navigation, not just text search.

## When to Use Serena vs Native Tools

| Task | Use Serena | Use Native Tools |
|------|-----------|-----------------|
| Find where a function is defined | `mcp__serena__find_symbol` | — |
| Find all callers of a function | `mcp__serena__find_referencing_symbols` | — |
| Get class/module structure overview | `mcp__serena__get_symbols_overview` | — |
| Rename a symbol project-wide | `mcp__serena__rename_symbol` | — |
| Replace a function body | `mcp__serena__replace_symbol_body` | — |
| Search for text pattern in files | — | `Grep` |
| Find files by name pattern | — | `Glob` |
| Read full file contents | — | `Read` |
| Quick keyword search | — | `Grep` |

**Rule of thumb:** Use Serena when you care about *what code means* (symbols, types, call graphs). Use native tools when you care about *what code contains* (text, filenames, line content).

## Available Tools

### Code Navigation

#### `mcp__serena__find_symbol`
Find where a symbol (function, class, variable, type) is defined.

```
Use when: You know the name of something and need its definition location.
Example: Finding where `processAlert` is defined across the project.
```

#### `mcp__serena__find_referencing_symbols`
Find all places that reference a given symbol — callers, importers, subclasses.

```
Use when: You need to understand the impact of changing a symbol, or trace data flow.
Example: "Where is this function called?" before refactoring it.
```

#### `mcp__serena__find_referencing_code_snippets`
Find code snippets around each reference to a symbol — more granular than `find_referencing_symbols`.

```
Use when: You need the actual usage context around each reference, not just locations.
Example: Seeing how callers pass arguments to a function before changing its signature.
Prefer find_referencing_symbols for a quick list; use this when you need surrounding code.
```

#### `mcp__serena__get_symbols_overview`
Get a structural overview of symbols in a file or directory — classes, functions, constants.

```
Use when: You need to understand the shape of a module without reading every line.
Example: Understanding what a service exposes before integrating with it.
```

#### `mcp__serena__find_file`
Find files by name or path pattern using Serena's index.

```
Use when: You need semantic file discovery (prefer Glob for pattern matching).
```

#### `mcp__serena__list_dir`
List directory contents through Serena's context.

```
Use when: Exploring project structure in the context of a Serena session.
```

#### `mcp__serena__search_for_pattern`
Search for a text or regex pattern across the codebase.

```
Use when: Grep is unavailable or you want Serena's context-aware results.
Prefer Grep for most pattern searches — it's faster for simple cases.
```

### Code Modification

#### `mcp__serena__replace_symbol_body`
Replace the entire body of a function, method, or class with new code.

```
Use when: Rewriting an entire function (cleaner than line-based edits for large rewrites).
Caution: Verify the symbol name is unique or qualify with file path.
```

#### `mcp__serena__rename_symbol`
Rename a symbol and update all references project-wide.

```
Use when: Renaming functions, classes, or variables that are referenced in many places.
This is far safer than find-and-replace — it understands scope.
```

#### `mcp__serena__insert_before_symbol` / `mcp__serena__insert_after_symbol`
Insert code before or after a named symbol.

```
Use when: Adding a new function adjacent to an existing one, or inserting imports.
```

### Memory Management

Serena provides a persistent memory system for storing notes across sessions.

#### `mcp__serena__write_memory`
Write a note to Serena's memory store.

```
Use when: Recording architectural decisions, gotchas, or patterns discovered during a session.
Security: NEVER write secrets, credentials, API keys, passwords, or PII to memory.
Memory files persist as plaintext on disk. Only store structural/architectural insights.
```

#### `mcp__serena__read_memory` / `mcp__serena__list_memories`
Read stored notes from Serena's memory.

```
Use when: Starting a new session and wanting context from previous work on the same codebase.
```

#### `mcp__serena__edit_memory` / `mcp__serena__delete_memory` / `mcp__serena__rename_memory`
Manage existing memory entries.

### Session Setup

#### `mcp__serena__initial_instructions`
Get Serena's initial instructions and context for the current project.

```
Call this first when starting a Serena session in a new project.
```

#### `mcp__serena__onboarding` / `mcp__serena__check_onboarding_performed`
Check and perform Serena's project onboarding to index the codebase.

```
Run onboarding once per project. Check first to avoid re-indexing.
```

## Activation Pattern

Before using any MCP tool, load it with ToolSearch. Serena has 13+ tools — ToolSearch returns at most 5 per call, so use multiple calls or load on-demand:

```
# Load navigation tools
ToolSearch: "+serena find symbol reference overview"

# Load memory and session tools
ToolSearch: "+serena memory write read"

# Or load a specific tool on-demand
ToolSearch: "select:mcp__serena__find_symbol"
```

This pattern works for ANY MCP server, not just Serena. Use ToolSearch to discover what's available before calling unfamiliar MCP tools.

## Common Workflows

### Tracing a Bug Through the Codebase

1. `mcp__serena__find_symbol` — locate the function where the bug lives
2. `mcp__serena__find_referencing_symbols` — find all callers to understand context
3. `mcp__serena__get_symbols_overview` — understand the module structure
4. `Read` — read specific files for details
5. `Edit` — make the targeted fix

### Safe Refactoring

1. `mcp__serena__find_symbol` — confirm the symbol's current definition
2. `mcp__serena__find_referencing_symbols` — see all call sites
3. `mcp__serena__rename_symbol` — rename with automatic reference updates
4. `Grep` — verify no string-based references were missed (e.g., in config files)

### Understanding a New Module

1. `mcp__serena__get_symbols_overview` — get the module's public surface
2. `mcp__serena__find_referencing_symbols` — see how it's used elsewhere
3. `Read` — read key files identified by the overview

### Large Function Rewrite

1. `Read` — read the existing function to understand it fully
2. `mcp__serena__replace_symbol_body` — replace with new implementation
3. Run tests to verify correctness

## If Serena Is Unavailable

If ToolSearch returns no `mcp__serena__*` tools, Serena is not configured for this project. Fall back to native tools:

| Serena Tool | Fallback | Notes |
|-------------|----------|-------|
| `find_symbol` | `Grep` for definition patterns | Less precise — may match comments/strings |
| `get_symbols_overview` | `Grep` + `Read` | Read file and scan for class/function definitions |
| `find_referencing_symbols` | `Grep` for symbol name across codebase | No scope awareness — will include false positives |
| `find_referencing_code_snippets` | `Grep` with context (`-C` flag) | Manual context extraction |
| `search_for_pattern` | `Grep` | Equivalent for most cases |
| `replace_symbol_body` | `Edit` / `Write` | Line-number based — less resilient to drift |
| `rename_symbol` | `Edit` with `replace_all` + `Grep` to verify | No scope awareness — verify manually |
| `insert_before/after_symbol` | `Edit` | Must identify correct line numbers |
| `read_memory` / `write_memory` | None | Skip memory operations entirely |

**Do NOT attempt to call Serena tools if they are not loaded — they will fail.** Detect availability via ToolSearch and adapt.

## Best Practices

- **Start with `initial_instructions`** when beginning a Serena session in a new project — it configures Serena correctly for the codebase.
- **Prefer `find_symbol` over Grep** for finding definitions — Serena understands scope and won't return false positives from comments or strings.
- **Use `find_referencing_symbols` before any rename** — knowing all call sites prevents broken refactors.
- **Use `replace_symbol_body` for large rewrites** — cleaner than multiple line-level edits, and Serena can verify the symbol exists before writing.
- **Store architectural insights in memory** — use `write_memory` to capture non-obvious design decisions so future sessions benefit from them.
- **Combine Serena with native tools** — Serena for structure, Grep/Glob/Read for content. They are complementary, not competing.
