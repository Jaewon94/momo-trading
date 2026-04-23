"""Server-side confirmation tokens for high-risk admin actions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from core.config import settings
from util.time_util import ensure_kst, now_kst


class AdminActionConfirmationService:
    def __init__(self, *, secret: str | None = None, ttl_seconds: int | None = None) -> None:
        self._secret = (secret or self._default_secret()).encode("utf-8")
        self._ttl_seconds = int(ttl_seconds) if ttl_seconds is not None else None
        self._used_nonces: set[str] = set()

    def create_challenge(
        self,
        *,
        action: str,
        resource_id: str,
        quantity: str | int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        issued_at = ensure_kst(now or now_kst())
        ttl_seconds = self._ttl_seconds
        if ttl_seconds is None:
            ttl_seconds = int(settings.ADMIN_ACTION_CONFIRMATION_TTL_SEC)
        expires_at = issued_at + timedelta(seconds=max(ttl_seconds, 1))
        payload = {
            "action": self._normalize_part(action),
            "resource_id": self._normalize_part(resource_id),
            "quantity": self._normalize_quantity(quantity),
            "nonce": secrets.token_urlsafe(16),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        token = self._encode(payload)
        return {
            "action": payload["action"],
            "resource_id": payload["resource_id"],
            "quantity": payload["quantity"],
            "expires_at": payload["expires_at"],
            "confirmation_token": token,
        }

    def verify_token(
        self,
        token: str | None,
        *,
        action: str,
        resource_id: str,
        quantity: str | int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not token:
            raise ValueError("confirmation token is required")

        payload = self._decode(token)
        expected = {
            "action": self._normalize_part(action),
            "resource_id": self._normalize_part(resource_id),
            "quantity": self._normalize_quantity(quantity),
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise ValueError("confirmation token does not match this action")

        expires_at = ensure_kst(datetime.fromisoformat(str(payload["expires_at"])))
        if ensure_kst(now or now_kst()) > expires_at:
            raise ValueError("confirmation token expired")

        nonce = str(payload.get("nonce") or "")
        if nonce in self._used_nonces:
            raise ValueError("confirmation token already used")
        self._used_nonces.add(nonce)
        return payload

    def _encode(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._secret, body, hashlib.sha256).digest()
        return ".".join((
            self._b64encode(body),
            self._b64encode(signature),
        ))

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            body_text, signature_text = token.split(".", 1)
            body = self._b64decode(body_text)
            signature = self._b64decode(signature_text)
        except Exception as exc:
            raise ValueError("invalid confirmation token") from exc

        expected_signature = hmac.new(self._secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid confirmation token")

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid confirmation token") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid confirmation token")
        return payload

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padded = value + ("=" * (-len(value) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    @staticmethod
    def _normalize_part(value: str | int | None) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _normalize_quantity(value: str | int | None) -> str:
        return str(value if value is not None else "ALL").strip().upper() or "ALL"

    @staticmethod
    def _default_secret() -> str:
        return f"{settings.APP_NAME}:{settings.DATABASE_URL}"


admin_action_confirmation_service = AdminActionConfirmationService()
