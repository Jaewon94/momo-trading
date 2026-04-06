from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.runtime_setting import RuntimeSetting
from repositories.async_base_repository import AsyncBaseRepository


class RuntimeSettingRepository(AsyncBaseRepository[RuntimeSetting]):
    def __init__(self, db: AsyncSession):
        super().__init__(RuntimeSetting, db)

    async def get_by_key(self, key: str) -> RuntimeSetting | None:
        return await self.filter_by_one(key=key)

    async def get_all_settings(self) -> list[RuntimeSetting]:
        result = await self.db.execute(select(RuntimeSetting))
        return list(result.scalars().all())

    async def upsert_value(self, key: str, value_json: str) -> RuntimeSetting:
        setting = await self.get_by_key(key)
        if setting is None:
            setting = RuntimeSetting(key=key, value_json=value_json)
            return await self.create(setting)
        setting.value_json = value_json
        return await self.update(setting)
