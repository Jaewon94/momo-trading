from datetime import timedelta

import pytest

from services.admin_action_confirmation_service import AdminActionConfirmationService
from util.time_util import now_kst


def test_admin_action_confirmation_service_accepts_matching_token_once() -> None:
    service = AdminActionConfirmationService(secret="test-secret")
    challenge = service.create_challenge(
        action="SELL_HOLDING",
        resource_id="005930",
        quantity="ALL",
        now=now_kst(),
    )

    result = service.verify_token(
        challenge["confirmation_token"],
        action="SELL_HOLDING",
        resource_id="005930",
        quantity="ALL",
        now=now_kst(),
    )

    assert result["action"] == "SELL_HOLDING"
    assert result["resource_id"] == "005930"

    with pytest.raises(ValueError, match="already used"):
        service.verify_token(
            challenge["confirmation_token"],
            action="SELL_HOLDING",
            resource_id="005930",
            quantity="ALL",
            now=now_kst(),
        )


def test_admin_action_confirmation_service_rejects_mismatched_or_expired_token() -> None:
    service = AdminActionConfirmationService(secret="test-secret", ttl_seconds=30)
    issued_at = now_kst()
    challenge = service.create_challenge(
        action="CANCEL_AND_SELL_PENDING",
        resource_id="ORDER-1",
        quantity="ALL",
        now=issued_at,
    )

    with pytest.raises(ValueError, match="does not match"):
        service.verify_token(
            challenge["confirmation_token"],
            action="CANCEL_AND_SELL_PENDING",
            resource_id="ORDER-2",
            quantity="ALL",
            now=issued_at,
        )

    with pytest.raises(ValueError, match="expired"):
        service.verify_token(
            challenge["confirmation_token"],
            action="CANCEL_AND_SELL_PENDING",
            resource_id="ORDER-1",
            quantity="ALL",
            now=issued_at + timedelta(seconds=31),
        )
