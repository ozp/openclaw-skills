# Heuristics Guide for Repository Evaluation v2

## Overview

This evaluator uses a hybrid scoring model with three major lenses:

1. **Structure / architecture**
2. **Semantic design coherence**
3. **Stack fit / operational suitability**

It is grounded in static evidence and aligned, where practical, with:
- ISO/IEC 25010 quality dimensions
- ATAM-style scenario reasoning
- Maintainability Index style scoring
- Martin-style dependency metrics

---

## 1. Core Metrics

### 1.1 Maintainability Index (proxy)

Used as a standardized maintainability signal.

Approximation inputs:
- LOC
- comment ratio
- cyclomatic proxy
- estimated Halstead volume proxy

Interpretation:

| MI | Interpretation |
|----|----------------|
| 80-100 | Strong maintainability signals |
| 60-79 | Good / workable |
| 40-59 | Moderate debt likely |
| <40 | High maintenance risk |

### 1.2 Dependency Metrics

| Metric | Meaning |
|--------|---------|
| Fan-in (`Ca`) | How many modules depend on this module |
| Fan-out (`Ce`) | How many modules this module depends on |
| Instability (`I = Ce / (Ca + Ce)`) | Outgoing dependency pressure |
| Cycles | Potential circular dependency chains |

### 1.3 Coupling / Cohesion Signals

- files with many cross-concern references
- large files with many complexity tokens
- modules with both high fan-in and high fan-out
- layer-crossing imports

---

## 2. Quality Dimensions

### 2.1 Architectural Conformance

Positive signals:
- clear layers
- unidirectional dependencies
- low cycle count
- domain not importing UI/adapters directly

Negative signals:
- circular dependencies
- mixed responsibilities
- cross-layer leakage
- unstable core modules

### 2.2 Error Handling

Positive signals:
- explicit exceptions / result handling
- visible guards and validation
- low silent error count

Negative signals:
- empty catch blocks
- broad exception swallowing
- implicit fallback without explicit handling

### 2.3 State Management

Positive signals:
- local/context-bounded state
- dependency injection instead of hidden singletons
- explicit persistence boundaries

Negative signals:
- global mutable state
- singleton-heavy coordination
- shared state with no visible guard

### 2.4 Testability

Positive signals:
- injection points
- pure-function ratio
- contract types / schemas
- low side-effect density

Negative signals:
- direct hardcoded external calls everywhere
- hidden state and construction logic
- no visible seams for mocking

---

## 3. Semantic Layer

The semantic layer is a **qualitative-static** layer. It tries to recover software meaning from symbols, contracts, guard clauses, and boundary placement.

### 3.1 Semantic Dimensions

#### Domain Centralization
Are use cases and business rules concentrated in domain/service/usecase/application layers?

**High score:** domain rules mostly live away from controllers/routes.

**Low score:** important rules appear mostly in adapters/controllers.

#### Invariant Visibility
Are business constraints visible in code?

Examples:
- assertions
- explicit validation functions
- guard clauses
- rejected invalid states

**High score:** invariants are explicit and repeated where needed.

**Low score:** rules appear implicit or absent.

#### Contract Explicitness
Are boundaries typed and validated?

Signals:
- DTOs
- schemas
- serializers
- validators
- typed request/response contracts

#### Boundary Discipline
Do adapters orchestrate, or do they own business rules?

**Penalty:** controllers/routes/handlers contain significant validation and business branching.

#### Naming Coherence
Can intent be reconstructed from names?

Signals:
- meaningful entities
- explicit use-case verbs
- bounded domain vocabulary

### 3.2 Semantic Risks

Typical semantic risk outputs:
- business rules in adapters
- no explicit invariants detected
- no explicit contracts detected
- flows fragmented across unrelated modules
- terminology drift across entities and handlers

---

## 4. Stack Evaluation

The stack evaluator answers a different question than architecture quality:

> Even if the code is decent, is this stack a good fit for the target environment?

### 4.1 Stack dimensions

#### Deployability
- packaging/tooling present
- clear runtime assumptions
- infrastructure manageable for the target

#### Portability
- Docker/supporting setup
- documented installation
- low environment lock-in signals

#### Observability
- health checks
- metrics
- tracing
- error monitoring

#### Local Dev Friction
- count of required services
- infra complexity
- lack of local defaults / README support

#### Operational Surface
- number of infra technologies
- datastore count
- framework count
- required platform moving parts

### 4.2 Environment fit labels

| Label | Meaning |
|-------|---------|
| compatible | Good fit, no major structural blockers |
| partial | Viable with tradeoffs or setup burden |
| blocked | Fundamental mismatch for the requested environment |

---

## 5. ATAM-lite

The evaluator includes a light scenario-based framing inspired by ATAM.

It does **not** run a full stakeholder workshop. Instead, it frames likely quality-attribute tradeoffs such as:
- maintainability vs operational complexity
- portability vs platform specialization
- local simplicity vs enterprise observability
- serverless fit vs stateful dependencies

This is useful for decision support, not formal architecture certification.

---

## 6. Recommendation Policy

### adopt
- overall score >= 7
- no major blockers
- semantic and stack sections do not reveal structural contradictions

### evaluate
- overall score 4-6.9
- repo may be viable but has meaningful debt, tradeoffs, or uncertainty

### avoid
- overall score < 4
- serious maintainability, semantic, or stack-fit issues

---

## 7. Confidence and Limits

Confidence must be reduced when:
- coverage is low
- stack manifests are missing
- naming is too generic to infer flows
- language parsing is weak for the target codebase

This evaluator is best used for:
- broad screening
- candidate comparison
- architecture triage
- targeted follow-up review planning

It is not a substitute for:
- runtime validation
- benchmark testing
- security audit tooling
- formal verification
