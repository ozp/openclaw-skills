# Repository Ecosystem Evaluator

Evaluate repositories for **architecture quality**, **maintainability**, **semantic design coherence**, and **stack fit**.

This skill is designed for software due diligence, repo comparison, adoption screening, and environment-fit analysis.

## Scope

This is a **hybrid static evaluator**:

- **static analysis** for structure, dependencies, coupling, complexity, and maintainability
- **semantic-static analysis** for domain boundaries, invariants, contracts, and critical flow hints
- **stack evaluation** for environment fit and operational complexity
- **ATAM-lite framing** for scenario-based tradeoff discussion
- **ISO/IEC 25010-inspired quality mapping** for standardized reporting

It does **not** claim full semantic understanding or runtime correctness.

## Quick Start

### Full repository report

```bash
python3 scripts/repo_eval.py /path/to/repo --env local_dev --format json
python3 scripts/repo_eval.py /path/to/repo --env enterprise_k8s --format markdown
```

### Stack-only report

```bash
python3 scripts/stack_eval.py /path/to/repo --env local_dev --format json
```

## Target environments

- `local_dev`
- `enterprise_k8s`
- `cloud_serverless`
- `edge_device`
- `undefined`

## What it evaluates

### 1. Architecture / structure
- entry points
- layer layout
- dependency graph
- fan-in / fan-out
- instability
- cycle detection
- architecture pattern classification

### 2. Maintainability / code quality
- maintainability index proxy
- cyclomatic proxy
- comment ratio
- coupling / cohesion signals
- god object hints
- state management signals
- error handling coverage signals

### 3. Semantic layer
- domain centralization
- invariant visibility
- contract explicitness
- boundary discipline
- naming coherence
- inferred entities
- inferred use cases
- inferred critical flows

### 4. Stack evaluation
- frameworks
- datastores
- infra dependencies
- packaging/tooling
- observability
- local dev friction
- deployability
- portability
- scenario fit by target environment

## Methodological anchors

This skill draws from:

- **ISO/IEC 25010 / SQuaRE**
- **ATAM** (via an ATAM-lite scenario framing)
- **Maintainability Index** style analysis
- **Martin dependency metrics** style reasoning (`fan-in`, `fan-out`, `instability`)

See:
- `references/methodology.md`
- `references/heuristics.md`
- `references/evaluation-schema-v1.json`

## Interpreting scores

### Overall recommendation
- `adopt`
- `evaluate`
- `avoid`

### Important nuance
A repository can:
- score well structurally but poorly semantically
- be architecturally clean but operationally mismatched to the target environment
- have a good stack fit but weak maintainability

Use the sections together, not in isolation.

## Example: full report

```json
{
  "summary": {
    "overall_score": 7.3,
    "consistency_score": 7.8,
    "maintainability_index": 64.4,
    "semantic_score": 6.2,
    "stack_fit_score": 7.1,
    "recommendation": "adopt"
  },
  "architecture": {
    "detected_pattern": "layered",
    "confidence": 0.8
  },
  "semantic": {
    "semantic_score": 6.2,
    "dimensions": {
      "domain_centralization": 7.5,
      "invariant_visibility": 5.0,
      "contract_explicitness": 8.0,
      "boundary_discipline": 6.5,
      "naming_coherence": 6.0
    }
  },
  "stack": {
    "environment_target": "local_dev",
    "stack_fit_score": 7.1,
    "scenario_fit": {
      "label": "compatible"
    }
  }
}
```

## Practical use cases

### Compare alternatives
Use the evaluator across several repositories, then compare:
- overall score
- semantic score
- stack fit score
- risks and tradeoffs

### Audit inheritance risk
Use it to identify:
- diffuse business logic
- poor boundary discipline
- hidden operational complexity
- maintainability hotspots

### Evaluate stack suitability
Use `stack_eval.py` when the main question is:
- is this stack viable for local use?
- is it too operationally heavy?
- does it look k8s-ready?
- does it show observability and deployability signals?

## Limitations

- static only
- heuristic semantic layer
- approximate maintainability math
- manifest/text-based stack detection
- not a replacement for targeted deep review of core domain flows

## Version

2.0.0 - April 2026
