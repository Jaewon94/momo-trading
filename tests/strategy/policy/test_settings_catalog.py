from core.runtime_settings import MUTABLE_SETTINGS
from strategy.policy.settings_catalog import (
    POLICY_SETTINGS_CATALOG,
    catalog_as_dict,
    catalog_by_owner,
    classify_policy_setting,
)


def test_policy_settings_catalog_covers_all_mutable_settings() -> None:
    assert set(POLICY_SETTINGS_CATALOG) == set(MUTABLE_SETTINGS)


def test_policy_settings_catalog_metadata_is_complete() -> None:
    for key, metadata in POLICY_SETTINGS_CATALOG.items():
        assert metadata.key == key
        assert metadata.owner
        assert metadata.scope
        assert metadata.risk in {"low", "medium", "high"}
        assert metadata.mutable is True
        assert metadata.source == "core.runtime_settings.MUTABLE_SETTINGS"


def test_policy_settings_catalog_classifies_key_policy_owners() -> None:
    expected = {
        "ORDER_SUBMISSION_MODE": ("order_submission", "ORDER_SUBMISSION", "high"),
        "RISK_APPETITE": ("risk_manager", "BUY", "high"),
        "AGGRESSIVE_TARGET_EXPOSURE_PCT": ("exposure_alignment", "BUY", "high"),
        "DEFAULT_STOP_LOSS_PCT_MID": ("holding_exit", "HOLDING_EXIT", "high"),
        "DETERMINISTIC_TIER1_FAST_GATE_MODE": (
            "deterministic_tier1_fast_gate",
            "CANDIDATE",
            "medium",
        ),
        "HORIZON_SCAN_LONG_DAY_OF_WEEK": ("scheduler", "SCHEDULER", "medium"),
        "HORIZON_MID_MAX_CANDIDATES": ("candidate_scoring", "CANDIDATE", "medium"),
        "NEWS_GATE_ROLLOUT_MODE": ("news_gate", "BUY", "medium"),
    }

    for key, (owner, scope, risk) in expected.items():
        metadata = POLICY_SETTINGS_CATALOG[key].to_dict()
        assert metadata["owner"] == owner
        assert metadata["scope"] == scope
        assert metadata["risk"] == risk


def test_policy_settings_catalog_helpers_are_serializable() -> None:
    grouped = catalog_by_owner()
    serialized = catalog_as_dict()

    assert "risk_manager" in grouped
    assert serialized["RISK_APPETITE"]["owner"] == "risk_manager"
    assert classify_policy_setting("UNKNOWN_EXPERIMENT").owner == "runtime_settings"
