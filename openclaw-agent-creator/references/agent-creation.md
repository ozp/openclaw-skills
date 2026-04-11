# Agent Creation Reference

## Verified CLI patterns

### Interactive

```bash
openclaw agents add <name>
openclaw agents add <name> --workspace <dir>
openclaw agents add <name> --workspace <dir> --bind <channel[:accountId]>
```

### Non-interactive

```bash
openclaw agents add <name> \
  --workspace <dir> \
  --model <provider/model> \
  --non-interactive
```

Notes:
- Agent IDs are normalized from the supplied name.
- `--non-interactive` requires `--workspace`.
- Authentication/model setup can be configured during the interactive flow.

## Workspace file map

OpenClaw expects these user-editable files in the workspace bootstrap set:

- `AGENTS.md` — operational rules, startup sequence, memory policy
- `SOUL.md` — persona, tone, boundaries
- `TOOLS.md` — environment-specific notes and conventions
- `IDENTITY.md` — name, emoji, avatar, concise identity
- `USER.md` — who the agent helps and how to address them
- `HEARTBEAT.md` — periodic checklist or intentionally empty heartbeat instructions
- `BOOTSTRAP.md` — first-run ritual for brand-new workspaces only
- `MEMORY.md` — curated long-term memory
- `memory/YYYY-MM-DD.md` — daily notes, not auto-injected

## Injection and token implications

Bootstrap files are appended into project context on each turn. Keep them concise.

Key implications:
- `MEMORY.md` is injected when present and can grow expensive.
- `memory/*.md` daily notes are not auto-injected; load them on demand.
- Large bootstrap files are truncated.
- The default per-file cap is controlled by `agents.defaults.bootstrapMaxChars`.
- The default total bootstrap cap is controlled by `agents.defaults.bootstrapTotalMaxChars`.

## Mapping a design document into workspace files

Use this mapping when converting a user document or third-party template into a real agent:

### `IDENTITY.md`
Put only stable identity markers:
- agent name
- role/nature
- vibe
- emoji/avatar

### `SOUL.md`
Put only enduring behavioral guidance:
- communication style
- decision posture
- boundaries
- domain stance

Avoid operational checklists here.

### `AGENTS.md`
Put execution rules here:
- startup sequence
- what to read each session
- memory policy
- safety rules
- workflow rules
- group chat behavior if relevant

### `USER.md`
Put only user-specific profile details:
- name / preferred form of address
- pronouns
- timezone
- stable preferences that are safe to expose in that workspace

### `TOOLS.md`
Put setup-specific notes here:
- local hostnames
- camera names
- speaker names
- custom conventions
- file paths that are environment-specific

### `HEARTBEAT.md`
Keep it small. Use it for recurring checks or leave it empty by default when no periodic behavior is wanted.

### `BOOTSTRAP.md`
Use only for first-run discovery. Delete after the ritual is complete.

## Inter-agent visibility (`allowAgents`)

**Default behavior: isolation.** After `openclaw agents add`, the new agent is invisible to every other agent. No agent can discover or spawn it via `agents_list` / `sessions_spawn` until explicitly permitted.

This is bidirectional — each agent independently controls who it can see:
- Agent A needs `allowAgents: ["B"]` to discover/spawn B.
- Agent B needs `allowAgents: ["A"]` to discover/spawn A.

Configure in `openclaw.json` under `agents.list[].subagents.allowAgents`:

```json5
{
  agents: {
    list: [
      {
        id: "main",
        subagents: {
          allowAgents: ["mineru"]   // main can see and spawn mineru
        }
      },
      {
        id: "mineru",
        subagents: {
          allowAgents: ["main"]    // mineru can see and spawn main
        }
      }
    ]
  }
}
```

Use `["*"]` to allow visibility to all configured agents (less restrictive, useful for orchestrators).

To apply the same policy to all agents at once, set `allowAgents` in `agents.defaults.subagents` instead of per-agent.

**This step is never done automatically by the CLI.** Omitting it is the most common reason `agents_list` returns an empty or incomplete list.

## Exec policy baseline for new agents

Creation and visibility are not enough. New agents also need an explicit host-exec posture.

Recommended baseline for this environment:

- `main`: human-supervised operator; may remain `full` when intentionally configured that way.
- new non-main agents: start in burn-in mode with host approvals set to `allowlist` + `ask=on-miss`.
- mature worker agents: keep per-agent `allowlist`; optionally set `ask=off` once the command set is stable.
- avoid using `full` as the default for every newly created worker agent.

Clarifications:
- `security = "full"` is unrestricted host exec as the runtime user on the gateway/node host. It does **not** imply root by itself.
- skills do not replace exec approvals.
- if an agent needs interpreters (`python3`, `node`, etc.), prefer `strictInlineEval = true`.

Suggested rollout method:
1. create the agent;
2. keep host exec conservative at first;
3. observe the actual recurring commands;
4. add a narrow per-agent allowlist;
5. only after stabilization, consider removing prompts for allowlisted commands.

## Minimal creation checklist

1. Define purpose and scope.
2. Choose interactive or non-interactive creation.
3. Run `openclaw agents add ...`.
4. Verify the workspace path.
5. Customize the bootstrap files.
6. Remove `BOOTSTRAP.md` after first-run setup if it is no longer needed.
7. Keep workspace instructions short enough to avoid context bloat.
8. **Configure inter-agent visibility.** Edit `openclaw.json` and add `subagents.allowAgents` to every agent that needs to discover or spawn the new agent, and to the new agent itself if it needs to call back. Without this step, `agents_list` will not return the new agent to any other agent.
9. **Configure exec posture explicitly.** Record whether the agent is `full`, `allowlist + on-miss`, or `allowlist + ask=off`, and why.

## Source basis used for this skill

This reference is based on verified local OpenClaw docs for agent runtime, bootstrap injection, and template files, plus the user's supplied draft document for the practical authoring flow. Treat local docs as authoritative when conflicts appear.
