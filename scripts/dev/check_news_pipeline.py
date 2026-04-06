from __future__ import annotations

import json
import os
import sys
from urllib import error, parse, request


def main() -> int:
    base_url = os.environ.get("MOMO_ADMIN_BASE_URL", "http://127.0.0.1:9000")
    query = parse.urlencode({
        "recent_limit": 3,
        "performance_days": 30,
    })
    url = f"{base_url.rstrip('/')}/api/v1/admin/news/overview?{query}"

    try:
        with request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        print(f"뉴스 overview 조회 실패: {exc}", file=sys.stderr)
        return 1

    data = payload.get("data") or {}
    runtime = (data.get("runtime") or {}).get("overall") or {}
    sources = (data.get("runtime") or {}).get("sources") or {}
    ingestion = data.get("ingestion") or {}
    storage = data.get("storage") or {}

    print(f"storage.ready={bool(storage.get('ready'))} message={storage.get('message') or '-'}")
    print(
        "overall"
        f" status={runtime.get('last_status') or 'IDLE'}"
        f" mode={runtime.get('last_mode') or '-'}"
        f" run_at={runtime.get('last_run_at') or '-'}"
        f" message={runtime.get('last_message') or '-'}"
    )
    print(
        "ingestion"
        f" recent_24h={int(ingestion.get('recent_24h_count') or 0)}"
        f" recent_7d={int(ingestion.get('recent_7d_count') or 0)}"
        f" latest={ingestion.get('latest_published_at') or '-'}"
    )

    for code in sorted(sources.keys()):
        source = sources.get(code) or {}
        counts = source.get("counts") or {}
        print(
            f"source[{code}]"
            f" status={source.get('status') or 'IDLE'}"
            f" updated_at={source.get('updated_at') or '-'}"
            f" created={int(counts.get('created') or 0)}"
            f" duplicates={int(counts.get('duplicates') or 0)}"
            f" skipped={int(counts.get('skipped') or 0)}"
            f" last_success={source.get('last_success_at') or '-'}"
            f" last_error={source.get('last_error_at') or '-'}"
            f" failures={int(source.get('consecutive_failures') or 0)}"
            f" message={source.get('message') or '-'}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
