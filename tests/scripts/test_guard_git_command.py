import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "guard_git_command.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("guard_git_command", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_git_commit_requires_approval() -> None:
    module = _load_module()

    result = module.check_command("git commit -m test")

    assert result.status == "ask"
    assert result.exit_code == 1


def test_regular_git_push_requires_separate_approval() -> None:
    module = _load_module()

    result = module.check_command("git push origin feature/test")

    assert result.status == "ask"
    assert result.exit_code == 1


def test_force_push_to_protected_branch_is_blocked() -> None:
    module = _load_module()

    result = module.check_command("git push --force origin main")

    assert result.status == "blocked"
    assert result.exit_code == 2


def test_non_git_command_is_allowed() -> None:
    module = _load_module()

    result = module.check_command("python -m pytest")

    assert result.status == "allowed"
    assert result.exit_code == 0


def test_secret_scan_detects_realistic_token_and_ignores_placeholder(tmp_path: Path) -> None:
    module = _load_module()
    safe = tmp_path / "safe.md"
    unsafe = tmp_path / "unsafe.py"
    safe.write_text("GITHUB_TOKEN=your_placeholder_token\n", encoding="utf-8")
    token = "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyzABCD"
    unsafe.write_text(f"TOKEN='{token}'\n", encoding="utf-8")

    findings = module.scan_secrets([safe, unsafe], root=tmp_path)

    assert findings == ["unsafe.py:1: possible github_token"]


def test_pre_push_blocks_protected_branch_deletion() -> None:
    module = _load_module()

    result = module.check_pre_push("(delete) 0000000000000000000000000000000000000000 refs/heads/main abc123\n")

    assert result.status == "blocked"
    assert result.exit_code == 2
