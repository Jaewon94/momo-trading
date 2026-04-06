import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "start.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _build_test_env(
    tmp_path: Path,
    broker_provider: str,
    extra_env_lines: list[str] | None = None,
) -> tuple[dict[str, str], Path, Path]:
    venv_activate = tmp_path / "venv" / "bin" / "activate"
    venv_alembic = tmp_path / "venv" / "bin" / "alembic"
    venv_activate.parent.mkdir(parents=True, exist_ok=True)
    venv_activate.write_text("#!/bin/sh\n", encoding="utf-8")
    _write_executable(
        venv_alembic,
        """#!/bin/sh
exit 0
""",
    )

    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    lsof_bin = tmp_path / "lsof"
    docker_bin = tmp_path / "docker"
    python_bin = tmp_path / "python"
    env_file = tmp_path / ".env.test"

    _write_executable(
        docker_bin,
        f"""#!/bin/sh
printf '%s\\n' "$@" >> '{docker_log}'
exit 0
""",
    )
    _write_executable(
        python_bin,
        f"""#!/bin/sh
printf '%s\\n' "$@" >> '{python_log}'
exit 0
""",
    )
    _write_executable(
        lsof_bin,
        """#!/bin/sh
exit 0
""",
    )
    env_lines = [f"BROKER_PROVIDER={broker_provider}"]
    env_lines.extend(extra_env_lines or [])
    env_file.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MOMO_ENV_FILE": str(env_file),
            "MOMO_VENV_DIR": str(venv_activate.parent.parent),
            "MOMO_PID_FILE": str(tmp_path / "momo.pid"),
            "MOMO_LOG_FILE": str(tmp_path / "momo.log"),
            "MOMO_DOCKER_BIN": str(docker_bin),
            "MOMO_PYTHON_BIN": str(python_bin),
            "MOMO_LSOF_BIN": str(lsof_bin),
            "MOMO_HOST": "127.0.0.1",
            "MOMO_PORT": "9900",
            "MOMO_STARTUP_WAIT_SEC": "0",
        }
    )
    return env, docker_log, python_log


def test_start_script_does_not_shell_export_complex_env_values(tmp_path: Path) -> None:
    env, _, _ = _build_test_env(
        tmp_path,
        "KIWOOM",
        extra_env_lines=['CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]'],
    )
    cors_log = tmp_path / "cors.log"

    python_bin = Path(env["MOMO_PYTHON_BIN"])
    _write_executable(
        python_bin,
        f"""#!/bin/sh
printf '%s\\n' "${{CORS_ORIGINS:-__UNSET__}}" > '{cors_log}'
exit 0
""",
    )

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert cors_log.read_text(encoding="utf-8").strip() == "__UNSET__"


def test_start_script_starts_kis_mcp_when_broker_provider_is_kis(tmp_path: Path) -> None:
    env, docker_log, python_log = _build_test_env(tmp_path, "KIS")

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert docker_log.read_text(encoding="utf-8").splitlines() == ["compose", "up", "-d", "kis-mcp"]
    python_lines = _read_lines(python_log)
    uvicorn_index = python_lines.index("uvicorn")
    assert python_lines[uvicorn_index - 1 : uvicorn_index + 2] == ["-m", "uvicorn", "main:app"]


def test_start_script_stops_kis_mcp_when_broker_provider_is_not_kis(tmp_path: Path) -> None:
    env, docker_log, python_log = _build_test_env(tmp_path, "KIWOOM")

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert docker_log.read_text(encoding="utf-8").splitlines() == ["compose", "stop", "kis-mcp"]
    python_lines = _read_lines(python_log)
    uvicorn_index = python_lines.index("uvicorn")
    assert python_lines[uvicorn_index - 1 : uvicorn_index + 2] == ["-m", "uvicorn", "main:app"]


def test_start_script_default_foreground_does_not_enable_reload(tmp_path: Path) -> None:
    env, _, python_log = _build_test_env(tmp_path, "KIWOOM")

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--reload" not in python_log.read_text(encoding="utf-8").splitlines()


def test_start_script_enables_reload_only_with_explicit_flag(tmp_path: Path) -> None:
    env, _, python_log = _build_test_env(tmp_path, "KIWOOM")

    result = subprocess.run(
        ["bash", str(START_SCRIPT), "--reload"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--reload" in python_log.read_text(encoding="utf-8").splitlines()


def test_start_script_blocks_start_when_target_port_is_already_in_use(tmp_path: Path) -> None:
    env, docker_log, python_log = _build_test_env(tmp_path, "KIWOOM")

    lsof_bin = Path(env["MOMO_LSOF_BIN"])
    _write_executable(
        lsof_bin,
        """#!/bin/sh
printf 'Python 3131\\n'
exit 0
""",
    )

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "이미 사용 중" in result.stdout
    assert not docker_log.exists()
    assert not python_log.exists()


def test_start_script_status_reports_running_when_port_is_listening_without_pid_file(tmp_path: Path) -> None:
    env, _, _ = _build_test_env(tmp_path, "KIWOOM")

    lsof_bin = Path(env["MOMO_LSOF_BIN"])
    _write_executable(
        lsof_bin,
        """#!/bin/sh
printf 'Python 3131\\n'
exit 0
""",
    )

    result = subprocess.run(
        ["bash", str(START_SCRIPT), "status"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "실행 중" in result.stdout
    assert "PID: 3131" in result.stdout
    assert "localhost:9900/admin" in result.stdout


def test_start_script_status_recovers_stale_pid_file_from_listening_port(tmp_path: Path) -> None:
    env, _, _ = _build_test_env(tmp_path, "KIWOOM")
    pid_file = Path(env["MOMO_PID_FILE"])
    pid_file.write_text("99999\n", encoding="utf-8")

    lsof_bin = Path(env["MOMO_LSOF_BIN"])
    _write_executable(
        lsof_bin,
        """#!/bin/sh
printf '3131\\n'
exit 0
""",
    )

    result = subprocess.run(
        ["bash", str(START_SCRIPT), "status"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "stale PID" in result.stdout
    assert "PID: 3131" in result.stdout
    assert pid_file.read_text(encoding="utf-8").strip() == "3131"


def test_start_script_backup_db_calls_backup_helper_without_starting_server(tmp_path: Path) -> None:
    env, docker_log, python_log = _build_test_env(tmp_path, "KIWOOM")

    result = subprocess.run(
        ["bash", str(START_SCRIPT), "backup-db"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "운영 DB 백업 생성" in result.stdout
    assert docker_log.exists() is False
    assert _read_lines(python_log) == ["scripts/dev/backup_runtime_db.py"]
