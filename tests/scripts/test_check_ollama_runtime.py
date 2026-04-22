import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_OLLAMA_RUNTIME = REPO_ROOT / "scripts" / "dev" / "check_ollama_runtime.py"


def test_check_ollama_runtime_runs_directly_outside_repo_root(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("MOMO_ENV_FILE", None)

    result = subprocess.run(
        [sys.executable, str(CHECK_OLLAMA_RUNTIME)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "ModuleNotFoundError" not in result.stderr
