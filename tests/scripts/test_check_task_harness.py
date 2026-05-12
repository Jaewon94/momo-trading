import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_task_harness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_task_harness", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_minimal_harness(root: Path, task_id: str = "2026-05-12-001-test-task") -> Path:
    (root / ".agent" / "tasks" / task_id).mkdir(parents=True)
    (root / ".agent" / "project-card.md").write_text("# Project\n", encoding="utf-8")
    (root / ".agent" / "security-policy.md").write_text("# Security\n", encoding="utf-8")
    (root / ".agent" / "current-task.json").write_text(
        f'{{"task_id":"{task_id}","status":"implementing","path":".agent/tasks/{task_id}","updated_at":"2026-05-12T00:00:00+09:00"}}\n',
        encoding="utf-8",
    )
    task_dir = root / ".agent" / "tasks" / task_id
    (task_dir / "brief.md").write_text(
        "# Brief\n\n## Research Gate\n\n## Completion Criteria\n\n## Verification Plan\n",
        encoding="utf-8",
    )
    (task_dir / "test-plan.md").write_text("# Test Plan\n\n## Commands\n\n```bash\ntrue\n```\n", encoding="utf-8")
    (task_dir / "decision-record.md").write_text("# Decision Record\n", encoding="utf-8")
    (task_dir / "quality-scorecard.md").write_text("# Quality Scorecard\n", encoding="utf-8")
    (task_dir / "state.json").write_text(
        f'{{"schema_version":"momo.task.v1","task_id":"{task_id}","status":"implementing","updated_at":"2026-05-12T00:00:00+09:00"}}\n',
        encoding="utf-8",
    )
    (task_dir / "run-log.json").write_text(
        f'{{"schema_version":"momo.run-log.v1","task_id":"{task_id}","events":[{{"at":"2026-05-12T00:00:00+09:00","type":"task_started","summary":"started"}}]}}\n',
        encoding="utf-8",
    )
    return task_dir


def test_validate_repo_accepts_complete_current_task(tmp_path: Path) -> None:
    module = _load_module()
    _write_minimal_harness(tmp_path)

    result = module.validate_repo(tmp_path, strict_current=True)

    assert result.ok
    assert result.checked_tasks >= 1


def test_validate_repo_fails_when_required_task_file_missing(tmp_path: Path) -> None:
    module = _load_module()
    task_dir = _write_minimal_harness(tmp_path)
    (task_dir / "decision-record.md").unlink()

    result = module.validate_repo(tmp_path, strict_current=True)

    assert not result.ok
    assert any("missing decision-record.md" in error for error in result.errors)


def test_validate_repo_fails_for_invalid_task_id(tmp_path: Path) -> None:
    module = _load_module()
    _write_minimal_harness(tmp_path, task_id="bad-task-id")

    result = module.validate_repo(tmp_path, task_id="bad-task-id")

    assert not result.ok
    assert any("task id must be" in error for error in result.errors)


def test_strict_current_turns_brief_warning_into_error(tmp_path: Path) -> None:
    module = _load_module()
    task_dir = _write_minimal_harness(tmp_path)
    (task_dir / "brief.md").write_text("# Brief\n\n## Research Gate\n", encoding="utf-8")

    relaxed = module.validate_repo(tmp_path, strict_current=False)
    strict = module.validate_repo(tmp_path, strict_current=True)

    assert relaxed.ok
    assert relaxed.warnings
    assert not strict.ok
    assert any("Completion Criteria" in error for error in strict.errors)


def test_current_task_pointer_must_reference_existing_task(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "project-card.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / ".agent" / "security-policy.md").write_text("# Security\n", encoding="utf-8")
    (tmp_path / ".agent" / "current-task.json").write_text(
        '{"task_id":"2026-05-12-001-missing","status":"implementing"}\n',
        encoding="utf-8",
    )

    result = module.validate_repo(tmp_path, strict_current=True)

    assert not result.ok
    assert any("task does not exist" in error for error in result.errors)
