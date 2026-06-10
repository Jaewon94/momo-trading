# Final Report

뉴스 판단 governance 중앙화 작업을 완료했다. 이번 변경은 뉴스 기능을 즉시
강한 매매 신호로 바꾸는 작업이 아니라, 향후 장마감 리서치/LLM 활용을 안전하게
키울 수 있도록 정책, 문서, 테스트 진입점을 한 곳으로 묶는 리팩터링이다.

## Changed

- `strategy/news_intelligence_policy.py`
  - horizon별 뉴스 threshold/freshness multiplier, lookback, prompt item,
    pressure candidate cap을 제공하는 중앙 정책 추가.
  - 뉴스 severity keyword, event taxonomy, after-hours research guardrail 계약 추가.
- `services/news_signal_service.py`
  - 기존 내부 horizon profile/severity keyword를 중앙 정책 참조로 교체.
- `services/news_context_service.py`
  - Tier prompt에 들어가는 뉴스 lookback/item limit을 중앙 정책에서 읽도록 변경.
- `agent/market_scanner.py`
  - 후보 뉴스 압력 계산 대상 수를 중앙 정책에서 읽도록 변경.
- `strategy/policy/registry.py`, `docs/architecture/trading-policy-governance.md`
  - `news_intel` owner에 horizon policy와 after-hours research guardrail을 포함.
- `docs/architecture/news-intelligence-governance.md`
  - 장마감 뉴스 리서치, 비용 제한, item-id citation, outcome/shadow metric,
    prompt injection 방어 원칙 문서화.
- `AGENTS.md`, `.agent/project-card.md`
  - future agent가 뉴스/공시/웹/LLM 리서치 변경 시 중앙 정책과 문서를 함께 보도록
    진입점 추가.

## Behavior Impact

- Intended live order behavior change: none.
- after-hours LLM research job remains disabled by default.
- News/LLM output does not place orders directly.
- Existing news gate/context/scanner behavior is routed through a shared policy
  module, but thresholds and candidate caps are behavior-preserving.

## Verification

- `.venv313/bin/python -m pytest tests/strategy/test_news_intelligence_policy.py tests/services/test_news_signal_service.py tests/services/test_news_context_service.py tests/agent/test_market_scanner.py tests/strategy/policy/test_policy_registry.py tests/strategy/policy/test_settings_catalog.py -q`: 30 passed
- `.venv313/bin/python -m py_compile agent/market_scanner.py services/news_signal_service.py services/news_context_service.py strategy/news_intelligence_policy.py strategy/policy/registry.py`: passed
- `python scripts/check_task_harness.py --strict-current`: passed after state status correction
- `python scripts/change_harness.py ...`: risk high/protected yes, required focused tests and runtime integrity noted
- `git diff --check`: passed
- `python scripts/check_runtime_integrity.py --days 7`: passed, runtime status OK
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-013-news-intelligence-governance`: passed
- Restart verification:
  - `bash start.sh -d` started then exited under the exec tool process lifecycle, without traceback.
  - Restarted persistently in `tmux` session `momo-trading-live` with `bash start.sh`.
  - `curl -s http://127.0.0.1:9000/api/v1/health`: SUCCESS
  - `/api/v1/admin/system/status`: scheduler running, agent running, news polling OK, market session `NXT_AFTER`, auto trading false.
  - `python scripts/check_runtime_integrity.py --days 7`: passed after restart.

## Remaining Work

- Implement actual after-hours research memo only after storage schema, cost
  telemetry, source/item citation, and shadow outcome metrics are designed.
- Add classifier/enrichment that maps news items into the central event taxonomy.
- Add admin preview/reporting for news quality, match reason, and forward return
  impact before increasing news trading weight.
