import sqlite3
from pathlib import Path

from services.runtime_backup_service import RuntimeBackupService


def test_runtime_backup_service_creates_sqlite_snapshot(tmp_path):
    source_path = tmp_path / "app.db"
    backup_root = tmp_path / "backups"

    conn = sqlite3.connect(source_path)
    try:
        conn.execute("create table sample (id integer primary key, value text)")
        conn.execute("insert into sample (value) values ('hello')")
        conn.commit()
    finally:
        conn.close()

    service = RuntimeBackupService(backup_dir=backup_root)
    service._resolve_database_path = lambda: source_path

    backup = service.create_database_backup(reason="manual")

    backup_path = Path(backup["path"])
    assert backup["filename"].startswith("app-manual-")
    assert backup["relative_path"] == str(backup_path)
    assert backup_path.exists() is True

    backup_conn = sqlite3.connect(backup_path)
    try:
        row = backup_conn.execute("select value from sample").fetchone()
    finally:
        backup_conn.close()

    assert row == ("hello",)


def test_runtime_backup_service_rejects_non_sqlite_database_url(monkeypatch):
    service = RuntimeBackupService()

    monkeypatch.setattr(
        "services.runtime_backup_service.settings",
        type("Settings", (), {"DATABASE_URL": "postgresql://example/db"})(),
    )

    try:
        service._resolve_database_path()
        assert False, "ValueError expected"
    except ValueError as exc:
        assert "SQLite" in str(exc)
