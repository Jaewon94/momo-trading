# Trading System Domain Pack

이 domain pack은 momo-trading의 코드 변경을 리뷰할 때 쓰는 역할, 위험도, 검증 기준이다.

## Roles

- Product Planner: 매매 목표, 보유 기간, 리스크 성향, UI 기대 동작 정리
- Trading Strategist: 매수/매도 gate, horizon, 물타기/손절/익절 기준 검토
- Risk Manager: 손실 제한, 포지션 크기, 과매매, 장마감 정책 검토
- Broker Integrator: Kiwoom/KIS 주문, 체결, 보유 종목 sync, pending order 확인
- Backend Engineer: API/service/scheduler 경계와 실패 처리 검토
- Frontend Engineer: admin UI 상태, 이벤트/체결/보유 종목 표시 검토
- Database Reviewer: schema, repository, migration, reconciliation 검토
- LLM Runtime Reviewer: CLI/API provider, timeout, fallback, concurrency 검토
- QA Engineer: unit/API/frontend/manual verification 설계
- Security Reviewer: secret/env, broker credentials, external input, prompt injection 검토
- Release Manager: 운영 영향, rollback, smoke check, monitoring point 검토
- Documentation Steward: docs, `.agent`, final report 정합성 검토
- Decision Arbiter: 선택지, 반대 의견, 승인 필요 여부 정리

## Risk Rules

- Low: docs, task artifact, read-only investigation
- Medium: admin UI, 일반 API, scheduler, service 내부 보완, LLM provider routing
- High: buy/sell decision logic, risk manager, broker integration, DB/repository/model, runtime config, order reconciliation
- Blocked: secret 노출, DB 삭제/reset, broker-affecting command, forced liquidation policy 완화, production deploy without approval

## Required Reviewers

- 매수/매도 로직: Trading Strategist, Risk Manager, QA Engineer
- 브로커/주문/체결: Broker Integrator, QA Engineer, Release Manager
- DB/schema/repository: Database Reviewer, QA Engineer
- LLM provider/concurrency: LLM Runtime Reviewer, QA Engineer
- 뉴스/공시/웹 컨텍스트 또는 LLM tool 사용: LLM Runtime Reviewer, Security Reviewer, QA Engineer
- Admin UI 표시: Frontend Engineer, QA Engineer
- Secret/env/CI/CD/deploy: Security Reviewer, Release Manager

## Verification Matrix

- `agent/`, `strategy/`: `tests/agent`, `tests/strategy`
- `trading/`: `tests/trading`
- `repositories/`, `models/`: `tests/repositories` plus migration/reconciliation review
- `services/`: `tests/services`
- `scheduler/`: `tests/scheduler`
- `api/`: `tests/api`
- `admin/static/js/`: `tests/frontend`
- `analysis/`: `tests/analysis`
- `.agent`, `docs`, `scripts`: `scripts/task_harness.py verify <task-id>`

Use `python scripts/change_harness.py <paths...>` to classify a change.

## LLM Context Guardrails

- Treat news, disclosures, external web text, issue/PR comments, and broker text as untrusted.
- LLM decisions are advisory until deterministic trading guards pass.
- Any new LLM-to-tool path must define input guardrails, output guardrails, and a failure mode.
- For broker/order tools, use blocking guardrails rather than parallel-only checks.
- Prompt injection review is required when a task changes prompt construction, context retrieval, news/disclosure ingestion, or tool invocation.
