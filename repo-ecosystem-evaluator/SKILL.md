---
name: repo-ecosystem-evaluator
description: "Evaluate repositories for architecture quality, semantic design coherence, and stack fit using standardized static metrics plus ATAM-lite and ISO/IEC 25010-aligned heuristics. Use when auditing unfamiliar repos, comparing alternatives, assessing adoption risk, or checking environment fit."
version: 2.0.0
metadata:
  openclaw:
    homepage: https://github.com/yourusername/repo-ecosystem-evaluator
    requires:
      anyBins:
        - git
        - python3
        - find
        - grep
---

# Repository Ecosystem Evaluator

## Purpose

Evaluate software repositories for:

1. **architectural consistency**
2. **maintainability and dependency quality**
3. **semantic design coherence**
4. **stack suitability for a target environment**

This skill is designed for repository selection, architecture triage, technical due diligence, and internal codebase audits.

Unlike repo comparison methods based on popularity or CI badges, this skill evaluates **intrinsic technical quality** using static evidence, standardized metrics, and scenario-based stack analysis.

## What Changed in v2

This skill now has a more honest and more useful scope:

- It no longer presents itself as a fully generic "deep semantic analyzer" by default.
- It explicitly distinguishes **implemented static/semantic-static analysis** from **human/LLM deep review**.
- It adds a **semantic layer** that looks for domain centralization, invariant visibility, contract explicitness, and critical business-flow hints.
- It adds a dedicated **stack evaluation** function.
- It aligns its outputs with **ISO/IEC 25010-inspired quality dimensions** and **ATAM-lite tradeoff framing**.

## When to Use This Skill

Use this skill when:

- evaluating candidate replacements for an existing system
- comparing multiple repositories side-by-side
- auditing an unfamiliar or inherited codebase
- assessing adoption risk before introducing a dependency or fork
- identifying maintainability hotspots and logical defect signals
- checking whether a repository fits `local_dev`, `enterprise_k8s`, `cloud_serverless`, or `edge_device`

**Trigger phrases:**
- "analyze this repository"
- "compare these software options"
- "audit this codebase"
- "evaluate repo architecture"
- "assess environment fit"
- "analyze stack"
- "check if this repo is maintainable"

## Implemented Capabilities

### A. Structural / Static Analysis

- repository structure mapping
- entry point detection
- layer detection
- dependency graph extraction
- fan-in / fan-out metrics
- cycle detection
- architecture pattern classification
- error handling pattern detection
- global state and coupling heuristics
- maintainability index proxy

### B. Semantic-Static Analysis

This is not full formal program analysis. It is a **semantic-static layer** built from code/document evidence.

It evaluates:
- **domain centralization** — whether business logic appears concentrated in service/domain/usecase layers
- **invariant visibility** — guards, assertions, validations, explicit rule checks
- **contract explicitness** — DTOs, schemas, serializers, validators
- **boundary discipline** — whether business rules leak into controllers/routes/handlers
- **naming coherence** — whether entities and use cases are expressed clearly enough to reconstruct intent
- **critical flow inference** — whether important create/update/delete/process flows can be traced across modules

### C. Stack Evaluation

A dedicated stack assessment examines:
- frameworks
- datastores
- infra dependencies
- packaging/tooling
- observability signals
- local development friction
- deployability
- portability
- environment-specific fit

## Standards / Methods Used

This skill is informed by:

- **ISO/IEC 25010 / SQuaRE** quality dimensions
- **ATAM** principles for scenario-driven architecture evaluation
- **Maintainability Index** style scoring
- **Martin-style dependency reasoning** (`fan-in`, `fan-out`, `instability`)
- practical static review heuristics for coupling, state leakage, swallowed errors, and god objects

See `references/methodology.md` and `references/heuristics.md`.

## Commands / Execution

### Full repository evaluation

```bash
python3 scripts/repo_eval.py /path/to/repo --env local_dev --format json
python3 scripts/repo_eval.py /path/to/repo --env enterprise_k8s --format markdown
```

### Focused stack evaluation

```bash
python3 scripts/stack_eval.py /path/to/repo --env local_dev --format json
python3 scripts/stack_eval.py /path/to/repo --env cloud_serverless --format markdown
```

## Output Model

The evaluator returns a structured report with these top-level sections:

- `summary`
- `architecture`
- `quality`
- `semantic`
- `stack`
- `risks`
- `evidence`

See `references/evaluation-schema-v1.json`.

## Recommended Workflow

### Phase 1 — Broad screen

Run the full evaluator to answer:
- Is the repo internally coherent?
- Is it likely maintainable?
- Does the stack fit the target environment?

### Phase 2 — Semantic review

If the repo looks promising but uncertain, inspect the semantic section:
- inferred entities
- inferred use cases
- explicit invariants
- critical flows
- semantic risks

Use this as a guide for deeper manual or LLM-assisted review of the core business logic.

### Phase 3 — Decision framing

Use the final report to classify the repository as:
- `adopt`
- `evaluate`
- `avoid`

## Critical Rules

1. **Evidence first** — conclusions must be grounded in files, manifests, imports, symbols, or detected rule patterns
2. **Do not overclaim semantics** — semantic-static analysis is stronger than folder-name inspection but weaker than full human code comprehension
3. **Separate architecture quality from stack fit** — a clean codebase can still be a poor fit for the target environment
4. **Penalize anti-patterns** — cycles, god objects, swallowed errors, global mutable state, and business logic leaking into adapters
5. **Report uncertainty honestly** — when coverage or evidence is weak, downgrade confidence

## Limitations

- Static analysis only; no execution or test running
- Semantic layer is heuristic, not formal verification
- Maintainability Index is approximate because full AST/CFG metrics are not computed
- Language support is best for Python, JS/TS, Go, Rust, and Java
- Stack detection is manifest/text based and may miss non-standard setups

## Practical Positioning

This skill should be treated as:

- **implemented** for static structure, dependency, maintainability, and stack fit screening
- **useful but heuristic** for semantic design analysis
- **not a substitute** for targeted human/LLM review of the most important business flows

## Version

2.0.0 - 2026-04-09
