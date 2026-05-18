#!/usr/bin/env python3
"""Read-only runtime integrity gate for a running momo-trading server."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:9000"
STATUS_RANK = {"OK": 0, "WARN": 1, "FAIL": 2, "ERROR": 3}


@dataclass(frozen=True)
class CheckOutcome:
    ok: bool
    status: str
    summary: str
    details: dict[str, Any]


def _fetch_json(url: str, timeout_sec: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"response must be a JSON object: {url}")
    return payload


def _response_data(payload: dict[str, Any], endpoint: str) -> Any:
    if payload.get("result") not in {None, "SUCCESS"}:
        raise ValueError(f"{endpoint}: result={payload.get('result')!r}, message={payload.get('message')!r}")
    return payload.get("data")


def _status_rank(status: str) -> int:
    return STATUS_RANK.get(status.upper(), STATUS_RANK["ERROR"])


def _worst_allowed_rank(allowed_statuses: set[str]) -> int:
    if not allowed_statuses:
        return STATUS_RANK["OK"]
    return max(_status_rank(status) for status in allowed_statuses)


def evaluate_lifecycle_report(report: dict[str, Any], *, allowed_statuses: set[str]) -> CheckOutcome:
    status = str(report.get("status") or "ERROR").upper()
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    failing_checks = [
        {
            "key": check.get("key"),
            "status": check.get("status"),
            "actual": check.get("actual"),
            "target": check.get("target"),
        }
        for check in checks
        if isinstance(check, dict) and _status_rank(str(check.get("status") or "ERROR")) > _worst_allowed_rank(allowed_statuses)
    ]
    details = {
        "open_buy_count": summary.get("open_buy_count"),
        "pending_confirm_count": summary.get("pending_confirm_count"),
        "confirm_failed_count": summary.get("confirm_failed_count"),
        "unpaired_sell_count": summary.get("unpaired_sell_count"),
        "broker_missing_open_buy_count": summary.get("broker_missing_open_buy_count"),
        "broker_mismatched_open_buy_quantity": summary.get("broker_mismatched_open_buy_quantity"),
        "broker_untracked_holding_count": summary.get("broker_untracked_holding_count"),
        "repairable_sell_count": summary.get("repairable_sell_count"),
        "failing_checks": failing_checks,
    }
    ok = _status_rank(status) <= _worst_allowed_rank(allowed_statuses)
    concise = (
        f"status={status} "
        f"pending={details['pending_confirm_count']} "
        f"confirm_failed={details['confirm_failed_count']} "
        f"unpaired_sells={details['unpaired_sell_count']} "
        f"broker_missing_open_buys={details['broker_missing_open_buy_count']} "
        f"broker_mismatch_qty={details['broker_mismatched_open_buy_quantity']} "
        f"broker_untracked_holdings={details['broker_untracked_holding_count']}"
    )
    return CheckOutcome(ok=ok, status=status, summary=concise, details=details)


def evaluate_order_reconciliation_report(report: dict[str, Any], *, allowed_statuses: set[str]) -> CheckOutcome:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    pending_counts = {
        "broker_pending_count": int(summary.get("broker_pending_count") or 0),
        "db_pending_count": int(summary.get("db_pending_count") or 0),
        "partial_fill_pending_count": int(summary.get("partial_fill_pending_count") or 0),
    }
    counts = {
        "broker_only_count": int(summary.get("broker_only_count") or 0),
        "broker_linked_non_pending_count": int(summary.get("broker_linked_non_pending_count") or 0),
        "db_only_stale_count": int(summary.get("db_only_stale_count") or 0),
        "quantity_mismatch_count": int(summary.get("quantity_mismatch_count") or 0),
    }
    pending_warnings = [
        {"key": key, "status": "WARN", "actual": value, "target": 0}
        for key, value in pending_counts.items()
        if value > 0
    ]
    failing = [
        {"key": key, "status": "FAIL", "actual": value, "target": 0}
        for key, value in counts.items()
        if value > 0
    ]
    status = "FAIL" if failing else ("WARN" if pending_warnings else "OK")
    details = {
        **pending_counts,
        **counts,
        "failing_checks": pending_warnings + failing,
    }
    concise = (
        f"order_reconciliation={status} "
        f"broker_pending={details['broker_pending_count']} "
        f"db_pending={details['db_pending_count']} "
        f"broker_only={details['broker_only_count']} "
        f"broker_linked_non_pending={details['broker_linked_non_pending_count']} "
        f"db_only_stale={details['db_only_stale_count']} "
        f"qty_mismatch={details['quantity_mismatch_count']} "
        f"partial_pending={details['partial_fill_pending_count']}"
    )
    ok = _status_rank(status) <= _worst_allowed_rank(allowed_statuses)
    return CheckOutcome(ok=ok, status=status, summary=concise, details=details)


def evaluate_runtime_settings(settings_payload: dict[str, Any], *, allowed_statuses: set[str]) -> CheckOutcome:
    admin_confirmation_required = bool(settings_payload.get("ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED"))
    failing = []
    if not admin_confirmation_required:
        failing.append({
            "key": "admin_dangerous_action_confirmation",
            "status": "WARN",
            "actual": False,
            "target": True,
        })
    status = "WARN" if failing else "OK"
    details = {
        "admin_dangerous_action_confirmation_required": admin_confirmation_required,
        "trading_enabled": bool(settings_payload.get("TRADING_ENABLED")),
        "autonomy_mode": settings_payload.get("AUTONOMY_MODE"),
        "order_submission_mode": settings_payload.get("ORDER_SUBMISSION_MODE"),
        "failing_checks": failing,
    }
    concise = (
        f"settings={status} "
        f"trading_enabled={details['trading_enabled']} "
        f"autonomy={details['autonomy_mode']} "
        f"order_mode={details['order_submission_mode']} "
        f"admin_confirm={details['admin_dangerous_action_confirmation_required']}"
    )
    ok = _status_rank(status) <= _worst_allowed_rank(allowed_statuses)
    return CheckOutcome(ok=ok, status=status, summary=concise, details=details)


def evaluate_system_status(system_status: dict[str, Any], *, allowed_statuses: set[str]) -> CheckOutcome:
    trading_enabled = bool(system_status.get("trading_enabled"))
    scheduler_running = bool(system_status.get("scheduler_running"))
    agent_running = bool(system_status.get("agent_running"))
    effective_order_mode = str(system_status.get("effective_order_submission_mode") or "")
    failing = []
    if trading_enabled and not scheduler_running:
        failing.append({"key": "scheduler_running", "status": "FAIL", "actual": False, "target": True})
    if trading_enabled and not agent_running:
        failing.append({"key": "agent_running", "status": "FAIL", "actual": False, "target": True})
    status = "FAIL" if failing else "OK"
    details = {
        "trading_enabled": trading_enabled,
        "autonomy_mode": system_status.get("autonomy_mode"),
        "effective_order_submission_mode": effective_order_mode,
        "scheduler_running": scheduler_running,
        "agent_running": agent_running,
        "market_session": system_status.get("market_session"),
        "failing_checks": failing,
    }
    concise = (
        f"system={status} "
        f"trading_enabled={trading_enabled} "
        f"autonomy={details['autonomy_mode']} "
        f"effective_order_mode={effective_order_mode} "
        f"scheduler={scheduler_running} "
        f"agent={agent_running}"
    )
    ok = _status_rank(status) <= _worst_allowed_rank(allowed_statuses)
    return CheckOutcome(ok=ok, status=status, summary=concise, details=details)


def combine_outcomes(outcomes: dict[str, CheckOutcome], *, allowed_statuses: set[str]) -> CheckOutcome:
    status = max((outcome.status for outcome in outcomes.values()), key=_status_rank, default="ERROR")
    details = {
        name: {
            "status": outcome.status,
            "ok": outcome.ok,
            "summary": outcome.summary,
            "details": outcome.details,
        }
        for name, outcome in outcomes.items()
    }
    failing_checks = [
        {"section": name, **check}
        for name, outcome in outcomes.items()
        for check in outcome.details.get("failing_checks", [])
    ]
    details["failing_checks"] = failing_checks
    summary = " | ".join(outcome.summary for outcome in outcomes.values())
    ok = _status_rank(status) <= _worst_allowed_rank(allowed_statuses)
    return CheckOutcome(ok=ok, status=status, summary=summary, details=details)


def check_runtime(
    *,
    base_url: str,
    days: int,
    timeout_sec: float,
    allowed_statuses: set[str],
) -> CheckOutcome:
    base_url = base_url.rstrip("/")
    health = _response_data(_fetch_json(f"{base_url}/api/v1/health", timeout_sec), "health")
    if not isinstance(health, dict) or health.get("status") != "healthy":
        return CheckOutcome(
            ok=False,
            status="ERROR",
            summary=f"health check failed: {health!r}",
            details={"health": health},
        )

    system_payload = _fetch_json(f"{base_url}/api/v1/admin/system/status", timeout_sec)
    system_status = _response_data(system_payload, "system/status")
    if not isinstance(system_status, dict):
        raise ValueError("system/status: data must be a JSON object")

    settings_payload = _fetch_json(f"{base_url}/api/v1/admin/settings", timeout_sec)
    runtime_settings = _response_data(settings_payload, "settings")
    if not isinstance(runtime_settings, dict):
        raise ValueError("settings: data must be a JSON object")

    reconciliation_payload = _fetch_json(f"{base_url}/api/v1/admin/trades/reconciliation", timeout_sec)
    reconciliation_report = _response_data(reconciliation_payload, "trades/reconciliation")
    if not isinstance(reconciliation_report, dict):
        raise ValueError("trades/reconciliation: data must be a JSON object")

    query = urllib.parse.urlencode({"days": days})
    payload = _fetch_json(f"{base_url}/api/v1/admin/trades/lifecycle-integrity?{query}", timeout_sec)
    report = _response_data(payload, "trades/lifecycle-integrity")
    if not isinstance(report, dict):
        raise ValueError("trades/lifecycle-integrity: data must be a JSON object")
    return combine_outcomes(
        {
            "system": evaluate_system_status(system_status, allowed_statuses=allowed_statuses),
            "settings": evaluate_runtime_settings(runtime_settings, allowed_statuses=allowed_statuses),
            "order_reconciliation": evaluate_order_reconciliation_report(
                reconciliation_report,
                allowed_statuses=allowed_statuses,
            ),
            "lifecycle": evaluate_lifecycle_report(report, allowed_statuses=allowed_statuses),
        },
        allowed_statuses=allowed_statuses,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument(
        "--allow-status",
        action="append",
        choices=sorted(STATUS_RANK),
        default=["OK"],
        help="Highest runtime lifecycle status accepted as a passing gate. Repeat to allow multiple statuses.",
    )
    parser.add_argument(
        "--skip-if-unavailable",
        action="store_true",
        help="Exit 0 when the local server is unavailable; still fails on integrity WARN/FAIL once reachable.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable outcome.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    allowed_statuses = {str(status).upper() for status in args.allow_status}
    try:
        outcome = check_runtime(
            base_url=args.base_url,
            days=args.days,
            timeout_sec=args.timeout_sec,
            allowed_statuses=allowed_statuses,
        )
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        if args.skip_if_unavailable:
            print(f"runtime integrity skipped: server unavailable ({exc})")
            return 0
        print(f"runtime integrity error: server unavailable ({exc})", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"runtime integrity error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "ok": outcome.ok,
        "status": outcome.status,
        "summary": outcome.summary,
        "details": outcome.details,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        stream = sys.stdout if outcome.ok else sys.stderr
        print(f"runtime integrity: {outcome.summary}", file=stream)
        if outcome.details.get("failing_checks"):
            print(json.dumps(outcome.details["failing_checks"], ensure_ascii=False, indent=2), file=stream)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    sys.exit(main())
