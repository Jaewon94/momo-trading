# 거래 코어 수익방어 고도화 (2026-04-05)

## 목적
- 방향 적중률보다 손익비/손실제어를 먼저 개선해 순손익 안정화.
- 장중 급변/품질저하 구간에서 자동으로 매수 리스크를 줄이기.

## 반영 내용
1. 매수 실행 정책 분리
- 설정: `BUY_ORDER_EXECUTION_MODE` (`LIMIT_GUARD` | `MARKET`)
- 설정: `BUY_SLIPPAGE_GUARD_BPS`
- `LIMIT_GUARD` 모드에서 매수 지정가가 없으면 `현재가 + 슬리피지 가드(bp)`로 제한가 자동 생성.

2. 자동 리스크 킬스위치
- 신규 모듈: `strategy/trading_guard.py`
- 차단 기준:
  - 일손실률 한도 (`MAX_DAILY_DRAWDOWN_PCT`)
  - 연속 손실 횟수 (`MAX_CONSECUTIVE_LOSSES`)
  - 전략 기대값 하한 (`MIN_STRATEGY_EXPECTANCY`, 샘플 `EXPECTANCY_SAMPLE_SIZE`)
- 차단 시 `TRADING_ENABLED=false` 자동 전환(설정 ON 시).

3. 변동성 기반 포지션 사이징
- 설정: `VOLATILITY_POSITION_SIZING_ENABLED`, `RISK_PER_TRADE_PCT`
- 손절폭(`entry-stop`) 기준으로 허용 손실 예산 내 수량 재계산.
- 과대 수량 제안 시 자동 감축.

4. 운영 설정 노출 확장
- `/api/v1/admin/settings` mutable 항목에 신규 리스크/실행 설정 추가.

5. 호라이즌(단기/중기/장기) 기반 운영
- 신규 유틸: `strategy/trade_horizon.py`
- 판정 기준:
  - 단기: 이벤트 급등락/고변동/공격 전략
  - 장기: 강세/테마 국면 + 고신뢰도
  - 그 외 중기
- 적용:
  - 호라이즌별 리스크 배수 (`RISK_MULTIPLIER_SHORT/MID/LONG`)
  - 호라이즌별 비용 게이트(예상 비용 대비 기대엣지)
  - 호라이즌별 손절/익절/트레일링 기본값 보정

6. 수익 검증 리포트 API
- `GET /api/v1/admin/performance/summary?days=30`
  - overall KPI, 전략별/호라이즌별 KPI, 리스크 차단 횟수
- `GET /api/v1/admin/performance/periodic?period=weekly|monthly&size=8`
  - 주간/월간 버킷 기반 성과 추이
- KPI: trade_count, win_rate, expectancy, profit_factor, total_pnl, avg_return_pct, max_drawdown

## 기대 효과
- 급락일 손실 꼬리 위험 감소.
- 체결 품질 편차(슬리피지) 완화.
- 전략 성능 저하 국면에서 자동 방어.

## 테스트
- `tests/strategy/test_trading_guard.py`
- `tests/strategy/test_risk_manager_enhancements.py`
- `tests/agent/test_trading_agent_execution_policy.py`
- `tests/strategy/test_trade_horizon.py`
- `tests/agent/test_trading_agent_cost_gate.py`

## 2026-04-06 운영 이슈 대응 반영
1. 자동 매도 수량 정합성 보정
- 자동 매도 시 AI 제안 수량이 아니라 실제 보유 수량 스냅샷을 기준으로 SELL 주문 수량을 보정.
- 보유 수량이 없으면 SELL 주문을 스킵해 `매도가능수량 부족` 오류를 줄임.

2. 수동 매도/미체결 액션 UI 추가
- 3단 카드의 `SELL` 상태와 보유 종목 상세 모달에 `즉시 매도` 버튼 추가.
- 미체결 주문은 상태별로 분리:
  - 미체결 매수 → `주문 취소`
  - 미체결 매도 → `취소 후 즉시 매도`

3. 부분 매도 정합성 복구
- SELL 체결 시 열린 BUY lot 전체를 닫지 않고, 체결된 수량만큼만 닫힌 BUY 기록으로 분리.
- 남은 수량은 열린 BUY lot에 유지해 이후 보유 수량/매도 수량과 일치하도록 정리.
- `portfolio_sync_job`에서도 전량 청산뿐 아니라 부분 청산 복구를 지원.

4. 수익 검증 강화
- `뉴스 반영 거래 vs 일반 거래` 실제 성과 비교 추가.
- `Expectancy`, `Profit Factor`, `비용 차감 손익`이 일반 거래보다 열위면 rollout 승급을 보류(`KEEP`).

5. 현재 남은 운영 이슈
- 관리자 설정 변경이 재시작 후 유지되지 않음
- `scripts/dev/start.sh -d`의 PID 추적/상태 표시가 불안정함
- 종목 상세 타임라인에서 부분 매도 후 닫힌 BUY lot가 `매수 체결`로 보여 보유처럼 오해될 수 있음
- 3단 UI 배지가 `매수/매도` 단일 문구 중심이라 `접수중/대기중/부분 매도` 상태가 충분히 드러나지 않음

---

## 2차 고도화 계획 (뉴스 인텔 + 검증 운영)

### A. 매수 전 정보 체계 (현재/목표)
- 현재: 시세/거래량/차트/기술지표/과거성과 기반
- 부족: 뉴스/공시/해외 이슈가 실매매 경로에 미연동
- 목표: `차트 + 비용 + 뉴스` 3중 게이트로 진입 품질 강화

### B. 뉴스 운영 원칙
1. 상시 수집 + 이벤트 기반 재검증
- 새 기사 수신 시 `NEW_NEWS_ITEM` 이벤트 발행
- 영향 종목(보유/후보/영향도 상위)만 증분 재평가

2. 소스 신뢰도 계층화
- Tier A: 공시/거래소/공식 발표
- Tier B: 주요 통신사/경제지
- Tier C: 보조 소스(낮은 가중치)

3. 장중/장외 차등 운영
- 장중: 고빈도 수집 + 즉시 반영
- 장외: 저빈도 수집 + 익일 리스크 준비

4. 국내+해외 병행
- 해외 뉴스는 국내 종목 영향도 매핑 후 반영

5. DB 영속 저장 필수
- 재현성/사후분석/실험검증/회귀테스트 근거 확보

6. 재검증 정책
- 전량 재분석 금지, 영향 종목만 큐 기반 재검증
- 종목별 쿨다운 적용

7. 리포트 반영
- 기존 일/주/월 리포트에 뉴스 영향 섹션 추가
- 별도 뉴스 영향 리포트 제공

### C. 구현 단계
1. Phase 1: 뉴스 수집/정규화/저장 + 소스 신뢰도 스코어
2. Phase 2: 뉴스 감성/영향도 스코어 + 매수 전 뉴스 게이트
3. Phase 3: `NEW_NEWS_ITEM` 이벤트 재검증 파이프라인
4. Phase 4: 성과 리포트에 뉴스 영향/차단 사유 확장
5. Phase 5: UI/UX (의사결정 카드, 뉴스 타임라인, A/B 비교)
