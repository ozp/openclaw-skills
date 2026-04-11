---
name: serena-source-consultation
description: Use Serena plus local docs/source mirrors to verify real system behavior before making claims about architecture, configuration, hooks, agent behavior, or workspace-file semantics. Trigger when a task requires consulting source code, tracing implementation details, validating a plan against code, auditing a workspace against the actual code path, or checking drift between docs/config and implementation.
---

# Serena Source Consultation

Use this skill to run verification-first analysis against code and documentation.

## Core rule

Do not treat documentation, memory, or workspace conventions as authoritative when the answer depends on implementation details.
Consult the real source path first, then evaluate the local artifact.

## Workflow

1. Classify the question.
   - **Docs/interface question** → read local docs first.
   - **Behavior/implementation/compliance question** → consult source code.
2. Identify the target repository and verify local mirror state.
3. Consult source using the Serena workflow in `references/workflow.md`.
4. Only after source consultation, inspect the local config/workspace artifact.
5. Report separately:
   - source evidence,
   - local artifact evidence,
   - verified facts,
   - drift/discrepancies,
   - recommendation.

## Mandatory source-first triggers

Consult source before concluding on:
- OpenClaw architecture or runtime behavior
- meaning or effect of workspace files such as `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md`, `MEMORY.md`
- agent routing, hooks, compaction, memory, heartbeat, or tool behavior
- whether a skill or plan is aligned with actual implementation
- compliance or audit claims that depend on how the software really works

## Multi-phase audit rule

If a workspace or compliance audit depends on code semantics, split the work:

### Phase A — Canonical behavior
Map how the relevant feature works in code/docs.

### Phase B — Local state
Inspect the actual workspace/config files.

### Phase C — Drift assessment
Compare intended/canonical behavior against the local artifact.

If Phase A was not done, label the result **partial** rather than complete.

## Repo and mirror handling

Follow `references/repo-policy.md` when the target repository is local, mirrored, missing, stale, or needs refresh.

## Current OpenClaw environment

For this workspace, the main local OpenClaw source mirror and Serena path are documented in `references/workflow.md`.
Use that as the default target when the task is about OpenClaw itself.
