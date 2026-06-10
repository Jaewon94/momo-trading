# Final Report

## Outcome

구현 완료. 단기, 중기, 장기 스캔이 각각 다른 주기와 후보 필터, 뉴스 컨텍스트, 일봉 범위를 사용하도록 연결했다.

브로커 액션, 런타임 DB 변경, 마이그레이션, 주문 리셋, 강제 청산은 실행하지 않았다.

## Implemented

- `strategy/horizon_scan_policy.py`에 SHORT/MID/LONG별 스캔 프로필을 추가했다.
- 단기는 기존 장중 반복 스캔 흐름을 유지하고, 중기는 매일 1회, 장기는 주 1회 스케줄러 작업으로 분리했다.
- LLM 전 후보 필터를 horizon별로 다르게 적용한다. 기본값은 SHORT 30개, MID 60개, LONG 100개 후보를 본 뒤 각각 선별한다.
- 뉴스 컨텍스트는 horizon별 lookback과 prompt item 수를 사용한다. 기본값은 SHORT 24시간, MID 7일, LONG 30일이다.
- TradingAgent 분석 경로에 `target_horizon_hint`를 전달해 중기/장기 후보가 단기 기준으로 과도하게 재분류되지 않도록 했다.
- SHORT 스캔에 남아 있던 기존 중장기 편향 문구를 제거하고, SHORT/MID/LONG별 운용 방향이 각각 다르게 전달되도록 고쳤다.
- 런타임 설정, 정책 레지스트리, 설정 카탈로그, `.env.example`, 아키텍처 문서를 함께 갱신했다.

## Verification

Passed:

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/test_horizon_scan_policy.py tests/services/test_candidate_scoring_service.py tests/services/test_news_context_service.py tests/services/test_deterministic_prompt_context_service.py tests/agent/test_market_scanner.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/policy/test_settings_catalog.py tests/services/test_runtime_settings_service.py -q
.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/api/test_admin_manual_actions.py -q
.venv313/bin/python -m pytest tests/strategy/policy/test_policy_registry.py -q
.venv313/bin/python -m py_compile agent/trading_agent.py agent/market_scanner.py scheduler/scheduler.py services/deterministic_prompt_context_service.py services/news_context_service.py services/candidate_scoring_service.py strategy/horizon_scan_policy.py strategy/policy/registry.py strategy/policy/settings_catalog.py core/config.py core/runtime_settings.py
```

Focused test results:

- `189 passed in 34.78s`
- `18 passed in 1.34s`
- `4 passed in 0.65s`

Task harness note:

- `python scripts/task_harness.py verify 2026-06-10-011-horizon-scheduled-news-analysis` failed because the system Python 3.14 environment did not have `pytest`.
- `uv run python scripts/task_harness.py verify 2026-06-10-011-horizon-scheduled-news-analysis` then failed because `final-report.md` was required for a terminal task. This report resolves that artifact gap.
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-011-horizon-scheduled-news-analysis` passed.

Operational check:

```bash
python scripts/check_runtime_integrity.py --days 7
```

Result: failed.

- `trading_enabled=True`
- `autonomy=AUTONOMOUS`
- `effective_order_mode=FULL`
- `order_reconciliation=FAIL`
- `db_pending=1`
- `db_only_stale=1`
- `broker_missing_open_buys=1`

## Remaining Risks

- 장기 판단에는 아직 DART/재무제표/실적 컨센서스 같은 정량 펀더멘털 컨텍스트가 붙지 않았다. 이번 작업은 기존 뉴스 수집과 가격/차트 데이터 범위 확장까지다.
- 재시작 전에는 런타임 설정값이 실제 운영 프로세스에 반영되지 않는다.
- 기존 런타임 주문 정합성 이슈가 실제로 남아 있다. 이번 코드 변경과 별개로 운영 복구 작업이 필요하다.

## Restart Status

재시작하지 않았다. 현재 서비스가 `FULL`/`AUTONOMOUS` 상태이고 주문 정합성 검증이 실패했기 때문에, 재시작은 stale pending-order 정리 또는 명시적 위험 수용 이후에 진행해야 한다.
