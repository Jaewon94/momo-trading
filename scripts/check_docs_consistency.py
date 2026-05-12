#!/usr/bin/env python3
"""Run lightweight documentation and harness consistency checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "AGENTS.md",
    ".agent/README.md",
    ".agent/project-card.md",
    ".agent/security-policy.md",
    ".agent/tasks/README.md",
    "docs/workflows/code-commit-harness.md",
    "docs/workflows/hellforge-gap-audit.md",
    ".agent/domain-packs/trading-system/README.md",
    ".agent/templates/council-report.md",
    ".agent/templates/handoff.md",
    ".agent/templates/incident.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/trading_change.md",
    "scripts/check_task_harness.py",
    "scripts/task_harness.py",
    "scripts/change_harness.py",
    "scripts/guard_git_command.py",
    "scripts/check_markdown_links.py",
    "scripts/check_docs_consistency.py",
)
REQUIRED_TEXT = {
    "AGENTS.md": ("Harness Workflow", "Verification", "Safety Boundaries"),
    ".agent/security-policy.md": ("Trading Safety", "Ask first"),
    ".agent/security-policy.md": ("Trading Safety", "Ask first", "LLM And Untrusted Context"),
    "docs/workflows/code-commit-harness.md": ("Pre-Edit", "Pre-Commit", "Commit Approval"),
    "docs/workflows/hellforge-gap-audit.md": ("Applied", "Reviewed And Deferred", "Conclusion"),
    ".agent/domain-packs/trading-system/README.md": ("Risk Rules", "Required Reviewers", "Verification Matrix", "LLM Context Guardrails"),
    ".github/PULL_REQUEST_TEMPLATE.md": ("Risk / Approval", "Trading Safety"),
}


def check_docs(root: Path) -> list[str]:
    findings: list[str] = []
    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            findings.append(f"{rel_path}: required harness file is missing")

    for rel_path, required_terms in REQUIRED_TEXT.items():
        path = root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for term in required_terms:
            if term not in text:
                findings.append(f"{rel_path}: missing required section/text: {term}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    findings = check_docs(args.root.resolve())
    if findings:
        for finding in findings:
            print(finding, file=sys.stderr)
        return 1
    print("documentation consistency checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
