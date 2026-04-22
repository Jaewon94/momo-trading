# 2026-04-07 장외/시간외 세션 확장 계획

## 목적
- 현재 정규장 중심으로 동작하는 국내 주식 운영 흐름에 대해, 장전/장후/대체거래소(NXT) 세션을 어디까지 지원할지 기준을 정리한다.
- 자동매매 확장 전, 세션 상태/주문 타입/브로커 지원 범위를 분리해 점진적으로 고도화한다.

## 공식 기준 요약
- KRX 시간외종가
  - 장전 시간외종가: `08:30 ~ 08:40`
  - 장후 시간외종가: `15:40 ~ 16:00`
- KRX 시간외단일가
  - `16:00 ~ 18:00`
  - 10분 단위 체결
  - 당일 종가 대비 `±10%` 범위
- KRX 시가/종가 동시호가
  - 장시작 동시호가: `08:30 ~ 09:00`
  - 장마감 동시호가: `15:20 ~ 15:30`
- NXT(대체거래소)
  - 프리마켓: `08:00 ~ 08:50`
  - 메인 세션 연계: `09:00 ~ 15:20`
  - 애프터마켓: `15:30 ~ 20:00`

## 현재 코드 기준 확인
- `scheduler/market_calendar.py`
  - 이미 `NXT_PRE`, `KRX_NXT`, `KRX_CLOSE`, `NXT_AFTER` 세션 개념이 존재
  - 다만 KRX 시간외종가/시간외단일가는 아직 분리 모델이 없음
- `scheduler/scheduler.py`
  - 장 시작 스캔, 14:30 신규 매수 마감, 15:10 강제 청산 등 정규장 데이트레이딩 흐름 중심
- `trading/enums.py`
  - `Market`, `OrderType`가 정규장 주문 중심
  - 시간외종가/시간외단일가/NXT 전용 주문 정책이 아직 모델링되지 않음
- `trading/kis_api.py`
  - 시세/랭킹 조회는 `J`, `NX`, `UN` 시장 구분이 보이므로 조회 확장 여지는 있음
  - 주문 지원 범위는 별도 검증 필요

## 판단
### 지금 바로 하지 않는 것
- 자동 장외/시간외 주문 허용
- 이유:
  - 세션별 주문 규칙이 서로 다름
  - 시장가 불가/지정가 강제/단일가 체결/종가 기준 가격 조건 등 별도 정책이 필요
  - 현재 자동매매 흐름은 정규장 데이트레이딩 전제로 설계됨

### 지금 바로 하는 것
1. 세션 상태 모델 명확화
- 운영 화면과 API에서 현재 국내 시장 세션을 `장중/장외`가 아니라 구체적인 세션 코드와 라벨로 노출

2. 세션 안내/운영 UI 고도화
- 현재 세션
- 다음 세션 시작 시각
- 세션별 자동매매 지원 여부
- 세션별 수동 주문 가능 여부(추후)

3. 수동 지원 기반 마련
- 자동매매 확장 전에 주문 모델과 브로커 지원 범위를 분리 설계

## 단계별 실행 계획
### Phase 1. 세션 상태 모델/운영 UI
- `market_calendar`에서 현재 세션 코드/라벨/다음 세션 정보를 일관된 구조로 반환
- `/api/v1/admin/system/status`에 세션 정보 추가
- 관리자 운영 시그널/상단 뱃지에 `정규장/장전/장후/NXT` 상태 노출
- 버튼 문구를 세션 기준으로 정리
  - 예: `매매 사이클 실행`, `장마감 리뷰 실행`, `장외 세션 점검`

### Phase 2. 주문 정책 모델 확장
- `OrderSession` 또는 동등한 정책 모델 도입
- `REGULAR`, `PRE_MARKET_CLOSE`, `POST_MARKET_CLOSE`, `AFTER_HOURS_SINGLE`, `NXT_PRE`, `NXT_AFTER`
- `OrderType`와 세션 정책을 분리
- 브로커별 지원 가능한 세션/주문 타입 capability 정의

### Phase 3. 수동 주문 지원
- 관리자 화면에서 세션별 수동 주문 지원
- 장후 시간외종가 / 시간외단일가 / NXT 세션을 명시적으로 선택
- 지원하지 않는 브로커/세션은 UI에서 비활성 처리

### Phase 4. 자동화 검토
- 정규장 자동매매와 분리된 별도 정책으로만 검토
- 종가 기준 진입/청산 전략, 장외 리밸런싱 등 별도 전략 단위로 도입
- 기본값은 OFF 유지

## 설계 원칙
- Single Responsibility
  - 세션 판별, 주문 정책, 브로커 capability, UI 노출을 분리
- Open/Closed
  - 새 세션 추가 시 스케줄/브로커/UI가 공통 모델을 따라 확장되도록 구성
- Interface Segregation
  - 조회 가능 세션과 주문 가능 세션을 분리
- TDD
  - 세션 판별/표시/지원 범위부터 테스트로 고정 후 구현

## 1차 구현 범위
- 이번 단계는 `Phase 1`까지만 진행
- 자동 주문/시간외 주문 구현은 포함하지 않음

## 1차 구현 완료
- `market_calendar`에 세션 정보 구조 추가
  - `code`, `label`, `note`, `is_domestic_open`, `is_regular_open`, `supports_automated_trading`, `next_session_at`
- `/api/v1/admin/system/status`에 세션 필드 추가
  - `market_session`
  - `market_session_label`
  - `market_session_note`
  - `market_session_auto_trading`
  - `domestic_market_open`
  - `next_market_session`
- 관리자 운영 시그널/상단 배지에서 세션 라벨 기준으로 표시
  - 정규장 / NXT 프리마켓 / 장마감 동시호가 / NXT 애프터마켓 / 장외
- 실시간 실행 버튼 문구를 세션 기준으로 정리
  - 정규장: `매매 사이클 실행`
  - 국내 시장은 열려 있지만 정규장이 아닌 경우: `장외 세션 점검 실행`
  - 완전 장외: `장마감 리뷰 실행`

## 다음 단계
- `Phase 2` 주문 정책 모델 확장
- 브로커별 시간외/NXT 주문 capability를 공식 주문 문서 기준으로 재검증
- 수동 주문부터 세션 선택 지원 검토

## Phase 2 진행 현황
- 공통 주문 세션 모델 추가
  - `OrderSession.REGULAR`
  - `OrderSession.NXT_PRE`
  - `OrderSession.KRX_CLOSE_AUCTION`
  - `OrderSession.NXT_AFTER`
  - `OrderSession.PRE_MARKET_CLOSE`
  - `OrderSession.POST_MARKET_CLOSE`
  - `OrderSession.AFTER_HOURS_SINGLE`
- `BrokerCapabilities` 확장
  - `supports_nxt_quotes`
  - `supports_after_hours_orders`
  - `supports_after_hours_automation`
  - `supported_order_sessions`
- 현재 capability 기본값
  - `KIS`: `supports_nxt_quotes=true`, 주문 세션은 보수적으로 `REGULAR`만 허용
  - `KIWOOM`: 주문/시세 모두 보수적으로 `REGULAR` 중심 유지
- 관리자 상태 응답에 브로커 capability 노출
  - `supports_nxt_quotes`
  - `supports_after_hours_orders`
  - `supports_after_hours_automation`
  - `supported_order_sessions`
- 운영 시그널의 브로커 카드에서 현재 허용 세션을 함께 표시
- 수동 즉시 매도/취소 후 즉시 매도는 현재 세션과 브로커 capability를 함께 확인
  - 정규장이 아니면 UI에서 비활성화
  - 서버에서도 같은 규칙으로 차단

## 아직 하지 않은 것
- 시간외종가/시간외단일가 실제 주문 API 연결
- NXT 세션 주문 UI 노출
- 자동 장외 전략 허용

## 다음 구현 단위
1. 브로커별 공식 주문 문서 재검증
2. 세션별 수동 주문 타입 설계
3. 지원하지 않는 세션의 수동 주문 UI 분리

## 참고
- KRX 시간외종가/시간외단일가 안내
- NXT 거래시간 안내
- 브로커 API 주문 지원 범위는 실제 도입 시 공식 주문 문서로 재검증

## 공식 검증 메모
- KRX/NXT 시간표 자체는 공식 공시 기준으로 확정 가능
- 현재 코드에서는 조회 capability와 주문 capability를 분리해 두고, 주문은 `REGULAR`만 허용하는 보수적 기본값 유지
- 이유:
  - KIS 공개 문서에서는 조회 확장 여지가 보이지만, 시간외/단일가/NXT 주문을 일반 정규장 주문과 같은 정책으로 안전하게 열 수 있다는 근거를 아직 충분히 확보하지 못함
  - Kiwoom도 현재 프로젝트 기준으로 시간외 주문을 안전하게 추상화할 만큼 공식 연결 범위를 재검증하지 못함
