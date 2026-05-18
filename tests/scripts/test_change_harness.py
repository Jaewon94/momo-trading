import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "change_harness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("change_harness", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_strategy_change_is_high_risk_with_required_reviewers() -> None:
    module = _load_module()

    result = module.classify_paths(["strategy/risk_manager.py"])

    assert result.risk == "high"
    assert result.protected
    assert "risk-manager" in result.reviewers
    assert "tests/strategy" in result.checks
    assert module.RUNTIME_INTEGRITY_CHECK in result.checks


def test_admin_ui_change_is_medium_risk_frontend_work() -> None:
    module = _load_module()

    result = module.classify_paths(["admin/static/js/app.js"])

    assert result.risk == "medium"
    assert not result.protected
    assert "frontend-engineer" in result.reviewers
    assert "tests/frontend" in result.checks
    assert module.RUNTIME_INTEGRITY_CHECK not in result.checks


def test_scheduler_change_requires_runtime_integrity_gate() -> None:
    module = _load_module()

    result = module.classify_paths(["scheduler/scheduler.py"])

    assert result.risk == "medium"
    assert module.RUNTIME_INTEGRITY_CHECK in result.checks


def test_secret_file_change_is_blocked() -> None:
    module = _load_module()

    result = module.classify_paths([".env"])

    assert result.risk == "blocked"
    assert result.protected
    assert "security-reviewer" in result.reviewers


def test_unknown_code_path_defaults_to_medium_review() -> None:
    module = _load_module()

    result = module.classify_paths(["new_module/example.py"])

    assert result.risk == "medium"
    assert result.reviewers == ["code-reviewer"]
    assert result.checks == ["focused tests"]
