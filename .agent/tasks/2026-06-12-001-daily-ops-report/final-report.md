# Final Report

일일 운영 종합 리포트 체계를 구축했다. 장마감 매매 보고(daily_report)와 별개로,
시스템 전 기능의 하루치 운영 데이터를 평일 16:40에 자동 집계해 사람이 읽기 좋은
Markdown(+JSON)으로 `runtime/reports/daily_ops_<YYYYMMDD>.{md,json}`에 누적한다.

## Changed

- `services/daily_ops_report_service.py` (신규)
  - 섹션: 매매 funnel / 의사결정 게이트(decision_event) / LLM·AI 스킵 / 잡 / 에러(24h 이벤트 + 미해결 인시던트) / 리소스 / 뉴스 / 에이전트 활동.
  - 섹션별 독립 수집 (실패는 error 필드 + alert 플래그로 고립), 전일 JSON 대비 delta, 이상 신호 플래그(🔴/🟡).
  - LLM 코멘터리(옵션): 운영 요약 / 병목·이상 / 개선 제안 / **적용 검토할 신기능·최신 기법** 4단 구조, 실패해도 리포트 생성 지속.
- `scheduler/jobs/daily_ops_report_job.py` (신규) + `scheduler/scheduler.py`: 평일 16:40 cron 등록 (`daily_ops_report`).
- `core/config.py`: `DAILY_OPS_REPORT_ENABLED`, `DAILY_OPS_REPORT_LLM_ENABLED`.
- `scripts/dev/run_daily_ops_report.py` (신규): 수동/백필 실행기 (`--date`, `--no-llm`).
- `tests/services/test_daily_ops_report_service.py` (신규 7건), `tests/scheduler/test_scheduler_runtime_paths.py` 잡 ID 갱신.
- `.agent/project-card.md`: 병목/개선 분석 작업의 진입점으로 등록.
- `.gitignore`: `.understand-anything/` 로컬 캐시 제외 규칙.

## Behavior Impact

- Intended live order behavior change: none. 집계는 전부 읽기 전용 쿼리.
- 스케줄러에 read-only 잡 1개 추가 (16:40, 기존 잡들과 시간 충돌 없음).

## Verification

- `tests/services/test_daily_ops_report_service.py`: 7 passed
- `tests/scheduler/`: 139 passed (잡 ID 테스트 포함)
- `tests/core/ tests/strategy/policy/`: 27 passed (설정 추가 영향권)
- 실DB 검증: `run_daily_ops_report.py` 실행 → daily_ops_20260612.{json,md} 생성,
  미해결 인시던트 8건 플래그 표면화, LLM 코멘터리(4단 구조) 포함 확인
- `task_harness.py verify`: 7항목 전부 passed

## Known Issues / Follow-ups

- 리포트 외부 발송(텔레그램 등)은 로드맵 O1과 함께.
- 리포트 파일 보존 정책 미설정 (누적 시 observability_maintenance에 정리 추가).
- 서버 재시작 전까지 기존 프로세스에는 새 잡이 등록되지 않음 → 재시작으로 활성화.
