#!/usr/bin/env python3
"""Classify changed files into risk, reviewer, and verification guidance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Rule:
    prefix: str
    risk: str
    reviewers: tuple[str, ...]
    checks: tuple[str, ...]
    reason: str


@dataclass
class ChangeClassification:
    risk: str
    reviewers: list[str]
    checks: list[str]
    reasons: list[str]
    protected: bool


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
RULES: tuple[Rule, ...] = (
    Rule("agent/", "high", ("trading-strategist", "qa-engineer", "code-reviewer"), ("tests/agent",), "trading decision logic"),
    Rule("strategy/", "high", ("trading-strategist", "risk-manager", "qa-engineer"), ("tests/strategy",), "risk or strategy logic"),
    Rule("trading/", "high", ("broker-integrator", "qa-engineer", "code-reviewer"), ("tests/trading",), "broker integration"),
    Rule("repositories/", "high", ("database-reviewer", "qa-engineer"), ("tests/repositories",), "persistence layer"),
    Rule("models/", "high", ("database-reviewer", "qa-engineer"), ("tests",), "data model"),
    Rule("alembic/", "high", ("database-reviewer", "release-manager"), ("migration review",), "database migration"),
    Rule("scheduler/", "medium", ("backend-engineer", "qa-engineer"), ("tests/scheduler",), "scheduled job"),
    Rule("services/", "medium", ("backend-engineer", "qa-engineer"), ("tests/services",), "business service"),
    Rule("api/", "medium", ("api-integrator", "qa-engineer"), ("tests/api",), "API contract"),
    Rule("admin/static/js/", "medium", ("frontend-engineer", "qa-engineer"), ("tests/frontend",), "admin UI state"),
    Rule("analysis/", "medium", ("llm-runtime-reviewer", "qa-engineer"), ("tests/analysis",), "analysis or LLM provider"),
    Rule("core/config.py", "high", ("security-reviewer", "release-manager"), ("config review",), "runtime config"),
    Rule(".env", "blocked", ("security-reviewer",), ("secret handling",), "secret file"),
    Rule(".github/", "high", ("release-manager", "security-reviewer"), ("CI review",), "CI/CD workflow"),
    Rule("scripts/", "medium", ("qa-engineer", "code-reviewer"), ("tests/scripts",), "developer tooling"),
    Rule("docs/", "low", ("documentation-steward",), ("markdown link check",), "documentation"),
    Rule(".agent/", "low", ("documentation-steward",), ("task harness check",), "agent harness artifact"),
)


def changed_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.rsplit(" -> ", 1)[1]
        paths.append(raw)
    return paths


def matching_rules(path: str) -> list[Rule]:
    return [rule for rule in RULES if path == rule.prefix or path.startswith(rule.prefix)]


def classify_paths(paths: list[str]) -> ChangeClassification:
    risk = "low"
    reviewers: set[str] = set()
    checks: set[str] = set()
    reasons: list[str] = []
    protected = False

    for path in paths:
        rules = matching_rules(path)
        if not rules:
            reviewers.add("code-reviewer")
            checks.add("focused tests")
            reasons.append(f"{path}: no specific rule, default code review")
            risk = max(risk, "medium", key=lambda item: RISK_ORDER[item])
            continue
        for rule in rules:
            risk = max(risk, rule.risk, key=lambda item: RISK_ORDER[item])
            reviewers.update(rule.reviewers)
            checks.update(rule.checks)
            reasons.append(f"{path}: {rule.reason} -> {rule.risk}")
            if rule.risk in {"high", "blocked"}:
                protected = True

    return ChangeClassification(
        risk=risk,
        reviewers=sorted(reviewers),
        checks=sorted(checks),
        reasons=reasons,
        protected=protected,
    )


def format_text(classification: ChangeClassification) -> str:
    lines = [
        f"risk: {classification.risk}",
        f"protected: {'yes' if classification.protected else 'no'}",
        "reviewers:",
    ]
    lines.extend(f"- {item}" for item in classification.reviewers or ["code-reviewer"])
    lines.append("checks:")
    lines.extend(f"- {item}" for item in classification.checks or ["focused tests"])
    lines.append("reasons:")
    lines.extend(f"- {item}" for item in classification.reasons or ["no changed files"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--enforce", action="store_true", help="Fail for blocked changes")
    parser.add_argument("paths", nargs="*", help="Paths to classify; defaults to git status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    paths = args.paths or changed_files(root)
    classification = classify_paths(paths)
    if args.json:
        print(json.dumps(asdict(classification), ensure_ascii=False, indent=2))
    else:
        print(format_text(classification))
    if args.enforce and classification.risk == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
