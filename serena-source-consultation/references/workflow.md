# Serena Source Consultation Workflow

## Purpose

Use this workflow when you must verify behavior against the real codebase before proposing changes, evaluating compliance, or explaining how a feature works.

Canonical priority:
1. Runtime/system state
2. Source code
3. Local docs
4. Memory / prior notes

## Default OpenClaw target

- Local docs: `/home/linuxbrew/.linuxbrew/lib/node_modules/openclaw/docs/`
- Local source mirror: `/home/ozp/code/mirror/openclaw-src/`
- Serena project: `openclaw-src`
- Existing local method note: `/home/ozp/clawd/methods/source-consultation.md`
- Existing integration evaluation: `/home/ozp/clawd/automation/evaluations/serena-direct-host-integration.md`

## Decision tree

### Case 1 — Interface or documented usage
Read local docs first.
Escalate to source if the answer still depends on runtime or implementation behavior.

### Case 2 — Behavior, architecture, config, compliance, or workspace semantics
Consult source first.
Only then inspect the local config/workspace artifact.

## Serena sequence

Use this order whenever source consultation is needed:

1. Activate/load the target Serena project.
2. Locate the file with `find_file` or `list_dir`.
3. Inspect structure with `get_symbols_overview` when symbol-level understanding helps.
4. Read the implementation with `find_symbol` and/or `read_file`.
5. Trace usage with `find_referencing_symbols`.
6. Use `search_for_pattern` only with a restricted `relative_path` and explicit output limit.

## Query discipline

Avoid broad pattern searches.

Bad:
- searching a short generic term across `src/` without limits

Good:
- restrict `relative_path`
- set `max_answer_chars`
- search for specific symbol names, hook names, file names, or config keys

## Evidence standard

Before making a recommendation, capture:
- repository path / project name
- file path(s)
- symbol(s)
- line range(s) when available
- whether the evidence came from docs, code, runtime, or local workspace files

## Audit pattern for workspace files

When evaluating a workspace file such as `TOOLS.md`:
1. determine how that file is injected, loaded, or used in the product code/docs;
2. identify the practical effect of that file on agent behavior;
3. inspect the local file;
4. compare canonical behavior vs local content;
5. report drift, omissions, or over-claims.

## If Serena cannot be used

Fallback order:
1. local source mirror with ordinary file reads/searches if sufficient
2. GitHub source access for a specific path/commit
3. mark the conclusion as lower confidence if source semantics could not be verified adequately

## Current environment notes

- Serena via MCP/MCPHub is the currently validated working path.
- Direct host-native Serena integration was evaluated as technically viable but not yet standardized as the primary production path.
- Treat MCP Serena as the reliable operational path today unless the direct adapter is explicitly prepared and verified.
