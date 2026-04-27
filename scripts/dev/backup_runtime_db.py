from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.runtime_backup_service import runtime_backup_service


def main() -> int:
    backup = runtime_backup_service.create_database_backup(reason="cli")
    print(json.dumps(backup, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
