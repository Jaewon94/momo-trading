"""관리자 런타임 설정 영속 저장."""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class RuntimeSetting(Base, TimestampMixin):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
