import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_runtime_integrity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_runtime_integrity", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_lifecycle_report_ok_passes() -> None:
    module = _load_module()

    outcome = module.evaluate_lifecycle_report(
        {
            "status": "OK",
            "summary": {
                "pending_confirm_count": 0,
                "confirm_failed_count": 0,
                "unpaired_sell_count": 0,
                "broker_missing_open_buy_count": 0,
                "broker_mismatched_open_buy_quantity": 0,
            },
            "checks": [{"key": "pending_confirms", "status": "OK", "actual": 0, "target": 0}],
        },
        allowed_statuses={"OK"},
    )

    assert outcome.ok
    assert outcome.status == "OK"
    assert outcome.details["failing_checks"] == []


def test_lifecycle_report_fail_blocks_gate() -> None:
    module = _load_module()

    outcome = module.evaluate_lifecycle_report(
        {
            "status": "FAIL",
            "summary": {
                "pending_confirm_count": 0,
                "confirm_failed_count": 43,
                "unpaired_sell_count": 12,
                "broker_missing_open_buy_count": 8,
                "broker_mismatched_open_buy_quantity": 491,
            },
            "checks": [
                {"key": "pending_confirms", "status": "OK", "actual": 0, "target": 0},
                {"key": "unpaired_sells", "status": "FAIL", "actual": 12, "target": 0},
            ],
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "FAIL"
    assert outcome.details["confirm_failed_count"] == 43
    assert outcome.details["failing_checks"] == [
        {"key": "unpaired_sells", "status": "FAIL", "actual": 12, "target": 0}
    ]


def test_allow_warn_still_blocks_fail() -> None:
    module = _load_module()

    warn_outcome = module.evaluate_lifecycle_report(
        {"status": "WARN", "summary": {}, "checks": [{"key": "repairable_sells", "status": "WARN"}]},
        allowed_statuses={"OK", "WARN"},
    )
    fail_outcome = module.evaluate_lifecycle_report(
        {"status": "FAIL", "summary": {}, "checks": [{"key": "unpaired_sells", "status": "FAIL"}]},
        allowed_statuses={"OK", "WARN"},
    )

    assert warn_outcome.ok
    assert not fail_outcome.ok


def test_order_reconciliation_mismatch_blocks_gate() -> None:
    module = _load_module()

    outcome = module.evaluate_order_reconciliation_report(
        {
            "summary": {
                "broker_pending_count": 1,
                "db_pending_count": 2,
                "broker_only_count": 1,
                "broker_linked_non_pending_count": 1,
                "db_only_stale_count": 1,
                "quantity_mismatch_count": 0,
                "partial_fill_pending_count": 0,
            }
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "FAIL"
    assert outcome.details["broker_only_count"] == 1
    assert outcome.details["failing_checks"] == [
        {"key": "broker_pending_count", "status": "WARN", "actual": 1, "target": 0},
        {"key": "db_pending_count", "status": "WARN", "actual": 2, "target": 0},
        {"key": "broker_only_count", "status": "FAIL", "actual": 1, "target": 0},
        {"key": "broker_linked_non_pending_count", "status": "FAIL", "actual": 1, "target": 0},
        {"key": "db_only_stale_count", "status": "FAIL", "actual": 1, "target": 0},
    ]


def test_order_reconciliation_pending_without_drift_warns() -> None:
    module = _load_module()

    outcome = module.evaluate_order_reconciliation_report(
        {
            "summary": {
                "broker_pending_count": 0,
                "db_pending_count": 1,
                "broker_only_count": 0,
                "db_only_stale_count": 0,
                "quantity_mismatch_count": 0,
                "partial_fill_pending_count": 0,
            }
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "WARN"
    assert outcome.details["failing_checks"] == [
        {"key": "db_pending_count", "status": "WARN", "actual": 1, "target": 0}
    ]


def test_order_reconciliation_partial_fill_pending_warns() -> None:
    module = _load_module()

    outcome = module.evaluate_order_reconciliation_report(
        {
            "summary": {
                "broker_pending_count": 1,
                "db_pending_count": 1,
                "broker_only_count": 0,
                "db_only_stale_count": 0,
                "quantity_mismatch_count": 0,
                "partial_fill_pending_count": 1,
            }
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "WARN"
    assert outcome.details["failing_checks"] == [
        {"key": "broker_pending_count", "status": "WARN", "actual": 1, "target": 0},
        {"key": "db_pending_count", "status": "WARN", "actual": 1, "target": 0},
        {"key": "partial_fill_pending_count", "status": "WARN", "actual": 1, "target": 0},
    ]


def test_runtime_settings_warn_when_dangerous_confirmation_disabled() -> None:
    module = _load_module()

    outcome = module.evaluate_runtime_settings(
        {
            "TRADING_ENABLED": True,
            "AUTONOMY_MODE": "AUTONOMOUS",
            "ORDER_SUBMISSION_MODE": "FULL",
            "ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED": False,
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "WARN"
    assert outcome.details["admin_dangerous_action_confirmation_required"] is False
    assert outcome.details["failing_checks"][0]["key"] == "admin_dangerous_action_confirmation"


def test_system_status_fails_when_live_scheduler_is_down() -> None:
    module = _load_module()

    outcome = module.evaluate_system_status(
        {
            "trading_enabled": True,
            "autonomy_mode": "AUTONOMOUS",
            "effective_order_submission_mode": "FULL",
            "scheduler_running": False,
            "agent_running": True,
        },
        allowed_statuses={"OK"},
    )

    assert not outcome.ok
    assert outcome.status == "FAIL"
    assert outcome.details["failing_checks"] == [
        {"key": "scheduler_running", "status": "FAIL", "actual": False, "target": True}
    ]


def test_combined_runtime_outcome_preserves_sections() -> None:
    module = _load_module()

    ok = module.CheckOutcome(ok=True, status="OK", summary="ok", details={"failing_checks": []})
    warn = module.CheckOutcome(
        ok=False,
        status="WARN",
        summary="warn",
        details={"failing_checks": [{"key": "sample", "status": "WARN", "actual": 1, "target": 0}]},
    )

    outcome = module.combine_outcomes({"system": ok, "settings": warn}, allowed_statuses={"OK"})

    assert not outcome.ok
    assert outcome.status == "WARN"
    assert outcome.details["settings"]["status"] == "WARN"
    assert outcome.details["failing_checks"] == [
        {"section": "settings", "key": "sample", "status": "WARN", "actual": 1, "target": 0}
    ]
