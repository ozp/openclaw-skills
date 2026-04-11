#!/usr/bin/env python3
"""Repository Ecosystem Evaluator

Static + semantic-lite repository evaluation with standardized metrics.
No third-party dependencies required.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

CODE_EXTS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
    "vendor",
    "target",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "generated",
    "proto",
}

LAYER_HINTS = [
    "api",
    "app",
    "controllers",
    "routes",
    "handlers",
    "services",
    "usecases",
    "domain",
    "models",
    "entities",
    "repositories",
    "infra",
    "infrastructure",
    "adapters",
    "core",
]

SEMANTIC_RULE_PATTERNS = [
    r"assert\s+.+",
    r"raise\s+(?!SystemExit).+",
    r"throw\s+.+",
    r"return\s+.*error",
    r"validate[A-Za-z0-9_]*\(",
    r"guard[A-Za-z0-9_]*\(",
    r"if\s+.*\b(nil|null|None|undefined|invalid|expired|unauthorized|forbidden|empty)\b",
]

USECASE_HINTS = [
    "create",
    "update",
    "delete",
    "list",
    "get",
    "fetch",
    "load",
    "save",
    "approve",
    "reject",
    "assign",
    "sync",
    "process",
    "route",
    "classify",
    "import",
    "export",
]

ENTITY_PATTERNS = [
    re.compile(r"class\s+([A-Z][A-Za-z0-9]+)(Entity|Model|Aggregate|DTO|Schema)\b"),
    re.compile(r"type\s+([A-Z][A-Za-z0-9]+)(DTO|Schema|Model)\b"),
    re.compile(r"interface\s+([A-Z][A-Za-z0-9]+)(DTO|Schema|Model)\b"),
    re.compile(r"struct\s+([A-Z][A-Za-z0-9]+)\b"),
]

@dataclass
class SourceRef:
    file: str
    line: int | None = None
    snippet: str | None = None
    confidence: float | None = None


class RepoEvaluator:
    def __init__(self, repo: Path, env: str = "undefined"):
        self.repo = repo.resolve()
        self.env = env
        self.files: list[Path] = []
        self.by_lang: Counter[str] = Counter()
        self.imports: dict[str, set[str]] = defaultdict(set)
        self.reverse_imports: dict[str, set[str]] = defaultdict(set)
        self.sources: list[SourceRef] = []
        self.readme_text = ""
        self.manifests: dict[str, dict] = {}

    def run(self) -> dict:
        self.files = list(self.iter_code_files())
        self.load_readme()
        self.parse_manifests()

        structure = self.structure_metrics()
        deps = self.dependency_metrics()
        quality = self.quality_metrics(structure, deps)
        semantic = self.semantic_metrics()
        stack = self.stack_metrics(structure)
        risk = self.risk_metrics(quality, semantic, stack)
        summary = self.summary_metrics(quality, semantic, stack, risk)
        arch = self.architecture_metrics(structure, deps)

        return {
            "$schema": "repo-evaluation-v2.0",
            "repository": {
                "path": str(self.repo),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "commit_hash": self.git_commit_hash(),
            },
            "summary": summary,
            "architecture": arch,
            "quality": quality,
            "semantic": semantic,
            "stack": stack,
            "risks": risk,
            "evidence": {
                "coverage_pct": round(self.coverage_pct(), 1),
                "sources": [asdict(s) for s in self.sources[:80]],
            },
        }

    def iter_code_files(self) -> Iterable[Path]:
        for root, dirs, files in os.walk(self.repo):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for name in files:
                path = Path(root) / name
                lang = CODE_EXTS.get(path.suffix.lower())
                if lang:
                    self.by_lang[lang] += 1
                    yield path

    def load_readme(self) -> None:
        for name in ["README.md", "readme.md", "README.txt"]:
            p = self.repo / name
            if p.exists():
                self.readme_text = safe_read(p)
                self.sources.append(SourceRef(file=str(p.relative_to(self.repo)), line=1, snippet="README detected", confidence=1.0))
                return

    def parse_manifests(self) -> None:
        manifest_names = ["package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "pom.xml", "docker-compose.yml", "docker-compose.yaml", "Dockerfile"]
        for name in manifest_names:
            p = self.repo / name
            if p.exists():
                text = safe_read(p)
                self.manifests[name] = {"exists": True, "preview": text[:3000]}
                self.sources.append(SourceRef(file=str(p.relative_to(self.repo)), line=1, snippet=f"manifest:{name}", confidence=1.0))

    def structure_metrics(self) -> dict:
        rel_files = [str(f.relative_to(self.repo)) for f in self.files]
        top_dirs = Counter()
        layers = []
        for rf in rel_files:
            parts = rf.split("/")
            if len(parts) > 1:
                top_dirs[parts[0]] += 1
                if parts[0] in LAYER_HINTS and parts[0] not in layers:
                    layers.append(parts[0])
        entry_points = [rf for rf in rel_files if re.search(r"(^|/)(main|index|app|server)\.(py|js|ts|go|rs|java)$", rf)]
        return {
            "total_code_files": len(rel_files),
            "languages": dict(self.by_lang),
            "entry_points": entry_points[:20],
            "top_directories": top_dirs.most_common(20),
            "layers_detected": layers,
        }

    def dependency_metrics(self) -> dict:
        for path in self.files:
            rel = str(path.relative_to(self.repo))
            text = safe_read(path)
            for line_no, line in enumerate(text.splitlines(), start=1):
                targets = extract_imports(line, path.suffix.lower())
                for tgt in targets:
                    self.imports[rel].add(tgt)
                    self.reverse_imports[tgt].add(rel)
                    if len(self.sources) < 80:
                        self.sources.append(SourceRef(file=rel, line=line_no, snippet=line.strip()[:160], confidence=0.75))
        fan_out = {k: len(v) for k, v in self.imports.items()}
        fan_in = Counter()
        for _, tgts in self.imports.items():
            for tgt in tgts:
                fan_in[tgt] += 1
        cycles = self.detect_cycles(limit=20)
        instability = {}
        for module in set(fan_in) | set(fan_out):
            ca = fan_in.get(module, 0)
            ce = fan_out.get(module, 0)
            instability[module] = round(ce / (ca + ce), 3) if (ca + ce) else 0.0
        return {
            "fan_in": fan_in.most_common(20),
            "fan_out": sorted(fan_out.items(), key=lambda kv: kv[1], reverse=True)[:20],
            "cycles": cycles,
            "instability": sorted(instability.items(), key=lambda kv: kv[1], reverse=True)[:20],
        }

    def quality_metrics(self, structure: dict, deps: dict) -> dict:
        loc = 0
        comment = 0
        complexity_tokens = 0
        async_functions = 0
        guarded_async = 0
        try_blocks = 0
        silent_errors = 0
        global_state_hits = []
        pureish_functions = 0
        total_functions = 0
        injection_points = 0
        god_objects = []

        for path in self.files:
            rel = str(path.relative_to(self.repo))
            text = safe_read(path)
            lines = text.splitlines()
            loc += sum(1 for l in lines if l.strip())
            comment += sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*", "--")))
            complexity_tokens += sum(len(re.findall(r"\b(if|elif|else if|for|while|case|catch|except|switch|&&|\|\|)\b", l)) for l in lines)
            try_blocks += sum(1 for l in lines if re.search(r"\b(try|except|catch)\b", l))
            silent_errors += sum(1 for l in lines if re.search(r"except\s*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\}|except\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*pass", l))
            async_functions += sum(1 for l in lines if re.search(r"\basync\b|Promise<|Future<|CompletableFuture", l))
            guarded_async += sum(1 for l in lines if re.search(r"\bawait\b|\.then\(|async ", l) and re.search(r"\btry\b|catch|except", text))
            total_functions += sum(1 for l in lines if re.search(r"\bdef\b|\bfunction\b|=>|\bfunc\b|\bfn\b|\bpublic\b.+\(|\bprivate\b.+\(", l))
            pureish_functions += sum(1 for l in lines if re.search(r"\bdef\b|\bfunction\b|\bfunc\b|\bfn\b", l))
            injection_points += sum(1 for l in lines if re.search(r"constructor\([^)]*[A-Za-z][^)]*\)|__init__\([^)]*,\s*[A-Za-z_][A-Za-z0-9_]*\)|new\s+[A-Za-z]+\([^)]*config|interface\s+[A-Za-z]+", l))
            if len(lines) > 500 and complexity_tokens > 40:
                god_objects.append(rel)
            for i, l in enumerate(lines, start=1):
                if re.search(r"^(global\s+|let\s+[a-zA-Z_].*=|var\s+[a-zA-Z_].*=|static\s+[A-Za-z_].*=)", l.strip()):
                    global_state_hits.append({"file": rel, "line": i, "snippet": l.strip()[:160]})

        comment_ratio = (comment / loc) if loc else 0.0
        avg_complexity = complexity_tokens / max(len(self.files), 1)
        cyclomatic_proxy = max(1.0, complexity_tokens / max(total_functions, 1))
        halstead_volume_proxy = max(1.0, loc * 0.9)
        mi = max(0.0, min(100.0, 171 - 5.2 * math.log(halstead_volume_proxy) - 0.23 * cyclomatic_proxy - 16.2 * math.log(max(loc, 1)) + 50 * math.sin(math.sqrt(2.4 * min(comment_ratio * 100, 100)))))
        mi = round(mi * 100 / 171, 1)

        arch_score = self.arch_conformance_score(structure, deps)
        error_score = clamp((try_blocks * 1.2) - (silent_errors * 2), 0, 10)
        state_score = clamp(10 - min(len(global_state_hits), 8), 0, 10)
        coupling_score = clamp(10 - len(deps["cycles"]) - len(god_objects), 0, 10)
        testability_score = clamp((injection_points / max(total_functions, 1)) * 40 + (pureish_functions / max(total_functions, 1)) * 6, 0, 10)
        consistency_score = round(arch_score * 0.25 + error_score * 0.20 + state_score * 0.15 + coupling_score * 0.25 + testability_score * 0.15, 2)

        return {
            "maintainability_index": mi,
            "comment_ratio": round(comment_ratio, 3),
            "cyclomatic_proxy": round(cyclomatic_proxy, 2),
            "architectural_conformance_score": round(arch_score, 2),
            "consistency_score": consistency_score,
            "error_handling": {
                "strategy": self.error_strategy(try_blocks, silent_errors),
                "coverage_pct": round(min(100.0, (guarded_async / max(async_functions, 1)) * 100), 1),
                "silent_error_count": silent_errors,
                "logging_consistency": "unknown",
            },
            "state_management": {
                "scope_pattern": self.state_scope_pattern(global_state_hits),
                "mutation_strategy": "mixed",
                "global_state_hits": global_state_hits[:20],
            },
            "coupling_cohesion": {
                "coupling_score": round(coupling_score, 2),
                "cohesion_score": round(max(0.0, 10 - len(god_objects) * 1.5), 2),
                "god_objects": god_objects[:20],
                "spaghetti_risk": risk_bucket(len(deps["cycles"]) + len(god_objects), low=1, medium=4),
            },
            "testability": {
                "score": round(testability_score, 2),
                "pure_function_ratio": round(pureish_functions / max(total_functions, 1), 3),
                "injection_points": injection_points,
                "mockability": mockability_label(injection_points, total_functions),
            },
            "iso_25010_alignment": {
                "maintainability": round((mi / 10), 2),
                "reliability_signals": round(error_score, 2),
                "portability_signals": round(self.portability_signals(), 2),
                "compatibility_signals": round(self.compatibility_signals(), 2),
                "security_signals": round(self.security_signals(), 2),
            },
        }

    def semantic_metrics(self) -> dict:
        entities = []
        usecases = []
        invariants = []
        contracts = []
        adapters_with_rules = []

        for path in self.files:
            rel = str(path.relative_to(self.repo))
            text = safe_read(path)
            lines = text.splitlines()
            for rx in ENTITY_PATTERNS:
                for m in rx.finditer(text):
                    entities.append({"name": ''.join(g for g in m.groups() if g), "file": rel})
            for i, line in enumerate(lines, start=1):
                if re.search(r"^(\s*)(def|function|func|fn|class)\s+", line):
                    name_match = re.search(r"^(?:\s*)(?:def|function|func|fn|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                    symbol_name = name_match.group(1) if name_match else ""
                    if any(re.search(rf"\b{hint}[A-Za-z0-9_]*\b", symbol_name, re.I) for hint in USECASE_HINTS):
                        usecases.append({"file": rel, "line": i, "snippet": line.strip()[:160]})
                if any(re.search(pat, line) for pat in SEMANTIC_RULE_PATTERNS):
                    invariants.append({"file": rel, "line": i, "snippet": line.strip()[:180]})
                if re.search(r"(DTO|Schema|Serializer|validator|zod|pydantic|marshmallow|Joi|Yup)", line):
                    contracts.append({"file": rel, "line": i, "snippet": line.strip()[:160]})
                if re.search(r"(controller|route|handler)", rel, re.I) and any(re.search(pat, line) for pat in SEMANTIC_RULE_PATTERNS):
                    adapters_with_rules.append({"file": rel, "line": i, "snippet": line.strip()[:180]})

        domain_centers = [u for u in usecases if re.search(r"(domain|service|usecase|application|core)", u["file"], re.I)]
        adapter_centers = [u for u in usecases if re.search(r"(controller|route|handler|api|view)", u["file"], re.I)]
        domain_centralization = round(min(10.0, (len(domain_centers) / max(len(usecases), 1)) * 10), 2)
        invariant_visibility = round(min(10.0, (len(invariants) / max(len(usecases), 1)) * 3), 2)
        contract_explicitness = round(min(10.0, (len(contracts) / max(len(usecases), 1)) * 5), 2)
        boundary_discipline = round(max(0.0, 10 - len(adapters_with_rules) * 1.5), 2)
        naming_coherence = round(min(10.0, (len(entities) + len(usecases)) / max(len(self.files), 1) * 6), 2)
        semantic_score = round((domain_centralization * 0.30 + invariant_visibility * 0.20 + contract_explicitness * 0.20 + boundary_discipline * 0.20 + naming_coherence * 0.10), 2)

        critical_flows = self.infer_critical_flows(usecases)

        return {
            "semantic_score": semantic_score,
            "method": "semantic-static-v1",
            "dimensions": {
                "domain_centralization": domain_centralization,
                "invariant_visibility": invariant_visibility,
                "contract_explicitness": contract_explicitness,
                "boundary_discipline": boundary_discipline,
                "naming_coherence": naming_coherence,
            },
            "entities": entities[:30],
            "use_cases": usecases[:40],
            "invariants": invariants[:40],
            "contracts": contracts[:40],
            "critical_flows": critical_flows,
            "semantic_risks": self.semantic_risks(adapters_with_rules, invariants, contracts),
        }

    def stack_metrics(self, structure: dict) -> dict:
        components = self.detect_stack_components()
        scenario_fit = self.environment_fit(components)
        operational_surface = min(10.0, len(components["infra"]) + len(components["datastores"]) + len(components["frameworks"]))
        local_dev_friction = self.local_dev_friction(components)
        deployability = clamp(10 - local_dev_friction + (2 if components["packaging"] else 0), 0, 10)
        portability = clamp(self.portability_signals(), 0, 10)
        observability = clamp(2 * len(components["observability"]) + (2 if any("health" in x.lower() for x in components["frameworks"] + components["infra"]) else 0), 0, 10)
        stack_fit_score = round((deployability * 0.25 + portability * 0.20 + observability * 0.15 + scenario_fit["score"] * 0.25 + clamp(10 - operational_surface, 0, 10) * 0.15), 2)
        atam_lite = self.atam_lite(components)
        return {
            "stack": components,
            "environment_target": self.env,
            "scenario_fit": scenario_fit,
            "operational_surface": round(operational_surface, 2),
            "local_dev_friction": round(local_dev_friction, 2),
            "deployability": round(deployability, 2),
            "portability": round(portability, 2),
            "observability": round(observability, 2),
            "stack_fit_score": stack_fit_score,
            "atam_lite": atam_lite,
            "structure_languages": structure["languages"],
        }

    def risk_metrics(self, quality: dict, semantic: dict, stack: dict) -> dict:
        logic_defects = []
        if quality["state_management"]["scope_pattern"] == "global":
            logic_defects.append({"type": "race_condition", "severity": "high", "likelihood": "medium", "evidence": [hit["file"] + ":" + str(hit["line"]) for hit in quality["state_management"]["global_state_hits"][:5]]})
        if quality["error_handling"]["silent_error_count"]:
            logic_defects.append({"type": "unhandled_edge_case", "severity": "medium", "likelihood": "high", "evidence": ["silent error handlers detected"]})
        if semantic["semantic_risks"]:
            logic_defects.extend({"type": "semantic_drift", "severity": "medium", "likelihood": "medium", "evidence": [r]} for r in semantic["semantic_risks"][:5])
        operational = []
        if stack["local_dev_friction"] >= 7:
            operational.append("High local development friction due to multiple required services or missing local defaults")
        if stack["operational_surface"] >= 7:
            operational.append("Operational surface area is high; platform complexity may dominate feature work")
        maintenance = []
        if quality["maintainability_index"] < 45:
            maintenance.append("Maintainability index is low; refactoring backlog likely required")
        if semantic["semantic_score"] < 5:
            maintenance.append("Semantic design coherence is weak; domain rules may be diffuse or implicit")
        return {"logic_defects": logic_defects, "operational": operational, "maintenance": maintenance}

    def summary_metrics(self, quality: dict, semantic: dict, stack: dict, risk: dict) -> dict:
        overall = round(quality["consistency_score"] * 0.45 + (quality["maintainability_index"] / 10) * 0.20 + semantic["semantic_score"] * 0.20 + stack["stack_fit_score"] * 0.15, 2)
        blockers = len(risk["operational"]) + len([r for r in risk["logic_defects"] if r["severity"] in {"high", "critical"}])
        if overall >= 7 and blockers == 0:
            rec = "adopt"
        elif overall >= 4:
            rec = "evaluate"
        else:
            rec = "avoid"
        return {
            "overall_score": overall,
            "consistency_score": quality["consistency_score"],
            "maintainability_index": quality["maintainability_index"],
            "semantic_score": semantic["semantic_score"],
            "stack_fit_score": stack["stack_fit_score"],
            "recommendation": rec,
        }

    def architecture_metrics(self, structure: dict, deps: dict) -> dict:
        layers = structure["layers_detected"]
        pattern = "indeterminate"
        if any(x in layers for x in ["controllers", "services", "repositories"]):
            pattern = "layered"
        elif any(x in layers for x in ["adapters", "domain"]):
            pattern = "hexagonal"
        elif len([d for d, _ in structure["top_directories"] if re.search(r"service", d)]) >= 2:
            pattern = "microservices"
        elif len(structure["entry_points"]) <= 2 and len(structure["languages"]) <= 2:
            pattern = "monolith"
        confidence = round(min(1.0, (len(layers) / 5) + (0.1 if not deps["cycles"] else 0)), 2)
        violations = [{"type": "cycle", "location": " -> ".join(c), "description": "Potential circular dependency"} for c in deps["cycles"][:10]]
        return {"detected_pattern": pattern, "confidence": confidence, "layers_detected": layers, "violations": violations}

    def detect_cycles(self, limit: int = 20) -> list[list[str]]:
        graph = {k: set(v) for k, v in self.imports.items()}
        visited = set()
        stack = []
        on_stack = set()
        cycles = []

        def dfs(node: str):
            if len(cycles) >= limit:
                return
            visited.add(node)
            stack.append(node)
            on_stack.add(node)
            for nxt in graph.get(node, set()):
                if nxt not in graph:
                    continue
                if nxt not in visited:
                    dfs(nxt)
                elif nxt in on_stack:
                    idx = stack.index(nxt)
                    cycle = stack[idx:] + [nxt]
                    if cycle not in cycles:
                        cycles.append(cycle)
            stack.pop()
            on_stack.remove(node)

        for node in list(graph):
            if node not in visited:
                dfs(node)
            if len(cycles) >= limit:
                break
        return cycles

    def infer_critical_flows(self, usecases: list[dict]) -> list[dict]:
        flows = []
        grouped = defaultdict(list)
        for uc in usecases:
            stem = re.sub(r"[^a-z]", "", uc["snippet"].lower())
            for hint in USECASE_HINTS:
                if hint in stem:
                    grouped[hint].append(uc)
        for hint, items in grouped.items():
            if len(items) >= 2:
                flows.append({
                    "name": hint,
                    "touchpoints": items[:6],
                    "assessment": "multi-layer-flow-detected" if len({segment(i['file']) for i in items}) >= 2 else "single-layer-flow",
                })
        return flows[:20]

    def semantic_risks(self, adapters_with_rules: list[dict], invariants: list[dict], contracts: list[dict]) -> list[str]:
        risks = []
        if len(adapters_with_rules) >= 5:
            risks.append("Business rules appear in adapter/controller layers")
        if len(invariants) == 0:
            risks.append("No explicit invariants or guards detected in analyzed files")
        if len(contracts) == 0:
            risks.append("No explicit DTO/schema/validator contracts detected")
        return risks

    def detect_stack_components(self) -> dict:
        frameworks, datastores, infra, packaging, observability = set(), set(), set(), set(), set()
        text = "\n".join(m.get("preview", "") for m in self.manifests.values()) + "\n" + self.readme_text[:4000]
        rules = [
            (frameworks, ["react", "vue", "angular", "next", "nuxt", "express", "fastapi", "django", "flask", "spring", "gin", "echo", "actix", "axum"]),
            (datastores, ["postgres", "mysql", "sqlite", "mongodb", "redis", "elasticsearch", "supabase"]),
            (infra, ["docker", "kubernetes", "terraform", "ansible", "helm", "nginx"]),
            (packaging, ["npm", "pnpm", "yarn", "poetry", "pip", "cargo", "maven", "gradle", "go mod"]),
            (observability, ["opentelemetry", "prometheus", "grafana", "sentry", "health", "metrics", "tracing"]),
        ]
        for bucket, patterns in rules:
            for pat in patterns:
                rx = rf"(?<![A-Za-z0-9_]){re.escape(pat.lower())}(?![A-Za-z0-9_])"
                if re.search(rx, text.lower()):
                    bucket.add(pat)
        return {
            "frameworks": sorted(frameworks),
            "datastores": sorted(datastores),
            "infra": sorted(infra),
            "packaging": sorted(packaging),
            "observability": sorted(observability),
        }

    def environment_fit(self, components: dict) -> dict:
        compat, incompat = [], []
        score = 5.0
        if self.env == "local_dev":
            if "sqlite" in components["datastores"]:
                compat.append("Local-friendly datastore option detected (SQLite)")
                score += 2
            if len(components["infra"]) > 2:
                incompat.append("Several infra dependencies increase local setup friction")
                score -= 2
        elif self.env == "enterprise_k8s":
            if "kubernetes" in components["infra"] or "helm" in components["infra"]:
                compat.append("Kubernetes-oriented infrastructure detected")
                score += 2
            if not components["observability"]:
                incompat.append("Weak observability signals for enterprise operation")
                score -= 2
        elif self.env == "cloud_serverless":
            if any(db in components["datastores"] for db in ["postgres", "mysql"]):
                incompat.append("Stateful datastore dependencies may complicate serverless fit")
                score -= 1.5
        elif self.env == "edge_device":
            if len(components["frameworks"]) > 2 or len(components["datastores"]) > 1:
                incompat.append("Stack may be too heavy for edge profile")
                score -= 2
        return {
            "compatible": compat,
            "incompatible": incompat,
            "score": round(clamp(score, 0, 10), 2),
            "label": fit_label(score),
        }

    def atam_lite(self, components: dict) -> dict:
        scenarios = []
        if self.env == "enterprise_k8s":
            scenarios.append({"quality_attribute": "availability", "sensitivity_points": ["health endpoints", "graceful shutdown", "DB dependency"]})
            scenarios.append({"quality_attribute": "observability", "sensitivity_points": components["observability"] or ["No explicit telemetry detected"]})
        elif self.env == "local_dev":
            scenarios.append({"quality_attribute": "modifiability", "sensitivity_points": ["README/setup clarity", "optional infra", "SQLite/local defaults"]})
        else:
            scenarios.append({"quality_attribute": "maintainability", "sensitivity_points": ["module boundaries", "testability", "dependency complexity"]})
        return {"method": "ATAM-lite", "scenarios": scenarios}

    def portability_signals(self) -> float:
        score = 5.0
        if self.manifests.get("Dockerfile"):
            score += 2
        if any(name in self.manifests for name in ["docker-compose.yml", "docker-compose.yaml"]):
            score += 1
        if self.readme_text and re.search(r"(install|setup|quick start|getting started)", self.readme_text, re.I):
            score += 1
        return clamp(score, 0, 10)

    def compatibility_signals(self) -> float:
        score = 3.0
        if len(self.by_lang) >= 2:
            score += 2
        if any(x in self.manifests for x in ["package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml"]):
            score += 2
        return clamp(score, 0, 10)

    def security_signals(self) -> float:
        score = 3.0
        text = "\n".join(m.get("preview", "") for m in self.manifests.values()) + self.readme_text[:4000]
        if re.search(r"(auth|oauth|jwt|rbac|permission|csrf|helmet|security)", text, re.I):
            score += 3
        if re.search(r"(sentry|audit|logging)", text, re.I):
            score += 1
        return clamp(score, 0, 10)

    def local_dev_friction(self, components: dict) -> float:
        friction = 2.0
        friction += len(components["datastores"]) * 1.5
        friction += max(0, len(components["infra"]) - 1)
        if not self.readme_text:
            friction += 2
        return clamp(friction, 0, 10)

    def arch_conformance_score(self, structure: dict, deps: dict) -> float:
        score = 5.0
        layers = structure["layers_detected"]
        if len(layers) >= 3:
            score += 2
        if not deps["cycles"]:
            score += 2
        else:
            score -= min(4, len(deps["cycles"]))
        return clamp(score, 0, 10)

    def coverage_pct(self) -> float:
        total = len(self.files)
        return 100.0 if total else 0.0

    def git_commit_hash(self) -> str | None:
        try:
            out = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
            return out
        except Exception:
            return None

    def error_strategy(self, try_blocks: int, silent_errors: int) -> str:
        if try_blocks == 0:
            return "minimal"
        if silent_errors:
            return "mixed"
        return "exceptions"

    def state_scope_pattern(self, global_state_hits: list[dict]) -> str:
        return "global" if global_state_hits else "local"


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def extract_imports(line: str, suffix: str) -> list[str]:
    targets = []
    if suffix == ".py":
        m = re.match(r"\s*from\s+([A-Za-z0-9_\.]+)\s+import\s+", line)
        if m:
            targets.append(m.group(1).replace(".", "/") + ".py")
        m = re.match(r"\s*import\s+([A-Za-z0-9_\.]+)", line)
        if m:
            targets.append(m.group(1).split(",")[0].replace(".", "/") + ".py")
    elif suffix in {".js", ".ts", ".jsx", ".tsx"}:
        for pat in [r"from\s+['\"]([^'\"]+)['\"]", r"require\(['\"]([^'\"]+)['\"]\)"]:
            m = re.search(pat, line)
            if m and m.group(1).startswith((".", "/")):
                targets.append(m.group(1))
    elif suffix == ".go":
        m = re.search(r'"([^"]+)"', line)
        if m:
            targets.append(m.group(1))
    elif suffix == ".rs":
        m = re.match(r"\s*use\s+([A-Za-z0-9_:]+)", line)
        if m:
            targets.append(m.group(1).replace("::", "/") + ".rs")
    elif suffix == ".java":
        m = re.match(r"\s*import\s+([A-Za-z0-9_\.]+)", line)
        if m:
            targets.append(m.group(1).replace(".", "/") + ".java")
    return targets


def segment(path: str) -> str:
    return path.split("/")[0]


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def risk_bucket(value: int, low: int, medium: int) -> str:
    if value <= low:
        return "low"
    if value <= medium:
        return "medium"
    return "high"


def mockability_label(injection_points: int, total_functions: int) -> str:
    ratio = injection_points / max(total_functions, 1)
    if ratio >= 0.2:
        return "high"
    if ratio >= 0.08:
        return "medium"
    return "low"


def fit_label(score: float) -> str:
    if score >= 7:
        return "compatible"
    if score >= 4:
        return "partial"
    return "blocked"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate repository structure, semantics, and stack fit")
    parser.add_argument("repo", help="Local repository path")
    parser.add_argument("--env", default="undefined", choices=["cloud_serverless", "edge_device", "local_dev", "enterprise_k8s", "undefined"])
    parser.add_argument("--format", default="json", choices=["json", "markdown"])
    args = parser.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        print(json.dumps({"error": f"Path not found: {repo}"}))
        return 2

    report = RepoEvaluator(repo, env=args.env).run()

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report))
    return 0


def render_markdown(report: dict) -> str:
    s = report["summary"]
    a = report["architecture"]
    q = report["quality"]
    sem = report["semantic"]
    st = report["stack"]
    lines = [
        f"# Repository Evaluation: {Path(report['repository']['path']).name}",
        "",
        f"- Overall score: **{s['overall_score']}/10**",
        f"- Recommendation: **{s['recommendation']}**",
        f"- Pattern: **{a['detected_pattern']}** (confidence {a['confidence']})",
        f"- Maintainability Index: **{q['maintainability_index']}**",
        f"- Semantic score: **{sem['semantic_score']}**",
        f"- Stack fit score: **{st['stack_fit_score']}**",
        "",
        "## Semantic highlights",
    ]
    for item in sem.get("semantic_risks", [])[:5]:
        lines.append(f"- Risk: {item}")
    for flow in sem.get("critical_flows", [])[:5]:
        lines.append(f"- Flow `{flow['name']}`: {flow['assessment']}")
    lines.extend([
        "",
        "## Stack",
        f"- Environment target: `{st['environment_target']}`",
        f"- Fit: **{st['scenario_fit']['label']}**",
        f"- Frameworks: {', '.join(st['stack']['frameworks']) or 'none detected'}",
        f"- Datastores: {', '.join(st['stack']['datastores']) or 'none detected'}",
        f"- Infra: {', '.join(st['stack']['infra']) or 'none detected'}",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
