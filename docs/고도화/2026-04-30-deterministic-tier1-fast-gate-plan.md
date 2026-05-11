# Deterministic Tier1 Fast Gate 고도화 계획

작성일: 2026-04-30

## 배경

장중 후보 분석에서 Tier1 LLM 호출이 종목당 60~100초까지 늘어나면서 급등주/단타성 후보의 매수 타이밍을 놓칠 위험이 확인됐다. 오늘 운영 로그에서도 `qwen3:4b` 호출은 176초까지 지연됐고, Claude Code haiku 전환 후에도 후보별 48~101초 수준이 반복됐다.

안전 기준에서는 LLM을 완전히 제거하기보다, 명백한 비매수 후보를 코드로 빠르게 제거하고 최종 매수 후보만 LLM 검토로 넘기는 구조가 적합하다.

## 참고 원칙

- SEC Rule 15c3-5는 전자 주문에 대해 사전 자본/신용 한도, 오류 주문, 중복 주문, 규제 요건 검사를 요구한다.
- FINRA 알고리즘 트레이딩 가이던스는 코드 개발, 테스트, 운영 감시, 리스크 통제를 핵심 관리 영역으로 본다.
- KRX 호가가격단위는 가격대별로 다르므로 주문 직전 코드 레벨 보정이 필요하다.

## 목표

1. Tier1 LLM 호출 수와 장중 분석 지연을 줄인다.
2. 명백한 추격 매수/마감 임박/약세 후보를 LLM 전에 차단한다.
3. deterministic gate는 BUY를 직접 만들지 않고 HOLD/SKIP만 수행한다.
4. BUY 가능성이 남은 후보는 기존 Tier2 LLM과 리스크 게이트를 그대로 통과시킨다.

## 파이프라인

```text
시장 스캔
→ 포트폴리오/계좌 스냅샷 확인
→ 종목별 가격/일봉/분봉 조회
→ 차트/추세 지표 계산
→ PreAnalysisGate
→ Deterministic Tier1 Fast Gate
   - 명백한 HOLD는 Tier1 LLM 스킵
   - 애매하거나 강한 후보는 기존 Tier1/Tier2로 진행
→ Tier2 LLM 최종 검토
→ 비용/호가/계좌/중복 주문 게이트
→ 주문
```

## 1차 구현 범위

1차 구현은 안전성 우선으로 제한한다.

- 신규 서비스: `services/deterministic_tier1_fast_gate_service.py`
- 신규 설정:
  - `DETERMINISTIC_TIER1_FAST_GATE_ENABLED`
  - `TIER1_FAST_GATE_LATE_BUY_CUTOFF_HOUR`
  - `TIER1_FAST_GATE_LATE_BUY_CUTOFF_MINUTE`
  - `TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT`
  - `TIER1_FAST_GATE_MIN_CONTINUE_SCORE`
- 적용 위치: `agent/trading_agent.py`의 기존 `PreAnalysisGate` 통과 후, 피드백/뉴스/캐시/LLM Tier1 호출 전
- observability: `AI_SKIPPED` metric에 `DETERMINISTIC_TIER1_FAST_GATE` 기록

## 1차 판단 기준

### Hard Hold

- 보유 종목 또는 매도 방향 후보는 차단하지 않는다.
- 신규 매수 후보만 평가한다.
- 장 마감 임박 이후 급등 후보는 HOLD 처리한다.
- 차트 종합 방향이 약세이고 추세 점수도 음수이면 HOLD 처리한다.
- 점수 합산 결과가 임계값 미만이면 HOLD 처리한다.

### Score 요소

- 일봉 추세 방향
- 차트 종합 방향/신뢰도
- 분봉 추세 방향
- RSI 과열/건전 구간
- MACD histogram 방향
- 거래량 약화 여부
- 등락률 과열/적정 모멘텀
- 장 마감 임박 여부
- 시장 국면

## 운영 정책

- deterministic gate가 만드는 액션은 `HOLD` 또는 `CONTINUE`뿐이다.
- `CONTINUE`는 매수 추천이 아니다. 기존 LLM/리스크/주문 게이트로 넘긴다는 뜻이다.
- 운영 중 false negative가 우려되면 `TIER1_FAST_GATE_MIN_CONTINUE_SCORE`를 낮추거나 gate를 끌 수 있다.
- 뉴스 자동 폴링이 DB lock을 유발한 이력이 있으므로, 본 개선과 별도로 안정화 전까지는 비활성 유지가 안전하다.

## 검증 계획

1. 단위 테스트
   - 마감 임박 급등 비보유 후보는 Tier1 LLM 스킵
   - 보유 종목/매도 방향은 차단하지 않음
   - trading agent가 fast gate 스킵 시 `_tier1_analysis`를 호출하지 않음

2. 운영 검증
   - `AI_SKIPPED`에서 `DETERMINISTIC_TIER1_FAST_GATE` 건수 확인
   - Tier1 LLM 호출 수와 평균 지연 비교
   - 실제 주문 후보가 줄어드는 정도 확인
   - 장 마감 임박 추격 매수 방지 여부 확인

3. 다음 단계
   - shadow mode로 deterministic score와 기존 LLM 판단 비교
   - 점수 임계값을 종목/장세별로 조정
   - BUY 후보 상위 1~3개만 Tier2 LLM으로 보내는 top-N 정책 추가
