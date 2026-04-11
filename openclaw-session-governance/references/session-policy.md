# Session Governance Policy

## Objective

Keep durable OpenClaw sessions that preserve operational context, while preventing accumulation of stale ephemeral runs that confuse status output or resurface old work.

## Lifecycle layers

### 1. Conversation binding
- Controlled by session idle / max-age policies.
- Governs routing.
- Does not delete session records.

### 2. Session-store retention
- Controlled by session maintenance.
- Governs how long entries remain in the store.
- May warn or prune depending on configuration.

### 3. Explicit deletion / cleanup
- Removes session entries or cleanup artifacts.
- Must be treated separately from routing and retention.

## Classification model

### Persistent
Long-lived human-facing or operator-facing sessions with continuing context value.

Examples:
- `agent:main:main`
- intentionally durable specialist bases

Action:
- keep

### Recurring worker
Stable base sessions for ongoing automation.

Examples:
- `agent:karakeep:karakeep-cron-worker`

Action:
- keep the base session
- review surrounding ephemeral run residue separately

### Ephemeral completed
Finished subagents, retries, one-off runs, old provider threads, cron run sessions.

Examples:
- `:subagent:`
- `:cron:...:run:`
- `:openai:`

Action:
- cleanup candidate after retention threshold

Default threshold:
- 72 hours

### Review required
Anything unclear, inconsistent, or historically noisy.

Examples:
- cron summary helper sessions
- specialist bases no longer known to be active
- sessions implicated in delayed resurfacing incidents
- lead / MC sessions with unclear current role

Action:
- inspect first
- only then remove or reclassify

## Local defaults for this environment

### Protected exact keys
- `agent:main:main`
- `agent:karakeep:karakeep-cron-worker`
- `agent:sentinel:main`

### Review-first exact keys
- `agent:karakeep:karakeep-cron-summary`
- `agent:mineru:main`

### Cleanup-pattern heuristics
- keys containing `:subagent:`
- keys containing `:openai:`
- keys matching `:cron:...:run:`

## Operational cadence

### Weekly
- run audit
- generate updated markdown report
- run cleanup-safe in preview mode
- review new cleanup candidates
- optionally enforce safe cleanup when explicitly approved

### After incidents
- inspect any session linked to resurfacing, delayed announce, or stale artifact emission
- document the implicated keys
- reclassify if needed

### After architecture changes
- review recurring worker bases
- confirm protected set is still correct

## Cron recommendation

Use a weekly cron as a cadence trigger, not as the policy itself.

Recommended weekly job:
- run the audit
- run cleanup-safe in preview mode
- announce a concise summary with counts and report paths

Do not schedule automatic destructive cleanup until the preview output has been stable for multiple cycles.

## Success criteria

The policy is working when:
- active session lists are understandable
- recurring worker bases remain intact
- ephemeral residue does not accumulate indefinitely
- old sessions do not resurface abandoned work unexpectedly
