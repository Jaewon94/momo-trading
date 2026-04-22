# Broker Realtime Decoupling Design

**Date:** 2026-04-10

## Goal

브로커별 실시간 시세 처리 경로를 `KIS 전용 분기`에서 `공통 실시간 계약 + capability 기반 선택` 구조로 정리해, 코어가 특정 브로커 WebSocket 구현을 직접 알지 않도록 만든다. 이번 단계의 목표는 `KIWOOM 실시간 구현`이 아니라, 실시간 가능 여부와 폴링 폴백을 일관된 계약으로 표현하는 것이다.

## In Scope

- 실시간 어댑터 계약 정의
- 현재 브로커 기준 실시간 어댑터 선택 팩토리 추가
- [realtime/stream_manager.py](/Users/jaewon/open-project/momo-trading/realtime/stream_manager.py)의 KIS 전용 분기 제거
- [realtime/monitor.py](/Users/jaewon/open-project/momo-trading/realtime/monitor.py)의 provider 이름 기반 분기 제거
- 브로커 capability와 실시간 동작의 의미 정리
- 실시간 미지원 브로커의 폴링 폴백 경로 테스트 강화

## Out Of Scope

- Kiwoom 실시간 시세 어댑터 실제 구현
- Kiwoom 취소주문 구현
- 조건검색 또는 브로커별 스캔 공급자 확장
- 시간외 주문 세션 처리
- 기존 KIS WebSocket 파싱 포맷 변경

## Current State

- [trading/adapters/base.py](/Users/jaewon/open-project/momo-trading/trading/adapters/base.py)는 `BrokerAdapter`만 정의하고, 실시간 전용 계약은 없다.
- [realtime/stream_backend.py](/Users/jaewon/open-project/momo-trading/realtime/stream_backend.py)는 `KISStreamBackend`와 `NullStreamBackend`를 제공하지만, 선택 기준이 `settings.BROKER_PROVIDER == "KIS"` 문자열 비교에 묶여 있다.
- [realtime/stream_manager.py](/Users/jaewon/open-project/momo-trading/realtime/stream_manager.py)는 `_supports_kis_streams()`로 KIS만 실시간 가능하다고 가정한다.
- [realtime/monitor.py](/Users/jaewon/open-project/momo-trading/realtime/monitor.py)는 `_uses_kis_websocket()`로 시작 경로와 health check 경로를 분기한다.
- [trading/adapters/kis_adapter.py](/Users/jaewon/open-project/momo-trading/trading/adapters/kis_adapter.py)는 `supports_realtime_quotes=True`를 노출한다.
- [trading/adapters/kiwoom_adapter.py](/Users/jaewon/open-project/momo-trading/trading/adapters/kiwoom_adapter.py)도 현재는 `supports_realtime_quotes=True`를 노출하지만, 실제 실시간 연결 어댑터는 없다.
- [tests/realtime/test_monitor.py](/Users/jaewon/open-project/momo-trading/tests/realtime/test_monitor.py)는 현재 `KIWOOM 모드면 KIS websocket을 건너뛴다` 수준의 회귀만 검증한다.

## Problem Statement

현재 구조는 "브로커가 실시간을 지원하는가"가 아니라 "현재 브로커가 KIS인가"를 기준으로 동작한다. 이 방식은 다음 문제를 만든다.

- 코어 레이어가 브로커 이름을 직접 안다.
- capability가 있어도 실행 경로 선택에는 쓰이지 않는다.
- `KIWOOM`이 실시간 capability를 노출하더라도 실제 연결 계층과 일치하지 않는다.
- 이후 새 브로커나 새 실시간 구현을 추가할 때 `monitor`, `stream_manager`, `stream_backend`를 함께 수정해야 한다.

## Design Principles

### 1. Capability First

- 코어는 provider 이름 대신 capability와 실시간 계약만 사용한다.
- 실시간 지원 여부는 `supports_realtime_quotes`와 선택된 realtime adapter의 조합으로 판단한다.

### 2. 관심사 분리

- `BrokerAdapter`는 계좌/시세/주문 같은 거래 기능을 담당한다.
- `RealtimeAdapter`는 연결, 구독, 수신, 콜백 연결만 담당한다.
- `RealtimeMonitor`는 "실시간 vs 폴링" 정책만 담당한다.
- `StreamManager`는 구독 목록 관리와 재연결 orchestration만 담당한다.

### 3. 단계적 확장

- 이번 단계에서는 KIS를 새 계약 뒤로 숨기고, Kiwoom은 `polling-only` 상태를 명시한다.
- Kiwoom 실시간 구현은 다음 단계에서 같은 계약을 만족하는 어댑터를 추가하는 방식으로 확장한다.

### 4. TDD 우선

다음 순서를 고정한다.

1. capability 기반 시작 경로 테스트
2. `StreamManager`의 provider 독립 테스트
3. 실시간 미지원 어댑터의 폴링 폴백 테스트
4. 최소 구현
5. 기존 KIS 회귀 테스트

## Recommended Architecture

```text
RealtimeMonitor
    |
    +--> BrokerAdapter.capabilities
    |
    +--> StreamManager
              |
              +--> RealtimeAdapter
                        |
                        +--> KISRealtimeAdapter
                        +--> NullRealtimeAdapter
```

## Contracts

### Realtime Adapter

예상 위치:

- `realtime/adapters/base.py`
- `realtime/adapters/kis_realtime_adapter.py`
- `realtime/adapters/null_realtime_adapter.py`
- `realtime/realtime_factory.py`

필수 인터페이스:

- `set_on_price(callback)`
- `start()`
- `stop()`
- `subscribe(symbol, market)`
- `unsubscribe(symbol, market)`
- `listen()`
- `subscription_count`
- `is_connected`
- 선택적으로 `supports_reconnect` 또는 `mode` 같은 메타 정보

핵심은 `stream_manager`와 `monitor`가 KIS 전용 구현 세부사항을 더 이상 import하지 않는 것이다.

### Capability Rules

- KIS:
  - `supports_realtime_quotes=True`
  - realtime adapter = `KISRealtimeAdapter`
- Kiwoom:
  - 이번 단계에서는 실제 realtime adapter가 없으므로 capability와 실행 경로가 일치해야 한다.
  - 가장 단순한 선택은 `supports_realtime_quotes=False`로 정정하고 `NullRealtimeAdapter`를 사용한다.
  - 이렇게 하면 현재 동작과 문서가 일치하고, 이후 구현 시 capability를 다시 `True`로 올리면 된다.

## Backend Architecture

### `realtime/realtime_factory.py`

- 현재 브로커 어댑터와 설정을 기준으로 realtime adapter를 반환한다.
- 문자열 비교를 한 곳으로 고립시키고, 나머지 코어는 팩토리 결과만 사용한다.

### `realtime/stream_manager.py`

- 내부 필드로 `RealtimeAdapter`를 가진다.
- `_supports_kis_streams()` 같은 provider 전용 메서드를 제거한다.
- `start()`, `stop()`, `subscribe_symbols()`, `unsubscribe_symbols()`, `update_subscriptions()`는 adapter 위임과 구독 상태 관리만 한다.
- 재연결은 `adapter.listen()` 실패 시 재시작하고 기존 구독을 복원하는 현재 정책을 유지한다.

### `realtime/monitor.py`

- 시작 시 `get_broker_adapter()`와 realtime adapter를 함께 본다.
- `broker_adapter.capabilities.supports_realtime_quotes`가 참이면:
  - 가격 콜백 연결
  - `stream_manager.start()`
- 아니면:
  - 장중일 때 폴링 폴백 시작
- health loop도 provider 이름이 아니라 capability와 연결 상태만 기준으로 삼는다.

### `realtime/stream_backend.py`

- 이번 단계에서는 제거하거나, compatibility shim으로만 남긴다.
- 새 설계에서는 `stream_backend`가 최상위 선택 지점이 아니라 KIS 전용 구현 상세가 된다.
- 가장 단순한 방향은 KIS용 wrapper를 새 adapter로 옮기고, 이 파일은 점진적 삭제 대상으로 본다.

## Fallback Rules

- 실시간 capability가 없으면 폴링은 예외 경로가 아니라 정상 운영 경로다.
- 장외 시간에는 기존처럼 폴링을 중지한다.
- 실시간 capability가 있는 브로커에서 연결이 끊기거나 데이터가 stale이면 폴링 폴백을 활성화한다.
- 실시간 데이터가 다시 들어오면 폴링 폴백을 끈다.

## Error Handling

- 실시간 연결 실패는 서버 기동 실패로 전파하지 않는다.
- 실시간 미지원 브로커는 경고 로그 대신 debug 수준의 정상 경로 로그만 남긴다.
- adapter 내부 구현 오류와 capability 불일치는 테스트로 먼저 잡고, 런타임에서는 안전하게 폴링으로 떨어진다.

## Testing Strategy

### Realtime Monitor

[tests/realtime/test_monitor.py](/Users/jaewon/open-project/momo-trading/tests/realtime/test_monitor.py)

- 실시간 capability가 `True`면 `stream_manager.start()`가 호출된다.
- 실시간 capability가 `False`면 `stream_manager.start()` 없이 폴링이 시작된다.
- stale/disconnected 상태에서 폴링 폴백이 활성화된다.
- 실시간 데이터가 복구되면 폴링이 비활성화된다.

### Stream Manager

[tests/realtime/test_monitor.py](/Users/jaewon/open-project/momo-trading/tests/realtime/test_monitor.py) 또는 분리된 새 테스트 파일

- 구독 추가/삭제/복원이 provider 문자열 없이 adapter 인터페이스로만 동작한다.
- 연결 실패 후 재시작 시 기존 구독이 복원된다.
- `NullRealtimeAdapter` 사용 시 구독 카운트와 연결 상태가 안전하게 유지된다.

### Capability Consistency

- `KiwoomBrokerAdapter.capabilities.supports_realtime_quotes`가 현재 구현 상태와 일치하는지 검증한다.
- 실시간 adapter 팩토리가 브로커별 기대 타입을 반환하는지 검증한다.

## Migration Notes

1. 기존 KIS WebSocket 구현은 보존한다.
2. 다만 import 경로를 `monitor -> stream_backend -> kis_websocket`에서 `monitor -> stream_manager -> realtime adapter -> kis_websocket` 구조로 바꾼다.
3. `KIWOOM`의 capability는 실제 구현 상태에 맞게 보수적으로 정정한다.
4. 기존 회귀 테스트는 capability 기반 검증으로 치환한다.

## Risks

- `supports_realtime_quotes`를 `False`로 바꾸면 일부 상태 표시가 달라질 수 있다.
- `stream_backend`를 급하게 제거하면 기존 monkeypatch 테스트가 깨질 수 있다.
- 재연결 정책을 adapter 계층으로 과도하게 밀어 넣으면 책임이 다시 흐려질 수 있다.

## Final Decision

1. 브로커 실시간 경로는 별도 `RealtimeAdapter` 계약으로 분리한다.
2. `RealtimeMonitor`와 `StreamManager`는 provider 이름을 직접 보지 않는다.
3. 현재 실시간 구현이 없는 브로커는 capability를 보수적으로 정정하고 `NullRealtimeAdapter`로 처리한다.
4. KIS WebSocket은 유지하되, 새 adapter 뒤로 숨긴다.
5. 구현은 TDD로 진행한다.
