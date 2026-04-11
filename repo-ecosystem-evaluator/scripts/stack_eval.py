#!/usr/bin/env python3
"""Focused stack evaluation wrapper for repo-ecosystem-evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repo_eval import RepoEvaluator


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate repository stack fit and operational profile")
    parser.add_argument("repo", help="Local repository path")
    parser.add_argument("--env", default="undefined", choices=["cloud_serverless", "edge_device", "local_dev", "enterprise_k8s", "undefined"])
    parser.add_argument("--format", default="json", choices=["json", "markdown"])
    args = parser.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        print(json.dumps({"error": f"Path not found: {repo}"}))
        return 2

    report = RepoEvaluator(repo, env=args.env).run()["stack"]
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report, repo))
    return 0


def render_markdown(report: dict, repo: Path) -> str:
    return "\n".join([
        f"# Stack Evaluation: {repo.name}",
        "",
        f"- Environment target: **{report['environment_target']}**",
        f"- Stack fit score: **{report['stack_fit_score']}/10**",
        f"- Scenario fit: **{report['scenario_fit']['label']}**",
        f"- Deployability: **{report['deployability']}**",
        f"- Portability: **{report['portability']}**",
        f"- Observability: **{report['observability']}**",
        f"- Local dev friction: **{report['local_dev_friction']}**",
        f"- Frameworks: {', '.join(report['stack']['frameworks']) or 'none detected'}",
        f"- Datastores: {', '.join(report['stack']['datastores']) or 'none detected'}",
        f"- Infra: {', '.join(report['stack']['infra']) or 'none detected'}",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
