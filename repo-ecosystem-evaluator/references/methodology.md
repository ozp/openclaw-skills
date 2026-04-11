# Repository Ecosystem Evaluator — Methodology v2

This evaluator uses a **hybrid method**:

1. **Static structural analysis** for architecture, dependencies, complexity, and maintainability signals
2. **Semantic-static analysis** for domain boundaries, rule visibility, contract explicitness, and critical flow inference
3. **Stack fit assessment** for environment compatibility and operational complexity
4. **ATAM-lite scenario review** for quality-attribute tradeoff framing
5. **ISO/IEC 25010 alignment** for standardized quality dimensions

## Standards and Best-Practice Anchors

The evaluator is informed by the following families of methods:

- **ISO/IEC 25010 / SQuaRE** for quality characteristics, especially maintainability, reliability, compatibility, portability, and security signals
- **ATAM (Architecture Tradeoff Analysis Method)** for scenario-driven architecture evaluation and tradeoff identification
- **Maintainability Index** for a standardized maintainability proxy based on size, complexity, and comments
- **Martin package metrics** style reasoning for coupling and instability (`Ce`, `Ca`, `I = Ce / (Ca + Ce)`)
- **Static code review best practices** for boundary violations, god objects, error swallowing, and state leakage

## Dimensions

### 1. Architecture / Structure

Evaluates:
- entry points
- module boundaries
- layer detection
- dependency direction
- cycle detection
- architecture pattern classification

Primary outputs:
- detected pattern
- confidence
- violations
- fan-in / fan-out
- instability

### 2. Maintainability

Evaluates:
- lines of code
- comment ratio
- cyclomatic proxy
- maintainability index proxy
- coupling / cohesion signals
- god object hints

Primary outputs:
- maintainability index
- consistency score
- spaghetti risk

### 3. Reliability / Error Handling

Evaluates:
- exception / try-catch coverage signals
- silent/swallowed error patterns
- fallback hints
- guard clause presence

Primary outputs:
- strategy
- coverage percentage
- silent error count

### 4. Semantic Layer

This is intentionally not pure regex-only architecture labeling.
It tries to recover higher-level software meaning through code/document clues.

Evaluates:
- **domain centralization** — whether business logic appears concentrated in domain/service/usecase layers
- **invariant visibility** — whether explicit guards, assertions, validation, and rule checks are visible
- **contract explicitness** — DTOs, schemas, serializers, validators, typed contracts
- **boundary discipline** — whether business rules leak into adapters/controllers/routes
- **naming coherence** — whether entities and use cases are expressed clearly enough to reconstruct intent
- **critical flows** — repeated create/update/delete/process/approve-style flows across layers

Primary outputs:
- semantic score
- inferred entities
- inferred use cases
- invariants
- critical flows
- semantic risks

### 5. Stack Evaluation

Evaluates:
- frameworks and runtime mix
- datastore dependencies
- infra dependencies
- packaging/tooling surface
- observability signals
- local development friction
- deployability
- portability
- environment-specific fit

Primary outputs:
- stack fit score
- operational surface area
- local dev friction
- ATAM-lite scenarios

## Scoring Model

### Overall score

The current default overall score is:

```text
overall =
  consistency_score * 0.45 +
  (maintainability_index / 10) * 0.20 +
  semantic_score * 0.20 +
  stack_fit_score * 0.15
```

### Consistency score

```text
consistency =
  architecture_conformance * 0.25 +
  error_handling * 0.20 +
  state_management * 0.15 +
  coupling_cohesion * 0.25 +
  testability * 0.15
```

## Recommendations

- **adopt**: overall >= 7 and no major blockers
- **evaluate**: overall >= 4 or important tradeoffs remain
- **avoid**: overall < 4 or blocked by major risk

## Known Limits

- Static analysis cannot fully prove runtime correctness
- Semantic inference remains heuristic unless paired with interactive code reading
- Maintainability Index is approximate because cyclomatic and Halstead values are estimated without a full parser
- Framework detection is manifest/text-driven and may miss unconventional stacks

## Intended Usage

Use this evaluator in two passes:

### Pass 1 — broad screening
Use the full repo evaluator to decide whether a repository is promising.

### Pass 2 — focused review
If promising but uncertain, use the semantic outputs and stack outputs to guide deeper human/LLM review of:
- core business flows
- invariants
- integration points
- operational tradeoffs
