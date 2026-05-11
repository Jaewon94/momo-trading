from __future__ import annotations

import json
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal, run_sqlite_write_with_retry
from core.runtime_settings import (
    MUTABLE_SETTINGS,
    SECRET_RUNTIME_SETTINGS,
    coerce_runtime_setting_value,
    is_skipped_runtime_setting_value,
)
from repositories.runtime_setting_repository import RuntimeSettingRepository


class RuntimeSettingsService:
    async def update_settings(self, updates: dict[str, Any]) -> dict[str, dict[str, Any]]:
        changed: dict[str, dict[str, Any]] = {}
        normalized_updates: dict[str, Any] = {}

        for key, value in updates.items():
            if key not in MUTABLE_SETTINGS:
                continue

            normalized = coerce_runtime_setting_value(key, value)
            if is_skipped_runtime_setting_value(normalized):
                continue
            normalized_updates[key] = normalized

        old_values = {
            key: getattr(settings, key, None)
            for key in normalized_updates
        }

        async def _persist_updates() -> None:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    repository = RuntimeSettingRepository(session)
                    for key, normalized in normalized_updates.items():
                        await repository.upsert_value(key, self._serialize_value(normalized))

        await run_sqlite_write_with_retry(
            _persist_updates,
            retry_count=max(int(settings.SQLITE_WRITE_RETRY_COUNT), 5),
            retry_delay_ms=max(int(settings.SQLITE_WRITE_RETRY_DELAY_MS), 250),
        )

        for key, normalized in normalized_updates.items():
            old = old_values.get(key)
            setattr(settings, key, normalized)
            changed[key] = {"old": old, "new": normalized}
            logger.info("설정 변경: {} = {} → {}", key, old, normalized)

        return changed

    async def apply_persisted_settings(self) -> dict[str, Any]:
        applied: dict[str, Any] = {}
        allowed_keys = set(MUTABLE_SETTINGS) | SECRET_RUNTIME_SETTINGS

        async with AsyncSessionLocal() as session:
            repository = RuntimeSettingRepository(session)
            rows = await repository.get_all_settings()

        for row in rows:
            if row.key not in allowed_keys:
                continue

            normalized = coerce_runtime_setting_value(row.key, self._deserialize_value(row.value_json))
            if is_skipped_runtime_setting_value(normalized):
                continue

            setattr(settings, row.key, normalized)
            applied[row.key] = normalized

        return applied

    @staticmethod
    def _serialize_value(value: Any) -> str:
        return json.dumps(value)

    @staticmethod
    def _deserialize_value(value_json: str) -> Any:
        try:
            return json.loads(value_json)
        except json.JSONDecodeError:
            return value_json


runtime_settings_service = RuntimeSettingsService()
