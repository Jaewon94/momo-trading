#!/usr/bin/env python3
"""Validate repo-local task harness artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TASK_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{3}-[a-z0-9][a-z0-9-]*$")
ALLOWED_STATUSES = {
    "created",
    "researching",
    "planning",
    "implementing",
    "testing",
    "reviewing",
    "reporting",
    "completed",
    "blocked",
    "cancelled",
    "failed",
}
TERMINAL_STATUSES = {"completed", "blocked", "cancelled", "failed"}
REQUIRED_TASK_FILES = (
    "brief.md",
    "state.json",
    "run-log.json",
    "test-plan.md",
    "decision-record.md",
    "quality-scorecard.md",
)
REQUIRED_BRIEF_SECTIONS = ("Research Gate", "Completion Criteria", "Verification Plan")
REQUIRED_TEST_PLAN_SECTIONS = ("Commands",)
REQUIRED_PROJECT_FILES = (".agent/project-card.md", ".agent/security-policy.md")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_tasks: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.checked_tasks += other.checked_tasks


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"__json_error__": str(exc)}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def task_dirs(root: Path) -> list[Path]:
    tasks_path = root / ".agent" / "tasks"
    if not tasks_path.exists():
        return []
    return sorted(path for path in tasks_path.iterdir() if path.is_dir() and not path.name.startswith("."))


def add_warning_or_error(result: ValidationResult, message: str, strict: bool) -> None:
    if strict:
        result.errors.append(message)
    else:
        result.warnings.append(message)


def validate_project_files(root: Path, strict: bool) -> ValidationResult:
    result = ValidationResult()
    for rel_path in REQUIRED_PROJECT_FILES:
        path = root / rel_path
        if not path.exists():
            add_warning_or_error(result, f"{rel_path}: missing project harness file", strict)
    return result


def validate_state(path: Path, task_id: str, final_report_exists: bool, result: ValidationResult) -> None:
    rel = path.as_posix()
    state = load_json(path)
    if not isinstance(state, dict):
        result.errors.append(f"{rel}: must be a JSON object")
        return
    if "__json_error__" in state:
        result.errors.append(f"{rel}: invalid JSON: {state['__json_error__']}")
        return
    if state.get("task_id") != task_id:
        result.errors.append(f"{rel}: task_id must match directory name")
    status = state.get("status")
    if status not in ALLOWED_STATUSES:
        result.errors.append(f"{rel}: status must be one of {sorted(ALLOWED_STATUSES)}")
    if not state.get("updated_at"):
        result.errors.append(f"{rel}: missing updated_at")
    if status in TERMINAL_STATUSES and not final_report_exists:
        result.errors.append(f"{rel}: terminal task requires final-report.md")


def validate_run_log(path: Path, task_id: str, result: ValidationResult) -> None:
    rel = path.as_posix()
    payload = load_json(path)
    if not isinstance(payload, dict):
        result.errors.append(f"{rel}: must be a JSON object")
        return
    if "__json_error__" in payload:
        result.errors.append(f"{rel}: invalid JSON: {payload['__json_error__']}")
        return
    if payload.get("task_id") != task_id:
        result.errors.append(f"{rel}: task_id must match directory name")
    events = payload.get("events")
    if not isinstance(events, list):
        result.errors.append(f"{rel}: events must be a list")
        return
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            result.errors.append(f"{rel}: event {index} must be an object")
            continue
        if not event.get("type"):
            result.errors.append(f"{rel}: event {index} missing type")
        if not event.get("summary"):
            result.errors.append(f"{rel}: event {index} missing summary")
        if not (event.get("at") or event.get("created_at")):
            result.errors.append(f"{rel}: event {index} missing at/created_at")


def validate_task_dir(root: Path, path: Path, strict: bool = False) -> ValidationResult:
    result = ValidationResult(checked_tasks=1)
    rel = path.relative_to(root).as_posix()
    task_id = path.name

    if not TASK_ID_PATTERN.match(task_id):
        result.errors.append(f"{rel}: task id must be YYYY-MM-DD-NNN-slug")

    for filename in REQUIRED_TASK_FILES:
        if not (path / filename).exists():
            result.errors.append(f"{rel}: missing {filename}")

    brief = read_text(path / "brief.md")
    for section in REQUIRED_BRIEF_SECTIONS:
        if section not in brief:
            add_warning_or_error(result, f"{rel}/brief.md: missing {section} section", strict)

    test_plan = read_text(path / "test-plan.md")
    for section in REQUIRED_TEST_PLAN_SECTIONS:
        if section not in test_plan:
            add_warning_or_error(result, f"{rel}/test-plan.md: missing {section} section", strict)

    final_report_exists = (path / "final-report.md").exists()
    if (path / "state.json").exists():
        validate_state(path / "state.json", task_id, final_report_exists, result)
    if (path / "run-log.json").exists():
        validate_run_log(path / "run-log.json", task_id, result)

    return result


def current_task_id(root: Path) -> str | None:
    current_path = root / ".agent" / "current-task.json"
    current = load_json(current_path)
    if current is None:
        return None
    if not isinstance(current, dict):
        raise ValueError(".agent/current-task.json must be a JSON object")
    task_id = current.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError(".agent/current-task.json missing task_id")
    return task_id


def validate_current(root: Path, strict_current: bool) -> ValidationResult:
    result = ValidationResult()
    try:
        task_id = current_task_id(root)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result
    if not task_id:
        return result
    path = root / ".agent" / "tasks" / task_id
    if not path.exists():
        result.errors.append(f".agent/current-task.json: task does not exist: {task_id}")
        return result
    result.extend(validate_task_dir(root, path, strict=strict_current))
    return result


def validate_repo(
    root: Path,
    *,
    task_id: str | None = None,
    strict: bool = False,
    strict_current: bool = False,
) -> ValidationResult:
    root = root.resolve()
    result = validate_project_files(root, strict=strict or strict_current)

    if task_id:
        path = root / ".agent" / "tasks" / task_id
        if not path.exists():
            result.errors.append(f".agent/tasks/{task_id}: task does not exist")
        else:
            result.extend(validate_task_dir(root, path, strict=strict))
        return result

    for path in task_dirs(root):
        result.extend(validate_task_dir(root, path, strict=strict))

    current_result = validate_current(root, strict_current=strict_current)
    result.errors.extend(current_result.errors)
    result.warnings.extend(current_result.warnings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to validate")
    parser.add_argument("--task", dest="task_id", help="Validate one task id")
    parser.add_argument("--strict", action="store_true", help="Fail on all warnings")
    parser.add_argument("--strict-current", action="store_true", help="Fail on warnings for current task")
    parser.add_argument("--show-warnings", action="store_true", help="Print warnings")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_repo(
        args.root,
        task_id=args.task_id,
        strict=args.strict,
        strict_current=args.strict_current,
    )

    if args.show_warnings:
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    if result.errors:
        for error in result.errors:
            print(error, file=sys.stderr)
        return 1

    suffix = ""
    if result.warnings and not args.show_warnings:
        suffix = f"; {len(result.warnings)} warnings hidden"
    print(f"checked {result.checked_tasks} task artifact directories{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
