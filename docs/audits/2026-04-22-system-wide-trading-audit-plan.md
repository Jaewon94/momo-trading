# MOMO Trading 전체 시스템 감사 계획

> 상태: 사용자 확인 전 초안입니다. 이 문서가 승인되기 전에는 코드 수정, 런타임 설정 변경, 전략 파라미터 튜닝, 기능 제거를 하지 않습니다.

## 목표

자동매매 시스템 전체를 처음부터 끝까지 감사해서, 아래 항목에 대한 우선순위 개선 로드맵을 만듭니다.

- 가치가 낮거나 위험한 기능 제거 또는 기본 비활성화
- 런타임 성능과 안정성 개선
- 주문 실행, 체결 확인, 리스크 제어 개선
- 전략 평가와 기대 수익 품질 개선
- 앞으로의 변경을 감이 아니라 증거로 판단할 수 있는 관측성 개선

이 문서는 일부러 범위를 넓게 잡았습니다. 첫 산출물은 구현이 아니라 증거, 문제점, 실행 계획입니다.

## 하지 않을 것

- 어떤 변경도 수익을 보장한다고 말하지 않습니다. 목표는 위험 대비 기대값 개선, 손실 제한, 측정 신뢰도 향상입니다.
- 아웃오브샘플 또는 워크포워드 검증 없이 전략 파라미터를 튜닝하지 않습니다.
- 명시적 승인 없이 운영 중인 매매 동작을 바꾸지 않습니다.
- 별도 승인 없이 라이브 봇이 도는 중에 브로커/주문 로직을 바꾸지 않습니다.

## 진행 방식

증거 우선으로 순서대로 확인합니다.

1. 코드, DB, 런타임 메트릭, 최근 계좌/주문 기록으로 현재 동작을 맵핑합니다.
2. 각 하위 시스템을 `P0~P3` 심각도로 평가합니다.
3. 안전성 수정, 성능 개선, 매매 성과 실험을 분리합니다.
4. 현재 구현을 외부 베스트 프랙티스와 비교합니다.
5. 최종 실행 계획을 작성하고, 사용자 확인 후에만 구현합니다.

## 참고 기준

아래 기준을 그대로 복사하지는 않습니다. 다만 감사 관점의 기준선으로 사용합니다.

- SEC Rule 15c3-5: 사전 주문 리스크 제어, 자본/신용 한도, 오류 주문/중복 주문 방지, 제한 종목 차단, 사후 체결 감시를 요구합니다.
  출처: https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access
- FINRA 알고리즘 트레이딩 가이드: 알고리즘 전략의 리스크 평가, 코드 개발/테스트, 배포 통제, 모니터링을 강조합니다.
  출처: https://www.finra.org/rules-guidance/key-topics/algorithmic-trading
- FINRA Market Access Rule: 약한 사전 주문 한도, 비합리적 한도, 중복/오류 주문 통제 부족, 감시 부재를 주요 문제로 봅니다.
  출처: https://www.finra.org/rules-guidance/guidance/reports/2025-finra-annual-regulatory-oversight-report/market-access-rule
- SEC Market Access FAQ: 자동 주문 오류가 빠르게 누적될 수 있으므로 모든 주문에 사전 리스크 통제가 필요하다는 관점을 제공합니다.
  출처: https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0
- KRX Market Surveillance: 조작, 위법 행위, 규칙 위반, 계좌/패턴 기반 감시, market replay 같은 사후 감시 관점을 제공합니다.
  출처: https://global.krx.co.kr/contents/GLB/04/0402/0402030000/GLB0402030000.jsp
- 대한민국 자본시장과 금융투자업에 관한 법률: 한국 시장에서의 투자자 보호, 시장 공정성, 거래 질서, 불공정거래 행위 관점의 기준선으로 사용합니다.
  출처: https://elaw.klri.re.kr/eng_mobile/ganadaDetail.do?hseq=73666&key=FINANCIAL+INVESTMENT+SERVICES+AND+CAPITAL+MARKETS+ACT&param=F&type=abc
- NIST AI RMF: AI 시스템 리스크를 거버넌스, 맥락 파악, 측정, 완화 관점으로 관리합니다. LLM 의사결정 통제 기준으로 사용합니다.
  출처: https://www.nist.gov/itl/ai-risk-management-framework
- NIST SSDF: 보안 취약점을 줄이기 위한 안전한 소프트웨어 개발 프레임워크입니다. 시크릿, 의존성, 릴리즈, 변경 통제 기준으로 사용합니다.
  출처: https://www.nist.gov/node/1694946
- OWASP Secrets Management: API 키/토큰/계좌 정보 같은 시크릿의 생성, 회전, 폐기, 접근 제어, 감사, 사고 대응 기준입니다.
  출처: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Bailey, Borwein, López de Prado, Zhu의 Backtest Overfitting 논문: 투자 백테스트에서 일반적인 hold-out 방식이 불안정할 수 있음을 지적합니다.
  출처: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Bailey와 López de Prado의 Deflated Sharpe Ratio 논문: 다중 테스트, 선택 편향, 비정규 수익률, 백테스트 과최적화를 보정하는 관점을 제공합니다.
  출처: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

## 현재까지의 예비 증거

2026-04-22 기준 읽기 전용으로 확인한 내용입니다.

- 런타임 DB에는 `trade_results`, `orders`, `portfolio_holdings`, `account_equity_snapshots`, `agent_activity_logs`, `execution_metrics`, `error_incidents`, `strategy_signals`, `recommendations`, `news_items`가 있습니다.
- 재검증에서 추가 확인한 DB/모델 감사 대상은 `runtime_settings`, `trading_rules`, `account_day_baselines`, `error_events`, `resource_snapshots`, `resource_hourly_rollups`, `execution_metric_hourly_rollups`, `daily_reports`, `market_data_daily`, `market_snapshots`, `analysis_results`, `strategy_configs`, `stocks`, `portfolios`입니다.
- `README.md` 기준 핵심 흐름은 `스케줄러 -> 스캐너 -> 스크리너 -> 차트/LLM 분석 -> 최종 검토 -> 전략/리스크 -> 주문`입니다.
- 최근 수동 점검에서 매매와 주문은 활발했지만, `trade_results`의 실현 손익은 대부분 0이고 계좌 스냅샷의 평가손익은 변하고 있었습니다. 성과 측정 신뢰도가 우선 감사 대상입니다.
- 최근 활동 로그에서 `PENDING_CONFIRM`, 브로커 제한, 주문 실패가 보였습니다. 주문 생명주기와 체결 대사가 우선 감사 대상입니다.
- 뉴스 기능은 운영 중 부하/복잡성 때문에 꺼졌습니다. 다시 켜기 전에 실제 성과 기여도와 비용을 평가해야 합니다.
- 코드 대조 결과 `repositories/`, `models/`, `alembic/versions/`는 감사 증거의 source of truth로 포함해야 합니다. 서비스 계층만 보면 DB 상태 전이와 마이그레이션 이력을 놓칠 수 있습니다.
- 브로커 transport는 adapter뿐 아니라 `trading/mcp_client.py`, `trading/kis_websocket.py`, `docker/kis-mcp/`까지 포함해야 합니다. SSE 재연결, rate limit, 미확인 주문 복구가 주문 안정성에 직접 연결됩니다.

위 항목은 최종 결론이 아니라 감사 가설입니다. 실제 감사에서 검증해야 합니다.

## 감사 영역

### 1. 주문 생명주기와 브로커 연동

확인할 파일:

- `agent/decision_maker.py`
- `trading/order_executor.py`
- `trading/account_manager.py`
- `trading/adapters/base.py`
- `trading/adapters/kiwoom_adapter.py`
- `trading/adapters/kis_adapter.py`
- `trading/kiwoom_clients.py`
- `trading/mcp_client.py`
- `trading/kis_websocket.py`
- `trading/models.py`
- `trading/enums.py`
- `scheduler/jobs/portfolio_sync_job.py`
- `services/trading_service.py`
- `services/broker_smoke_service.py`
- `services/manual_trade_service.py`
- `services/order_service.py`
- `repositories/order_repository.py`
- `repositories/trade_result_repository.py`
- `repositories/portfolio_repository.py`
- `models/order.py`
- `models/trade_result.py`
- `models/portfolio.py`
- `tools/broker_smoke.py`
- `docker/kis-mcp/`
- `tests/trading/`
- `tests/agent/test_decision_maker.py`
- `tests/scheduler/test_portfolio_sync_job.py`
- `tests/services/test_trading_service.py`
- `tests/services/test_broker_smoke_service.py`
- `tests/api/test_admin_account_routes.py`
- `tests/api/test_admin_trade_routes.py`

확인 질문:

- 주문 상태가 `제출 -> 접수 -> 부분체결 -> 체결 -> 취소 -> 거절`로 명확히 관리되는가?
- 브로커 오류 코드가 재시도 가능, 최종 실패, 제한 종목, 현금 부족, 매도 가능 수량 부족, 네트워크 오류로 분류되는가?
- 중복 주문 차단이 단순 pending 체크가 아니라 종목/매수매도/주문 의도 단위로 동작하는가?
- `PENDING_CONFIRM` 상태가 오래 방치되지 않고 빠르게 대사되는가?
- 부분 체결과 부분 매도가 lot 단위 손익을 망가뜨리지 않는가?
- 매수/매도 수량이 현금, 보유 수량, 브로커 제약, 현재 미체결 주문을 모두 반영하는가?
- SSE/MCP transport가 끊긴 주문을 정확히 복구하거나 안전하게 실패시키는가?
- 브로커 rate limit, timeout, reconnect가 주문 중복이나 누락을 만들지 않는가?

수집할 증거:

- 주문 상태별 개수와 나이
- `PENDING_CONFIRM` 경과 시간 분포
- 브로커 거절 사유별 빈도
- DB 포지션과 브로커 계좌 스냅샷 차이
- 주문 제출부터 확인/거절/취소까지 걸린 시간

예상 결과:

- 오래된 pending 주문이 거래를 막거나 중복 거래를 유발하면 `P0/P1`
- DB 포지션과 브로커 포지션이 다르면 `P0/P1`
- 거절 주문이 학습/차단 없이 반복되면 `P1`

### 2. 리스크 제어와 자본 배분

확인할 파일:

- `strategy/risk_manager.py`
- `strategy/trading_guard.py`
- `strategy/ai_risk_tuner.py`
- `strategy/trade_horizon.py`
- `strategy/risk_appetite_insights.py`
- `strategy/holding_policy.py`
- `models/trading_rule.py`
- `repositories/account_day_baseline_repository.py`
- `repositories/runtime_setting_repository.py`
- `agent/trading_agent.py`
- `agent/decision_maker.py`
- `services/account_equity_service.py`
- `services/performance_reporting_service.py`
- `services/runtime_settings_service.py`
- `services/runtime_reconfiguration_service.py`
- `tests/strategy/`
- `tests/agent/test_trading_agent_cost_gate.py`
- `tests/agent/test_trading_agent_execution_policy.py`
- `tests/services/test_account_equity_service.py`
- `tests/services/test_performance_reporting_service.py`
- `tests/services/test_runtime_settings_service.py`

확인 질문:

- 주문별, 종목별, 테마/섹터별, 일일 총 노출 한도가 브로커 제출 전에 적용되는가?
- 미체결 주문도 노출 계산에 포함되는가?
- 같은 급등 모멘텀 종목에 반복 매수되는 집중 리스크가 제어되는가?
- 손실 차단 킬스위치가 실현손익, 평가손익, 총자산을 모두 고려하는가?
- 손절, 익절, 트레일링 스탑, 시간 손절, 이벤트 기반 청산이 일관되게 적용되는가?
- 세금, 수수료, 슬리피지가 포지션 사이징 전에 반영되는가?
- `trading_rules`와 runtime settings가 LLM 판단보다 우선되는 deterministic hard rule로 적용되는가?
- cost gate가 과도한 단타/소액 거래를 실질적으로 차단하는가?

수집할 증거:

- 종목별 최대 장중 노출
- 종목/테마/총계 기준 현재 노출 + 미체결 노출
- 총 매수 명목금액 대비 계좌 자산
- 미체결/취소/부분체결에 따른 현금 재사용 위험
- 장중 평가손익 하락 경로
- 리스크 통과 후 거절/스킵된 주문 수
- 주문 수량과 리스크 예산/손절폭의 관계

예상 결과:

- 반복 pending/confirmed 주문으로 총 노출이 커질 수 있으면 `P0`
- 평가손실을 킬스위치가 무시하면 `P1`
- 진입 로직보다 청산 로직이 약하면 `P1`

### 3. 전략과 시그널 품질

확인할 파일:

- `agent/market_scanner.py`
- `agent/stock_screener.py`
- `agent/trading_agent.py`
- `analysis/chart_analyzer.py`
- `analysis/sentiment/news_analyzer.py`
- `analysis/technical/`
- `strategy/stable_short.py`
- `strategy/aggressive_short.py`
- `strategy/base.py`
- `strategy/signal.py`
- `services/strategy_service.py`
- `services/performance_reporting_service.py`
- `repositories/analysis_repository.py`
- `repositories/recommendation_repository.py`
- `repositories/strategy_repository.py`
- `tests/agent/`
- `tests/strategy/`
- `tests/agent/test_trading_agent_news_gate.py`
- `tests/agent/test_trading_agent_market_data.py`
- `tests/agent/test_trading_agent_cycles.py`

확인 질문:

- 어떤 조건으로 종목이 분석 파이프라인에 들어오는가?
- 실패 주문이나 pending 주문 이후 같은 종목 반복 진입이 제어되는가?
- Tier1/Tier2 LLM 승인 과정이 기술적 분석만 쓴 기준선보다 실제로 나은가?
- 이 시스템이 반드시 이겨야 하는 단순 벤치마크는 무엇인가?
- 매수/HOLD/SKIP 결정 이후 5분, 15분, 30분, 1시간, 장마감 수익률이 어떤가?
- 진입에 사용한 투자 horizon과 청산 기준이 일치하는가?
- 특정 급등 패턴에 과도하게 집중되어 있지는 않은가?
- 뉴스 gate, cost gate, execution policy가 strategy decision과 충돌하지 않는가?

수집할 증거:

- 스캔 -> LLM -> 전략 -> 리스크 -> 주문 -> 체결 -> 손익 funnel
- 벤치마크 비교: 거래 안 함, 같은 후보군 랜덤 매수, 스캐너만, 기술적 분석만, LLM만, LLM+리스크
- BUY/HOLD/SKIP 이후 forward return 분포
- Tier1 confidence calibration
- Tier2 승인과 실제 결과의 관계
- 종목 반복 진입 통계
- 시장 국면/투자 horizon별 성과

예상 결과:

- LLM 승인이 기준선보다 낫지 않으면 `P1`
- 급등 후반부 추격 매수가 청산 규칙 없이 반복되면 `P1`
- 스캐너가 노이즈를 많이 만들어 LLM/브로커 리소스를 낭비하면 `P2`

### 4. 성과 측정과 백테스트 신뢰도

확인할 파일:

- `backtesting/engine.py`
- `backtesting/metrics.py`
- `backtesting/report.py`
- `backtesting/data_loader.py`
- `analysis/feedback/performance_tracker.py`
- `analysis/feedback/strategy_tuner.py`
- `services/performance_reporting_service.py`
- `models/`
- `tests/backtesting/`
- `tests/services/test_performance_reporting_service.py`

확인 질문:

- 백테스트가 의사결정 시점에 알 수 있었던 데이터만 사용하는가?
- 거래비용, 세금, 수수료, 슬리피지, 미체결, 상하한가가 모델링되는가?
- 워크포워드 또는 아웃오브샘플 검증이 있는가?
- 여러 전략 조합을 시험한 기록이 남아 선택 편향을 피할 수 있는가?
- 성과 지표가 닫힌 거래 기준인지, 열린 포지션 평가손익까지 포함하는지 명확한가?
- 라이브/모의 성과가 백테스트 가정과 대사되는가?
- 기업 이벤트, 거래정지, 상하한가, survivorship bias가 처리되는가?

수집할 증거:

- 백테스트 가정 목록
- 라이브 슬리피지와 시뮬레이션 슬리피지 차이
- 닫힌 거래 기대값, profit factor, drawdown, tail loss
- 열린 포지션 기준 drawdown, MFE, MAE
- 전략 파라미터 실험 횟수와 선택 기준
- look-ahead leakage 확인을 위한 데이터 가용 시각 점검

예상 결과:

- 리포트는 수익이라는데 계좌는 손실이면 `P0/P1`
- 백테스트가 비용/체결 불확실성을 무시하면 `P1`
- 인샘플 튜닝만으로 전략을 고르면 `P1`

### 5. LLM 파이프라인 안정성과 가치

확인할 파일:

- `analysis/llm/llm_factory.py`
- `analysis/llm/selection_policy.py`
- `analysis/llm/codex_provider.py`
- `analysis/llm/claude_code_provider.py`
- `analysis/llm/ollama_provider.py`
- `analysis/llm/model_catalog.py`
- `analysis/llm/prompts/`
- `services/llm_runtime_recommendation_service.py`
- `services/llm_usage_service.py`
- `tests/analysis/`
- `tests/services/test_llm_runtime_recommendation_service.py`
- `tests/services/test_llm_usage_service.py`
- `tests/frontend/test_settings_llm_concurrency_state.test.js`

확인 질문:

- CLI timeout cascade를 막을 만큼 LLM 동시성이 제어되는가?
- fallback provider로 바뀌어도 의사결정 의미가 유지되는가?
- prompt가 수량/가격 결정에 너무 많은 자유도를 주는가?
- LLM confidence가 실제 forward return과 맞는가?
- prompt/model 변경이 성과 변화와 연결될 수 있게 버전 관리되는가?
- 위험한 LLM 출력을 주문 전에 거부하는 deterministic guardrail이 있는가?

수집할 증거:

- LLM latency, timeout, fallback, 성공률 분포
- 모델/provider별 의사결정 결과
- LLM confidence와 forward return 관계
- prompt 버전별 성과
- 잘못된 형식 또는 정책 위반 LLM 출력 비율

예상 결과:

- LLM 불안정성이 장중 의사결정을 막으면 `P1`
- LLM sizing이 deterministic risk rule을 우회하면 `P1`
- 비싼 LLM 단계가 funnel 품질을 높이지 못하면 `P2`

### 6. 뉴스와 공시 파이프라인

확인할 파일:

- `services/news_polling_service.py`
- `services/news_ingest_service.py`
- `services/news_signal_service.py`
- `services/news_runtime_service.py`
- `services/news_translation_service.py`
- `services/news_translation_backfill_service.py`
- `services/news_reporting_service.py`
- `services/open_dart_disclosure_service.py`
- `services/krx_kind_disclosure_service.py`
- `services/yonhap_news_service.py`
- `services/bloomberg_news_service.py`
- `services/cnbc_news_service.py`
- `services/nasdaq_news_service.py`
- `services/investing_news_service.py`
- `services/seeking_alpha_news_service.py`
- `analysis/sentiment/news_analyzer.py`
- `repositories/news_item_repository.py`
- `models/news_item.py`
- `scheduler/scheduler.py`
- `api/routes/admin.py`
- `tests/services/test_news_*`
- `tests/api/test_admin_news_routes.py`
- `tests/agent/test_trading_agent_news_gate.py`
- `tests/agent/test_trading_agent_news_event.py`

확인 질문:

- 뉴스가 매수 필터링에 실제로 기여하는가, 아니면 지연/부하만 늘리는가?
- 소스 신뢰도, 중복 제거, cooldown, stale news 처리가 잘 되는가?
- 국내/해외/번역 설정 변경이 재시작 없이 안전하게 적용되는가?
- 뉴스 반영 거래가 일반 거래보다 나은가?
- 일부 뉴스 소스는 제거하거나 기본 비활성화해야 하는가?
- 소스별 failure threshold/cooldown이 실제로 noisy source를 차단하는가?
- 뉴스 수집, 번역, sentiment, trade gate가 서로 같은 freshness 기준을 사용하는가?

수집할 증거:

- 소스별 fetch 성공/실패
- provider별 번역 비용/지연
- 뉴스 영향 거래 vs 일반 거래 성과
- 뉴스로 차단된 거래 수와 차단이 실제로 유익했는지

예상 결과:

- 뉴스가 중복 재분석 루프나 중복 부하를 만들면 `P1`
- 뉴스 가치가 증명되지 않으면 계속 비활성화가 적절하며 `P2`
- 번역 지연으로 stale decision이 생기면 `P2`
- 소스가 noisy하거나 거의 안 쓰이면 active set 제거 후보 `P3`

### 7. 스케줄러, 실시간 이벤트, 동시성

확인할 파일:

- `scheduler/scheduler.py`
- `scheduler/market_calendar.py`
- `realtime/monitor.py`
- `realtime/event_detector.py`
- `realtime/stream_manager.py`
- `realtime/stream_backend.py`
- `realtime/adapters/`
- `core/events.py`
- `services/runtime_reconfiguration_service.py`
- `tests/scheduler/`
- `tests/realtime/`
- `tests/agent/test_trading_agent_cycles.py`
- `tests/services/test_runtime_reconfiguration_service.py`

확인 질문:

- 이벤트 기반 분석과 정기 스캔이 겹쳐 중복 주문을 만들 수 있는가?
- lock 범위가 job, symbol, account 단위로 적절한가?
- 런타임 설정 변경 후 스케줄러 재시작이 안전한가?
- 실시간 실패가 polling fallback으로 안전하게 degrade되는가?
- 이벤트 감지 threshold가 유용한 신호를 주는가, 아니면 급등 추격을 과도하게 만드는가?

수집할 증거:

- 동시 실행 job timeline
- 이벤트 발생부터 주문까지 latency
- 같은 종목 반복 분석 빈도
- stream reconnect와 polling fallback 기록

예상 결과:

- 동시 job이 aggregate risk check를 우회하면 `P0/P1`
- 이벤트 기반 거래가 이미 끝난 급등을 추격하면 `P1`
- 스케줄러 노이즈가 LLM/브로커 자원을 낭비하면 `P2`

### 8. 관측성, 인시던트, 운영

확인할 파일:

- `services/observability_service.py`
- `services/observability_reporting_service.py`
- `services/observability_maintenance_service.py`
- `services/error_capture_service.py`
- `services/error_incident_service.py`
- `services/system_preflight_service.py`
- `services/broker_runtime_service.py`
- `services/runtime_backup_service.py`
- `repositories/error_event_repository.py`
- `repositories/error_incident_repository.py`
- `repositories/execution_metric_repository.py`
- `repositories/resource_snapshot_repository.py`
- `models/error_event.py`
- `models/error_incident.py`
- `models/execution_metric.py`
- `models/resource_snapshot.py`
- `models/resource_hourly_rollup.py`
- `models/execution_metric_hourly_rollup.py`
- `scripts/dev/start.sh`
- `start.sh`
- `runtime/`
- `tests/services/test_observability_*`
- `tests/scripts/`

확인 질문:

- 운영자가 시스템이 안전한지, degraded인지, 멈췄는지 알 수 있는가?
- stale PID/log 문제가 아직 있는가?
- 인시던트가 해결되는가, 아니면 계속 쌓이기만 하는가?
- 브로커/API/LLM 오류가 행동 가능한 수준으로 그룹핑되는가?
- 일일 리포트와 Admin 화면이 계좌 스냅샷과 같은 사실을 보여주는가?

수집할 증거:

- component별 인시던트 개수와 age
- 수정 후에도 반복되는 오류
- PID/log freshness와 실제 프로세스 상태
- Admin API health와 dashboard 일관성

예상 결과:

- 운영자가 상태를 오해할 수 있으면 `P1`
- 오래된 open incident가 새 심각 오류를 가리면 `P1`
- `start.sh logs`가 stale 로그를 보여주면 `P2`

### 9. 보안, 시크릿, 릴리즈 안전성

확인할 파일:

- `.env.example`
- `.gitignore`
- `core/config.py`
- `services/runtime_settings_service.py`
- `services/runtime_reconfiguration_service.py`
- `services/runtime_backup_service.py`
- `trading/kiwoom_rest_client.py`
- `trading/kis_api.py`
- `trading/mcp_client.py`
- `analysis/llm/*provider.py`
- `scripts/dev/start.sh`
- `start.sh`

확인 질문:

- 브로커 인증값, LLM 토큰, GitHub 토큰, 계좌번호, 런타임 시크릿이 소스와 로그에서 제외되는가?
- 실거래에 영향을 주는 런타임 설정 변경은 누가/언제/무엇을 바꿨는지 감사 가능한가?
- 실수로 노출된 시크릿을 회전/폐기하는 절차가 있는가?
- production-like 설정이 커밋이나 dashboard에 노출되지 않는가?
- 의사결정을 재현할 수 있을 만큼 dependency와 CLI 버전이 고정/기록되는가?

수집할 증거:

- tracked file과 로그의 secret-like pattern
- 런타임 설정 변경 이력
- activity/error 로그의 토큰/계좌 정보 노출 여부
- dependency pinning과 CLI version 기록

예상 결과:

- 시크릿이나 계좌 인증값이 추적되거나 노출되면 `P0`
- live-trading 설정 변경에 durable audit trail이 없으면 `P1`
- 런타임 dependency version이 재현 불가능하면 `P2`

### 10. 데이터 품질과 시장 마이크로구조

확인할 파일:

- `services/market_data_service.py`
- `scheduler/jobs/market_data_job.py`
- `analysis/chart_analyzer.py`
- `analysis/technical/`
- `trading/symbols.py`
- `backtesting/data_loader.py`
- `models/market_data.py`
- `models/stock.py`
- `repositories/market_data_repository.py`
- `repositories/stock_repository.py`
- `tests/agent/test_trading_agent_market_data.py`
- `tests/backtesting/test_data_loader.py`

확인 질문:

- 종목 코드가 `A` prefix 유무와 관계없이 일관되게 정규화되는가?
- 현재가, 분봉, 일봉, 계좌 스냅샷의 시간이 맞는가?
- 오래된 가격으로 주문 수량/손절/목표가를 계산하지 않는가?
- 거래정지, 제한 종목, 상한가/하한가, 모의투자 제한이 모델에 반영되는가?
- 시장 데이터 누락과 API 실패가 전략 계층에 보이는가?

수집할 증거:

- symbol normalization mismatch
- 의사결정 시점의 quote/candle age
- 종목/일자별 OHLCV 누락률
- 제한 종목 또는 시장 상태로 인한 주문 실패

예상 결과:

- stale price나 코드 불일치로 주문이 나갈 수 있으면 `P0/P1`
- symbol normalization 문제로 포지션/주문 대사가 틀리면 `P1`
- 데이터 누락이 분석 자원을 낭비하거나 불필요한 skip을 만들면 `P2`

### 11. Admin UI와 수동 제어

확인할 파일:

- `admin/static/index.html`
- `admin/static/js/`
- `api/routes/admin.py`
- `tests/frontend/`
- `tests/api/test_admin_*`

확인 질문:

- 수동 제어가 안전하고 명시적이며 되돌릴 수 있는가?
- 위험한 action과 읽기 전용 action이 명확히 분리되는가?
- 미체결 주문과 보유 종목이 중복 액션을 막을 수 있게 표시되는가?
- 설정 변경이 안전한 reconfiguration flow를 거치는가?
- `admin/static/js/*_state.js` 모듈 테스트가 실제 DOM action과 계속 일치하는가?

수집할 증거:

- UI state test coverage
- settings apply flow와 direct settings update 차이
- manual trade action 경로

예상 결과:

- UI action이 의도치 않게 live trading을 바꾸면 `P1`
- UI 라벨이 pending과 filled 상태를 흐리면 `P2`

## 기능 제거와 단순화 기준

아래 중 하나 이상에 해당하면 제거/비활성화 후보로 둡니다.

- 위험 대비 수익, 손실 감소, 운영 안전성에 기여한다는 증거가 없다.
- 시간 민감한 의사결정에 latency를 추가하지만 가치가 측정되지 않는다.
- 운영자에게 혼란이나 거짓 확신을 준다.
- 브로커/계좌 source of truth와 다른 중복 데이터 경로를 만든다.
- 반복 실패가 있고 owner/runbook이 없다.
- 이론상 유용하지만 테스트, 메트릭, dashboard로 가치가 증명되지 않았다.
- LLM/뉴스 하위 시스템보다 deterministic rule이나 리포트로 대체하는 편이 낫다.

바로 삭제하지 않고 아래 중 하나로 분류합니다.

- `즉시 제거`: 의존성이 없다는 테스트가 있는 dead code 또는 unused UI
- `기본 비활성화`: 가능성은 있지만 불안정하거나 가치가 증명되지 않은 기능
- `유지하되 harden`: 유용하지만 안전장치가 부족한 기능
- `실험`: 가능성은 있지만 A/B 또는 shadow mode 측정이 필요한 기능

## 감사 중 실행할 읽기 전용 쿼리 예시

```sql
SELECT status, side, COUNT(*) AS count
FROM trade_results
GROUP BY status, side;

SELECT status, side, COUNT(*) AS count, SUM(quantity * COALESCE(price, filled_price, 0)) AS notional
FROM orders
GROUP BY status, side;

SELECT captured_at, total_asset, cash, stock_value, total_unrealized_pnl, pending_order_count
FROM account_equity_snapshots
ORDER BY captured_at DESC
LIMIT 100;

SELECT component, operation, severity, status, occurrence_count, last_seen_at, last_message
FROM error_incidents
ORDER BY last_seen_at DESC;

SELECT activity_type, phase, symbol, created_at, summary, error_message
FROM agent_activity_logs
ORDER BY created_at DESC
LIMIT 500;

SELECT key, value_json, updated_at
FROM runtime_settings
ORDER BY updated_at DESC;

SELECT rule_type, strategy_type, param_name, param_value, is_active, expires_at, applied_count
FROM trading_rules
ORDER BY created_at DESC;

SELECT component, operation, severity, created_at, message
FROM error_events
ORDER BY created_at DESC
LIMIT 200;

SELECT symbol, current_price, change_rate, updated_at
FROM market_snapshots
ORDER BY updated_at DESC
LIMIT 100;

SELECT source, status, sentiment, relevance_score, published_at, created_at
FROM news_items
ORDER BY created_at DESC
LIMIT 200;
```

## 점수 기준

심각도:

- `P0 Blocking`: 통제되지 않은 노출, 중복 주문, 거짓 손익, 위험한 운영 상태를 만들 수 있음
- `P1 Major`: 리스크 제어, 체결 품질, 성과 측정에 실질적 악영향
- `P2 Minor`: 비효율적이거나 시끄럽지만 즉시 위험하지는 않음
- `P3 Polish`: 편의성/정리 수준

하위 시스템 점수:

- `0`: 안전하지 않거나 측정 불가
- `1`: 큰 결함 있음
- `2`: 부분적으로 통제됨
- `3`: 대부분 통제되지만 알려진 결함 있음
- `4`: 증거 기반으로 강하게 운영됨

## 산출물

### 산출물 1: 증거 패키지

경로: `docs/audits/2026-04-22-system-wide-trading-audit-evidence.md`

포함 내용:

- 아키텍처 맵
- 메트릭 스냅샷
- DB 쿼리 결과 요약
- 파일/라인 근거
- 외부 기준 메모

### 산출물 2: 문제점 보고서

경로: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`

포함 내용:

- P0-P3 문제 목록
- 영향받는 파일
- 운영 영향
- 증거
- 권고안
- 제거, harden, optimize, experiment 중 분류

### 산출물 3: 승인 가능한 실행 계획

경로: `docs/superpowers/plans/2026-04-22-system-wide-trading-improvement-roadmap.md`

포함 내용:

- 순서가 정해진 작업 목록
- 먼저 작성할 테스트
- 수정할 파일
- rollout/rollback 계획
- 런타임 안전 체크
- 커밋 단위

이 산출물이 구현 전 마지막 확인 지점입니다. 명시적 승인 후에만 구현합니다.

## 제안 감사 단계

### Phase 0: 안전 동결과 기준선 확보

- 감사 중 봇을 계속 거래하게 둘지 확인
- 최신 계좌 스냅샷, DB 스냅샷, 런타임 설정, git commit 확보
- 뉴스/오프라인 기능과 live trading 설정 표시
- 현재 open orders, pending confirmations, 브로커/API 가용성 캡처
- 코드 변경 없음

### Phase 1: Source of Truth와 데이터 무결성

- 계좌 자산, 포지션, 주문, 체결, PnL의 기준 source of truth 확정
- 종목 코드 정규화와 stale market data 감사
- 깊은 전략 분석 전에 P0 문제 먼저 도출

### Phase 2: 주문과 리스크 무결성

- 주문 상태 전이와 브로커 대사 감사
- 포지션 사이징, pending exposure, drawdown control 감사
- P0/P1 안전 문제 우선 도출

### Phase 3: 성과 측정 진실성

- `trade_results`, `orders`, 브로커 스냅샷, equity snapshots 대사
- realized/unrealized PnL 신뢰성 판단
- canonical PnL 모델 정의

### Phase 4: 전략 가치 검증

- scanner -> LLM -> strategy -> risk -> order -> fill -> forward return funnel 구축
- 진입/청산 품질과 반복 종목 행동 평가
- 제거 가능한 저가치 단계 식별

### Phase 5: 백테스트와 실험 위생

- 백테스트 가정 검토
- walk-forward validation, 거래비용/슬리피지, 과최적화 방지 계획 추가
- 필요한 benchmark strategy 정의

### Phase 6: LLM, 뉴스, 런타임 비용

- LLM/뉴스의 가치와 latency/cost/failure 비교
- 증명되지 않은 기능의 비활성화, 단순화, gating 권고

### Phase 7: 보안, 운영, Admin

- 시크릿, health, logs, incidents, settings apply, PID tracking, manual controls 감사
- 운영자가 오해할 수 있는 부분 식별

### Phase 8: 로드맵 작성

- 모든 문제를 안전성, 기대값, 구현 리스크, 되돌리기 쉬움 기준으로 정렬
- 승인 가능한 구현 계획 작성

## 실행 전 확인 질문

구현 전에 반드시 확인합니다.

1. 감사 중 live bot을 계속 거래하게 둘까요, 아니면 read-only / semi-auto로 둘까요?
2. 감사 중 브로커 read-only API를 호출해 실시간 계좌 스냅샷을 봐도 될까요?
3. 감사가 끝날 때까지 뉴스 기능은 계속 꺼둘까요?
4. 개선 우선순위는 손실 방어를 먼저 둘까요, 기대수익 실험을 먼저 둘까요?
5. 최종 로드맵은 여러 PR/브랜치로 나눌까요?
6. 보안/시크릿 스캔은 로컬 `.env`, runtime logs, shell history 참조까지 봐도 될까요, 아니면 tracked file만 볼까요?
7. 감사 결과 가치가 낮다고 나와도 제거 대상에서 제외해야 하는 기능이 있나요?

이 질문에 답하기 전에는 구현을 진행하지 않습니다.
