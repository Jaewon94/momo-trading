# Broker Adapter Refactor Plan

## Goal

현재 KIS 전용 구조를 `브로커 어댑터` 구조로 리팩터링하여 다음 조건을 만족한다.

- 앱 코어가 특정 증권사 SDK/API 형식에 직접 의존하지 않는다.
- 내부 요청/응답 모델은 공통 DTO로 통일한다.
- 브로커별 차이는 어댑터 계층에서 흡수한다.
- TDD 방식으로 공통 계약 테스트와 브로커별 어댑터 테스트를 먼저 작성한다.
- 관심사 분리와 SOLID 원칙을 기준으로 점진적으로 리팩터링한다.

## Verified Inputs

### KIS

Context7 공식 소스 `/koreainvestment/open-trading-api` 기준으로 다음 축이 확인되었다.

- OAuth 인증
- REST access token 발급
- WebSocket approval key 발급
- 국내/해외 주식 시세 조회
- 주문/계좌 조회
- 실시간 WebSocket

### Kiwoom

Context7에서는 공식 문서가 아니라 래퍼 `/breadum/kiwoom-restful`만 확인되었다.
래퍼 기준으로 다음 축은 보인다.

- 실전/모의 호스트 분리
- 모의투자 서버 존재
- WebSocket 실시간
- 계좌/주문/시세 관련 래핑

단, 키움 구현 착수 전에는 반드시 `공식 문서`로 다시 검증한다.

## Design Principles

- Single Responsibility: 인증, 시세조회, 주문, 실시간, 스캔 공급자를 분리한다.
- Open/Closed: 새 브로커 추가 시 코어 변경 없이 어댑터 추가로 확장한다.
- Liskov Substitution: 모든 어댑터는 동일한 공통 계약을 만족해야 한다.
- Interface Segregation: 주문/실시간/스캔 기능을 분리하여 필요한 기능만 구현하게 한다.
- Dependency Inversion: `TradingAgent`, `MarketScanner`, `Scheduler`는 구체 구현이 아니라 인터페이스에 의존한다.

## Library Strategy

1. 우선 사용
- `typing.Protocol`
- `pydantic`
- `pytest`
- `pytest-asyncio`
- 기존 `httpx`, `websockets`

2. 도입 보류
- 무거운 DI 프레임워크
- 브로커별 비공식 SDK 직접 의존

이 프로젝트는 이미 `pydantic`, `pytest`, `httpx`, `websockets`를 사용 중이므로 1차 리팩터링에는 추가 라이브러리 없이 진행한다.

## Target Architecture

```text
agent / scheduler / services
        |
        v
  BrokerAdapter Protocol
        |
  +-----+-------------------+
  |                         |
  v                         v
KisBrokerAdapter      KiwoomBrokerAdapter

RealtimeAdapter Protocol
MarketScanProvider Protocol
```

## Common Contracts

### DTO

- `AccountBalance`
- `HoldingInfo`
- `PendingOrderInfo`
- `CurrentPrice`
- `OrderRequest`
- `OrderResult`
- `Candle`
- `BrokerCapabilities`

### Interfaces

- `BrokerAdapter`
  - `get_balance()`
  - `get_holdings()`
  - `get_pending_orders()`
  - `get_current_price()`
  - `get_daily_candles()`
  - `get_intraday_candles()`
  - `place_order()`
  - `cancel_order()`

- `RealtimeAdapter`
  - `connect()`
  - `disconnect()`
  - `subscribe()`
  - `unsubscribe()`

- `MarketScanProvider`
  - `get_volume_rank()`
  - `get_fluctuation_rank()`

## Implementation Phases

### Phase 1. Contract First

목표:
- 공통 DTO 정리
- 브로커 인터페이스 정의
- KIS 어댑터 기본 스캐폴딩

TDD:
- DTO validation test
- KIS adapter unit test

완료 조건:
- KIS 어댑터가 기존 단일톤 클라이언트를 감싼다.
- 앱 코어를 아직 바꾸지 않아도 독립 테스트 가능하다.

상태:
- 완료
- 공통 DTO와 `BrokerAdapter` 계약이 추가되었다.
- `KisBrokerAdapter`와 `KiwoomBrokerAdapter` 스캐폴딩 및 계약 테스트가 추가되었다.

### Phase 2. KIS Extraction

목표:
- `account_manager`, `mcp_client`, `order_executor`, `kis_websocket` 의존을 `KisBrokerAdapter` 뒤로 숨긴다.

대상 파일:
- `trading/account_manager.py`
- `trading/mcp_client.py`
- `trading/order_executor.py`
- `trading/kis_websocket.py`

TDD:
- 어댑터 contract test
- 기존 KIS 회귀 테스트

완료 조건:
- 코어 레이어에서 `mcp_client` 직접 참조가 사라진다.

상태:
- 진행 중
- 완료:
  - `admin` 계좌 조회 API
  - `TradingService`
  - `DecisionMaker` 주문 실행 및 체결 확인
  - `TradingAgent` 포트폴리오 조회, 손절/익절 매도, 시세/차트 조회 일부
  - `MarketScanner` 거래량/등락률 스캔
- 남음:
  - `TradingAgent` 내 브로커 전용 실시간/WebSocket 경로
  - `kis_websocket`과 `stream_manager` 계층 분리

### Phase 3. Core Decoupling

목표:
- `TradingAgent`, `MarketScanner`, `Scheduler`, `RealtimeMonitor`가 인터페이스만 바라보게 한다.

대상 파일:
- `agent/trading_agent.py`
- `agent/market_scanner.py`
- `scheduler/scheduler.py`
- `realtime/monitor.py`
- `realtime/stream_manager.py`

TDD:
- fake adapter 기반 agent unit test
- scheduler orchestration test

완료 조건:
- 브로커 교체 시 코어 수정이 필요 없다.

상태:
- 진행 중
- `TradingAgent`와 `MarketScanner`는 주요 조회/주문 경로에서 어댑터를 사용한다.
- 아직 `Scheduler`, `RealtimeMonitor`, `stream_manager`는 브로커 capability와 실시간 어댑터 분리가 남아 있다.

### Phase 4. Kiwoom Discovery Gate

목표:
- 키움 공식 문서 재검증
- 인증, 시세, 주문, 실시간, 모의투자 제약을 capability 표로 정리

게이트:
- 공식 문서 확인 전 구현 착수 금지

상태:
- 부분 완료
- Context7에서는 공식 키움 문서 대신 비공식 래퍼만 확인되었다.
- 현재 구현은 공식 사이트의 공개 가이드와 로컬 테스트 가능한 범위에서 REST 호스트/인증/기본 TR 기준으로 진행했다.
- 실계정 연결 전에는 실제 키움 개발자 콘솔 기준 재확인이 필요하다.

### Phase 5. Kiwoom Adapter

목표:
- `KiwoomBrokerAdapter`
- `KiwoomRealtimeAdapter`
- `KiwoomMarketScanProvider`

TDD:
- mock environment contract test
- parsing normalization test

완료 조건:
- `BROKER_PROVIDER=KIWOOM` 설정으로 동일 코어 로직을 재사용할 수 있다.

상태:
- 진행 중
- 완료:
  - `KiwoomRESTClient`
  - `KiwoomAccountClient`
  - `KiwoomMarketDataClient`
  - `KiwoomOrderExecutor`
  - `KiwoomBrokerAdapter`
  - 계좌/현재가/차트/주문 정규화 테스트
- 남음:
  - 실제 키움 키 기준 smoke test
  - 취소주문과 실시간 시세 어댑터
  - 조건검색 또는 브로커별 대체 스캔 전략

### Phase 6. Integration and Ops

목표:
- 설정 정리
- 문서 업데이트
- 모의투자 smoke test

추가 설정 예시:
- `BROKER_PROVIDER=KIS|KIWOOM`
- `BROKER_ENVIRONMENT=PAPER|LIVE`

상태:
- 진행 중
- 완료:
  - `BROKER_PROVIDER` 설정 추가
  - 키움 관련 `.env.example` 항목 추가
  - 읽기 전용 smoke test CLI 추가: `python -m tools.broker_smoke --symbol 005930 --market KRX`
- 남음:
  - 실제 키움 인증키 주입 후 로컬 smoke test 실행
  - 결과 기반 운영 가이드 보강

## Testing Strategy

### Unit Tests

- DTO validation
- adapter parsing
- order delegation
- capability exposure

### Contract Tests

- 모든 어댑터가 동일한 입력/출력 의미를 만족하는지 검증

### Integration Tests

- KIS paper smoke test
- Kiwoom mock smoke test

### Regression Tests

- health API
- 기존 KIS 경로가 phase 2 이전과 동일하게 동작하는지 검증

## Risks

- 키움 공식 문서의 세부 요청/응답 스펙은 아직 Context7에서 확정되지 않았다.
- 브로커마다 순위 스캔/조건검색/실시간 통보 범위가 다를 수 있다.
- 시장 시간, 모의투자 제약, 주문 가능 시장 범위는 capability 기반 분기가 필요하다.

## Current Slice

현재까지 완료된 작업은 다음과 같다.

1. 공통 DTO와 `BrokerAdapter` 계약 도입
2. `KisBrokerAdapter` 및 `KiwoomBrokerAdapter` 추가
3. `TradingService`, `DecisionMaker`, `TradingAgent`, `MarketScanner` 주요 경로를 어댑터 기반으로 전환
4. 키움 REST 클라이언트와 도메인 클라이언트 구현
5. 읽기 전용 브로커 smoke test CLI와 서비스 추가
6. 관련 테스트를 TDD 방식으로 누적 추가

현재 테스트 기준:
- `37 passed, 1 warning`

다음 작업 단위는 다음이다.

1. 키움 실연결 smoke test 실행
2. 실시간 시세/이벤트 경로를 `RealtimeAdapter`로 분리
3. `Scheduler`와 `stream_manager`의 브로커 capability 분기 정리
