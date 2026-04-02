import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "start.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _build_test_env(
    tmp_path: Path,
    broker_provider: str,
    extra_env_lines: list[str] | None = None,
) -> tuple[dict[str, str], Path, Path]:
    venv_activate = tmp_path / "venv" / "bin" / "activate"
    venv_activate.parent.mkdir(parents=True, exist_ok=True)
    venv_activate.write_text("#!/bin/sh\n", encoding="utf-8")

    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
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
            "MOMO_HOST": "127.0.0.1",
            "MOMO_PORT": "9900",
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
    assert python_log.read_text(encoding="utf-8").splitlines()[0:3] == ["-m", "uvicorn", "main:app"]


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
    assert python_log.read_text(encoding="utf-8").splitlines()[0:3] == ["-m", "uvicorn", "main:app"]
