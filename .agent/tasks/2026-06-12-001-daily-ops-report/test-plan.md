# Test Plan

Task: `2026-06-12-001-daily-ops-report`

## Commands

```bash
.venv313/bin/python -m pytest tests/services/test_daily_ops_report_service.py -q   # 7 passed
.venv313/bin/python -m pytest tests/scheduler/ -q                                   # 139 passed (잡 ID 테스트 갱신 포함)
.venv313/bin/python -m pytest tests/core/ tests/strategy/policy/ -q                 # 27 passed (설정 추가 영향)
.venv313/bin/python scripts/dev/run_daily_ops_report.py --no-llm                    # 실DB 생성 확인
.venv313/bin/python scripts/dev/run_daily_ops_report.py                             # LLM 코멘터리 포함 확인
python scripts/check_task_harness.py --strict-current
```

## Manual Checks

- runtime/reports/daily_ops_20260612.{json,md} 생성·내용 확인 (표 렌더링, 플래그, 인시던트 8건 표면화, LLM 코멘터리 4개 소제목).
- 서버 재시작 후 scheduler에 daily_ops_report 잡 등록 확인.
- 브로커/주문/청산 로직 무변경 (집계는 전부 읽기 전용).
