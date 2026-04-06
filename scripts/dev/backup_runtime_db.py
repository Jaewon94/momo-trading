from __future__ import annotations

import json

from services.runtime_backup_service import runtime_backup_service


def main() -> int:
    backup = runtime_backup_service.create_database_backup(reason="cli")
    print(json.dumps(backup, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
