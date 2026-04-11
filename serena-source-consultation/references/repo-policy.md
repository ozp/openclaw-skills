# Repository and Mirror Policy

## Goal

Keep source consultation repeatable by working against known local mirrors when possible.

## Mirror root convention

For agents that manage their own mirrors, use the explicitly documented authoritative mirror root for that agent. For Sentinel in this workspace, that root is `/home/ozp/code/mirror/`.

## Operating rules

1. If a suitable local mirror already exists, inspect it first.
2. If no local mirror exists and remote retrieval is allowed, create one and report that this happened.
3. If a local mirror exists, verify whether it appears stale before relying on it for architecture/compliance conclusions.
4. When feasible, compare:
   - local installed/runtime version,
   - local mirror branch/commit,
   - upstream branch/commit.
5. If the mirror is stale and freshness matters, update it and report the update.

## Minimum reporting

For any source-based conclusion, report when available:
- repository path
- branch
- local commit
- upstream reference checked
- freshness status: current / stale / unknown

## OpenClaw-specific note

The current local mirror used for OpenClaw source consultation is `/home/ozp/code/mirror/openclaw-src/`.
If future agents maintain their own per-agent mirrors, document the authoritative path clearly to avoid split-brain analysis.
