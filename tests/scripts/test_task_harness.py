import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_HARNESS = REPO_ROOT / "scripts" / "task_harness.py"
CHECK_HARNESS = REPO_ROOT / "scripts" / "check_task_harness.py"


def _copy_scripts(root: Path) -> None:
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "task_harness.py").write_text(TASK_HARNESS.read_text(encoding="utf-8"), encoding="utf-8")
    (scripts_dir / "check_task_harness.py").write_text(CHECK_HARNESS.read_text(encoding="utf-8"), encoding="utf-8")


def test_task_harness_start_status_and_log_workflow(tmp_path: Path) -> None:
    _copy_scripts(tmp_path)
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "project-card.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / ".agent" / "security-policy.md").write_text("# Security\n", encoding="utf-8")

    start = subprocess.run(
        [
            sys.executable,
            "scripts/task_harness.py",
            "start",
            "--title",
            "Harness smoke",
            "--goal",
            "Create a temp task.",
            "--slug",
            "harness-smoke",
            "--research",
            "local test",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert start.returncode == 0, start.stderr
    task_id = start.stdout.strip()
    task_dir = tmp_path / ".agent" / "tasks" / task_id
    assert task_dir.exists()
    assert (task_dir / "brief.md").exists()
    assert (task_dir / "decision-record.md").exists()

    status = subprocess.run(
        [sys.executable, "scripts/task_harness.py", "status"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert status.returncode == 0, status.stderr
    status_payload = json.loads(status.stdout)
    assert status_payload["task_id"] == task_id

    log = subprocess.run(
        [
            sys.executable,
            "scripts/task_harness.py",
            "log",
            task_id,
            "--event-type",
            "agent_step",
            "--summary",
            "Temp log entry.",
            "--status",
            "testing",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert log.returncode == 0, log.stderr
    state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
    run_log = json.loads((task_dir / "run-log.json").read_text(encoding="utf-8"))
    assert state["status"] == "testing"
    assert run_log["events"][-1]["summary"] == "Temp log entry."

    validate = subprocess.run(
        [sys.executable, "scripts/check_task_harness.py", "--strict-current"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert validate.returncode == 0, validate.stderr
