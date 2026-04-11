---
name: openclaw-agent-creator
description: Create and bootstrap new OpenClaw agents and their workspaces. Use when the user asks to create a new agent, add an isolated agent with `openclaw agents add`, set up an agent workspace, prepare AGENTS.md/SOUL.md/IDENTITY.md/USER.md/TOOLS.md/BOOTSTRAP.md/HEARTBEAT.md, turn an agent concept or template into a runnable OpenClaw agent, or iterate on an existing agent's behavior and guardrails.
---

# OpenClaw Agent Creator

Create agents with the OpenClaw CLI first. Use manual file edits to refine the generated workspace after creation.

## Workflow

### 1. Clarify the agent design

Ask only for the missing information. Prefer short rounds.

Minimum question set:
- mission: what the agent is for;
- surfaces: where it will operate and whether group chats matter;
- autonomy: advisor vs operator vs broad autonomy;
- prohibitions: what it must never do;
- memory posture: whether it should keep curated long-term memory;
- tone: concise/formal/warm and whether it should avoid speaking as the user;
- tool posture: tool-first vs answer-first and how strict verification should be.

### 2. Create the agent

Choose creation mode:
- interactive CLI for normal setup;
- non-interactive CLI for repeatable automation.

#### Interactive mode

```bash
openclaw agents add <agent-name>
```

Use CLI options when needed:

```bash
openclaw agents add <agent-name> --workspace <dir> --bind <channel[:accountId]>
```

#### Non-interactive mode

```bash
openclaw agents add <agent-name> \
  --workspace <dir> \
  --model <provider/model> \
  --non-interactive
```

`--non-interactive` requires `--workspace`.

### 3. Customize the workspace files

After creation, review and tailor the workspace files.

Core files:
- `IDENTITY.md`
- `SOUL.md`
- `AGENTS.md`
- `USER.md`
- `HEARTBEAT.md`

Optional files:
- `TOOLS.md`
- `BOOTSTRAP.md` for first-run discovery only
- `MEMORY.md`
- `memory/YYYY-MM-DD.md` seed entry when useful

Keep bootstrap files concise because injected files consume context tokens on every turn.

### 4. Apply the guardrails checklist

Ensure the generated agent includes explicit rules for:
- ask before destructive actions;
- ask before outbound messages or external side effects;
- stop and recover when CLI usage is wrong or an unknown flag appears;
- avoid loops and repeated retries without a changed plan;
- respect group chat etiquette;
- keep essential operational rules in `AGENTS.md`, because sub-agents inherit less context.

### 5. Configure inter-agent visibility

**The CLI never does this automatically.** After creation, the new agent is invisible to every other agent by default — `agents_list` will not return it.

Always determine:
- which existing agents need to discover or spawn this new agent;
- whether the new agent needs to call back to any of them.

Then edit `openclaw.json` and add `subagents.allowAgents` in **both directions** for each pair that needs to communicate:

```json5
// In agents.list:
{ id: "main",   subagents: { allowAgents: ["mineru"] } }
{ id: "mineru", subagents: { allowAgents: ["main"]   } }
```

Use `["*"]` on an orchestrator agent to allow it to see all configured agents. See `references/agent-creation.md` for full details.

### 6. Configure exec posture explicitly

Do **not** assume a newly created agent inherits a safe and functional host-exec policy.

Use this default operating policy for agents created outside Mission Control unless there is a strong reason to do otherwise:

- `main` or another human-supervised break-glass operator: may use `tools.exec.security = "full"` with approvals aligned intentionally.
- new specialist/worker agents: start with `allowlist` + `ask=on-miss`.
- once a worker agent's command set is understood and stable: keep `allowlist`, but consider `ask=off` for autonomy.
- avoid making every new agent `full` by default.

Important clarifications:
- `security = "full"` means unrestricted host exec as the gateway/node runtime user; it is **not** automatic root.
- skills and prompts do not replace host exec approvals; exec policy must still be modeled explicitly.
- for interpreters like `python3` or `node`, prefer `strictInlineEval = true`.

Operational method:
1. create the agent;
2. run it in `allowlist + on-miss` burn-in mode;
3. observe which commands are actually needed;
4. convert to a narrow per-agent allowlist;
5. only then consider `ask=off`.

Document the chosen exec posture for every new agent in the workspace or creation notes so future sessions do not have to rediscover it.

### 7. Validate with short acceptance tests

Provide a few scenario prompts to test the result, for example:
- draft but do not send a message;
- summarize workspace state without exposing secrets;
- recover from an unknown CLI flag by checking `--help`;
- decide whether to reply in a group chat;
- decide whether to ask for confirmation before an external or destructive action;
- confirm that `agents_list` returns the new agent from any agent that should be able to spawn it.

## Community Agent Library

Before designing a new agent from scratch, consult the **awesome-openclaw-agents** library for ready-made SOUL.md templates:

- **199 templates** across 25 categorias: automation, business, creative, data, development, devops, education, finance, hr, marketing, productivity, security, e mais.
- Cada entry tem identidade nomeada (Lens para code review, Beats para música, Clipper para vídeo) e SOUL.md estruturado.
- Usar como inspiração para naming, definição de role, responsabilidades, regras Do/Don't e formatos de output.

**Mirror local disponível** (preferencial — sem rede):
```bash
MIRROR=/home/ozp/code/mirror/awesome-openclaw-agents

# Buscar por categoria
jq -r '.agents[] | select(.category=="development") | "\(.id) — \(.name): \(.role)"' $MIRROR/agents.json

# Ler SOUL.md de um template
cat $MIRROR/agents/development/code-reviewer/SOUL.md

# Busca por palavra-chave
jq -r '.agents[] | select((.name+.role)|ascii_downcase|contains("review")) | "\(.category)/\(.id)"' $MIRROR/agents.json
```

**Nota:** `agents.json` tem estrutura `{ "total": 199, "agents": [...] }` — usar `.agents[]`, não `.[]`.

For the full catalog (25 categories, all commands, usage patterns), see:

- [`references/awesome-openclaw-agents.md`](references/awesome-openclaw-agents.md)

## How to adapt a template or concept

When the user provides a document, prompt, or third-party agent template:

1. Extract only durable operating rules, persona guidance, and workflow logic.
2. Map content into the correct files:
   - identity traits → `IDENTITY.md`
   - persona/tone/boundaries → `SOUL.md`
   - startup and operating rules → `AGENTS.md`
   - user-specific address/preferences → `USER.md`
   - environment-specific notes → `TOOLS.md`
   - heartbeat checklist → `HEARTBEAT.md`
   - first-run discovery ritual → `BOOTSTRAP.md`
3. Remove marketing language, redundant explanation, and non-OpenClaw instructions.
4. Verify commands and file behavior against local OpenClaw docs before asserting them.

## How to iterate on an existing agent

When improving an existing agent, first identify:
- top failure modes;
- desired autonomy changes;
- new safety boundaries;
- heartbeat changes.

Then make minimal, surgical edits to the relevant files instead of rewriting the whole workspace.

## Decision points to surface

Escalate before proceeding when the choice changes security, cost, or routing behavior:
- model/provider selection;
- channel bindings;
- agent workspace location outside the normal layout;
- authentication setup;
- whether the agent should be a persistent standalone agent versus just a reusable skill/template;
- which agents need bidirectional `allowAgents` visibility with the new agent.

## References

Read `references/agent-creation.md` when you need verified command/file details, workspace mapping, and token implications.

Read `references/awesome-openclaw-agents.md` for the community template library (162 agent SOUL.md templates across 19 categories) — consult before creating any new agent.
