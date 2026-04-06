from __future__ import annotations

import json
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal
from core.runtime_settings import (
    MUTABLE_SETTINGS,
    coerce_runtime_setting_value,
    is_skipped_runtime_setting_value,
)
from repositories.runtime_setting_repository import RuntimeSettingRepository


class RuntimeSettingsService:
    async def update_settings(self, updates: dict[str, Any]) -> dict[str, dict[str, Any]]:
        changed: dict[str, dict[str, Any]] = {}

        async with AsyncSessionLocal() as session:
            async with session.begin():
                repository = RuntimeSettingRepository(session)
                for key, value in updates.items():
                    if key not in MUTABLE_SETTINGS:
                        continue

                    normalized = coerce_runtime_setting_value(key, value)
                    if is_skipped_runtime_setting_value(normalized):
                        continue

                    old = getattr(settings, key, None)
                    setattr(settings, key, normalized)
                    await repository.upsert_value(key, self._serialize_value(normalized))
                    changed[key] = {"old": old, "new": normalized}
                    logger.info("설정 변경: {} = {} → {}", key, old, normalized)

        return changed

    async def apply_persisted_settings(self) -> dict[str, Any]:
        applied: dict[str, Any] = {}

        async with AsyncSessionLocal() as session:
            repository = RuntimeSettingRepository(session)
            rows = await repository.get_all_settings()

        for row in rows:
            if row.key not in MUTABLE_SETTINGS:
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
