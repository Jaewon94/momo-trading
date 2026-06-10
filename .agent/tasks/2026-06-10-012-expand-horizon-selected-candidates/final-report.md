# Final Report

## 변경 결과

- 최종 LLM 선별 상한을 확대했다.
  - SHORT: `8 -> 10`
  - MID: `8 -> 12`
  - LONG: `6 -> 12`
- 넓은 deterministic 후보 풀은 유지했다.
  - SHORT: 최대 `30`
  - MID: 최대 `60`
  - LONG: 최대 `100`
- 런타임 Admin settings에도 동일하게 반영했다.

## 현재 단중장 흐름

- SHORT는 빈번 스캔이다. 최근 장세, 거래량, 유동성, 급등락, 최근 24시간 뉴스 리스크를 우선 보고 60개 일봉 범위를 쓴다.
- MID는 일 1회 스캔이다. 20~120일 추세, 눌림 후 회복, 거래량 유지, 최근 7일 뉴스/공시 맥락을 보고 120개 일봉 범위를 쓴다.
- LONG은 주 1회 스캔이다. 120~240일 추세, 과도하지 않은 가격 위치, 공식 뉴스/공시와 사업 모멘텀을 보고 240개 일봉 범위를 쓴다.
- 각 horizon의 deterministic 후보가 market-scan LLM으로 넘어가고, LLM은 그 후보 안에서 최종 후보만 고른다.
- Tier1/Tier2 분석과 주문 판단은 최종 후보에 대해서만 수행한다.
- 주문 실행은 기존 리스크 프로필, 주문 모드, 매수 한도, 포트폴리오 제약, 브로커/세션 지원 여부를 계속 통과해야 한다.

## 판단 기준의 근거

- 이번 단중장 분리는 LLM만의 판단이 아니다.
- 코드 레일은 `strategy/horizon_scan_policy.py`에서 horizon별 후보 수, 뉴스 lookback, 일봉 길이, prompt focus로 강제된다.
- LLM에는 `target_horizon_hint`와 horizon별 뉴스/가격 맥락이 전달된다.
- 외부 근거는 horizon을 나누는 설계 방향을 뒷받침하는 용도다.
  - FINRA는 빈번한 일중매매를 비용, 마진, 빠른 손실 위험이 큰 별도 영역으로 본다.
  - FINRA Notice 26-10은 일중 노출 관리가 일반 보유와 다르게 관리되어야 함을 보여준다.
  - 시장 시간축 연구는 단기와 장기 신호 특성이 다를 수 있음을 보여준다.
  - 모멘텀 문헌은 중기 추세 신호 활용 가능성을 보여주지만 거래비용과 실행 리스크가 중요하다고 본다.
- 단, `10/12/12`라는 숫자 자체는 외부 표준값이 아니라 우리 서비스의 비용, 지연, 과매매 압력을 고려한 운영값이다.

## 검증 결과

- Focused pytest: `74 passed in 1.47s`
- Compile check: pass
- Task harness strict check: pass
- Runtime integrity: pass
- `git diff --check`: pass
- Health API: `healthy`

## 운영 상태

- 서버는 정상 응답 중이다.
- scheduler와 agent는 실행 중이다.
- 현재 세션은 `NXT_AFTER`라 정규 자동매매는 비활성이다.
- 최근 주문 경고 이력은 남아 있으나, 최신 runtime integrity 기준 pending/reconciliation 불일치는 없다.
