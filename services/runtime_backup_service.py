from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from shutil import copy2

from core.config import settings
from core.paths import PROJECT_ROOT, RUNTIME_BACKUP_DIR


class RuntimeBackupService:
    def __init__(self, backup_dir: Path | None = None) -> None:
        self._backup_dir = backup_dir or (RUNTIME_BACKUP_DIR / "db")

    def create_database_backup(self, *, reason: str = "manual") -> dict[str, object]:
        source_path = self._resolve_database_path()
        if not source_path.exists():
            raise FileNotFoundError(f"백업할 DB 파일이 없습니다: {source_path}")

        self._backup_dir.mkdir(parents=True, exist_ok=True)

        created_at = datetime.now().astimezone()
        safe_reason = self._sanitize_reason(reason)
        filename = f"app-{safe_reason}-{created_at.strftime('%Y%m%d-%H%M%S')}.db"
        backup_path = self._backup_dir / filename

        if source_path.suffix == ".db":
            self._backup_sqlite(source_path, backup_path)
        else:
            copy2(source_path, backup_path)

        return {
            "reason": safe_reason,
            "filename": filename,
            "path": str(backup_path),
            "relative_path": self._display_path(backup_path),
            "source_path": str(source_path),
            "size_bytes": int(backup_path.stat().st_size),
            "created_at": created_at.isoformat(),
        }

    def _resolve_database_path(self) -> Path:
        database_url = str(settings.DATABASE_URL or "").strip()
        if not database_url.startswith("sqlite:///"):
            raise ValueError("SQLite DB만 로컬 백업을 지원합니다.")

        raw_path = database_url.removeprefix("sqlite:///")
        if not raw_path:
            raise ValueError("DATABASE_URL에서 DB 경로를 확인할 수 없습니다.")

        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = (PROJECT_ROOT / db_path).resolve()
        return db_path

    def _backup_sqlite(self, source_path: Path, backup_path: Path) -> None:
        source_conn = sqlite3.connect(source_path)
        try:
            target_conn = sqlite3.connect(backup_path)
            try:
                source_conn.backup(target_conn)
            finally:
                target_conn.close()
        finally:
            source_conn.close()

    @staticmethod
    def _sanitize_reason(reason: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in (reason or "manual"))
        return cleaned.strip("-_") or "manual"

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(path)


runtime_backup_service = RuntimeBackupService()
