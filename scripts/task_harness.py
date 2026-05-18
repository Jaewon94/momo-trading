#!/usr/bin/env python3
"""Create and update repo-local task harness artifacts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / ".agent" / "tasks"
CURRENT_TASK_PATH = ROOT / ".agent" / "current-task.json"
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
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


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str, fallback: str = "task") -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().casefold()).strip("-")
    return slug[:64].strip("-") or fallback


def today() -> str:
    return datetime.now().astimezone().date().isoformat()


def next_sequence(date_prefix: str) -> int:
    if not TASKS_PATH.exists():
        return 1
    seen = 0
    for path in TASKS_PATH.iterdir():
        if not path.is_dir() or not path.name.startswith(f"{date_prefix}-"):
            continue
        parts = path.name.split("-", 4)
        if len(parts) >= 4 and parts[3].isdigit():
            seen = max(seen, int(parts[3]))
    return seen + 1


def make_task_id(title: str, slug: str = "") -> str:
    date_prefix = today()
    return f"{date_prefix}-{next_sequence(date_prefix):03d}-{slugify(slug or title)}"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def task_dir(task_id: str) -> Path:
    if not TASK_ID_PATTERN.match(task_id):
        raise ValueError(f"invalid task id: {task_id}")
    return TASKS_PATH / task_id


def render_brief(task_id: str, title: str, goal: str, created_at: str, research: list[str]) -> str:
    research_lines = "\n".join(f"- {item}" for item in research) or "- Not applicable"
    return f"""# Brief

## Metadata

- Task ID: `{task_id}`
- Created: `{created_at}`
- Repo: `momo-trading`
- Title: {title}

## Goal

{goal.strip()}

## Scope

In scope:

- Define the intended code, document, or operations change.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

{research_lines}

Plan implications:

- Adopt:
- Defer:
- Reject:

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Add task-specific commands here.
"""


def render_test_plan(task_id: str) -> str:
    return f"""# Test Plan

Task: `{task_id}`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
"""


def render_decision_record() -> str:
    return """# Decision Record

## Decision

Pending.

## Rationale

Pending.

## Deferred

Pending.

## Risks

Pending.
"""


def render_quality_scorecard() -> str:
    return """# Quality Scorecard

## Context Quality

- Status: pending

## Implementation Quality

- Status: pending

## Test Quality

- Status: pending

## Operational Safety

- Status: pending
"""


def initial_state(task_id: str, title: str, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": "momo.task.v1",
        "task_id": task_id,
        "status": "created",
        "title": title,
        "repo": "momo-trading",
        "risk_level": "medium",
        "task_type": "engineering",
        "priority": "normal",
        "primary_runtime": "codex",
        "created_at": created_at,
        "updated_at": created_at,
        "approval": {"required": False, "status": "not_required"},
        "checks": {},
        "artifacts": {
            "brief": f".agent/tasks/{task_id}/brief.md",
            "state": f".agent/tasks/{task_id}/state.json",
            "run_log": f".agent/tasks/{task_id}/run-log.json",
            "test_plan": f".agent/tasks/{task_id}/test-plan.md",
            "decision_record": f".agent/tasks/{task_id}/decision-record.md",
            "quality_scorecard": f".agent/tasks/{task_id}/quality-scorecard.md",
        },
        "errors": [],
    }


def initial_run_log(task_id: str, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": "momo.run-log.v1",
        "task_id": task_id,
        "events": [
            {
                "at": created_at,
                "type": "task_started",
                "status": "created",
                "summary": "Task artifact created.",
            }
        ],
    }


def update_state(task_id: str, status: str, checks: dict[str, str] | None = None) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}")
    path = task_dir(task_id) / "state.json"
    state = load_json(path, {})
    if not isinstance(state, dict) or not state:
        raise ValueError(f"missing state.json for {task_id}")
    state["status"] = status
    state["updated_at"] = now_iso()
    if checks:
        current = state.get("checks")
        if not isinstance(current, dict):
            current = {}
        current.update(checks)
        state["checks"] = current
    write_json(path, state)


def append_event(task_id: str, event_type: str, summary: str, status: str = "") -> None:
    log_path = task_dir(task_id) / "run-log.json"
    payload = load_json(log_path, {"schema_version": "momo.run-log.v1", "task_id": task_id, "events": []})
    events = payload.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError(f"invalid run-log events for {task_id}")
    events.append({"at": now_iso(), "type": event_type, "status": status, "summary": summary})
    write_json(log_path, payload)


def command_start(args: argparse.Namespace) -> int:
    task_id = make_task_id(args.title, args.slug)
    path = task_dir(task_id)
    if path.exists():
        print(f"task already exists: {task_id}", file=sys.stderr)
        return 1
    created_at = now_iso()
    path.mkdir(parents=True)
    (path / "brief.md").write_text(
        render_brief(task_id, args.title, args.goal, created_at, args.research).rstrip() + "\n",
        encoding="utf-8",
    )
    (path / "test-plan.md").write_text(render_test_plan(task_id).rstrip() + "\n", encoding="utf-8")
    (path / "decision-record.md").write_text(render_decision_record().rstrip() + "\n", encoding="utf-8")
    (path / "quality-scorecard.md").write_text(render_quality_scorecard().rstrip() + "\n", encoding="utf-8")
    write_json(path / "state.json", initial_state(task_id, args.title, created_at))
    write_json(path / "run-log.json", initial_run_log(task_id, created_at))
    write_json(CURRENT_TASK_PATH, {"task_id": task_id, "status": "created", "path": f".agent/tasks/{task_id}", "updated_at": created_at})
    print(task_id)
    return 0


def command_status(args: argparse.Namespace) -> int:
    task_id = args.task_id
    if not task_id:
        current = load_json(CURRENT_TASK_PATH, {})
        task_id = current.get("task_id") if isinstance(current, dict) else ""
    if not task_id:
        print("no current task", file=sys.stderr)
        return 1
    path = task_dir(task_id)
    state = load_json(path / "state.json", {})
    print(json.dumps({"task_id": task_id, "path": str(path.relative_to(ROOT)), "state": state}, ensure_ascii=False, indent=2))
    return 0


def command_log(args: argparse.Namespace) -> int:
    append_event(args.task_id, args.event_type, args.summary, args.status)
    if args.status:
        update_state(args.task_id, args.status)
    print(f"logged: {args.task_id}")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    commands = [
        ("diff_check", ["git", "diff", "--check"]),
        (
            "py_compile",
            [
                sys.executable,
                "-m",
                "py_compile",
                "scripts/check_task_harness.py",
                "scripts/task_harness.py",
                "scripts/guard_git_command.py",
                "scripts/change_harness.py",
                "scripts/check_runtime_integrity.py",
                "scripts/check_markdown_links.py",
                "scripts/check_docs_consistency.py",
            ],
        ),
        ("secret_scan", [sys.executable, "scripts/guard_git_command.py", "scan-secrets"]),
        ("task_harness", [sys.executable, "scripts/check_task_harness.py", "--strict-current"]),
        (
            "markdown_links",
            [
                sys.executable,
                "scripts/check_markdown_links.py",
                "AGENTS.md",
                ".agent",
                "docs/workflows/code-commit-harness.md",
            ],
        ),
        ("docs_consistency", [sys.executable, "scripts/check_docs_consistency.py"]),
        (
            "harness_tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/scripts/test_check_task_harness.py",
                "tests/scripts/test_task_harness.py",
                "tests/scripts/test_guard_git_command.py",
                "tests/scripts/test_docs_harness_checks.py",
                "tests/scripts/test_change_harness.py",
                "tests/scripts/test_check_runtime_integrity.py",
                "-q",
            ],
        ),
    ]
    checks: dict[str, str] = {}
    passed = True
    for name, command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        checks[name] = "passed" if result.returncode == 0 else "failed"
        print(f"{name}: {checks[name]}")
        if result.returncode != 0:
            passed = False
            if result.stdout:
                print(result.stdout[-1200:])
            if result.stderr:
                print(result.stderr[-1200:], file=sys.stderr)
            break
    append_event(args.task_id, "verification_run", "Standard harness verification completed.", "passed" if passed else "failed")
    update_state(args.task_id, "testing" if passed else "failed", checks=checks)
    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--title", required=True)
    start.add_argument("--goal", required=True)
    start.add_argument("--slug", default="")
    start.add_argument("--research", action="append", default=[])
    start.set_defaults(func=command_start)

    status = subparsers.add_parser("status")
    status.add_argument("task_id", nargs="?")
    status.set_defaults(func=command_status)

    log = subparsers.add_parser("log")
    log.add_argument("task_id")
    log.add_argument("--event-type", default="agent_step")
    log.add_argument("--summary", required=True)
    log.add_argument("--status", default="")
    log.set_defaults(func=command_log)

    verify = subparsers.add_parser("verify")
    verify.add_argument("task_id")
    verify.set_defaults(func=command_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"task harness error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
