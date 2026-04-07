# 장중 에러 수집과 incident 운영 계획

## 구현 상태
- 완료
  - `error_events` / `error_incidents` 테이블 추가
  - 공통 저장 서비스 `services/error_capture_service.py`
  - 뉴스 소스 polling 실패 연동
  - 스케줄러 뉴스 polling 실패 연동
  - LLM factory 전체 호출 실패 연동
  - 뉴스 번역 fallback 실패 연동
  - 수동 주문/취소/재매도 브로커 예외 연동
  - 관리자 `시스템 관측` 화면의 `Recent Errors`, `Repeated Incidents` 섹션 추가
  - 관리자 `에러 관측` 전용 페이지 추가
- 다음 확장 후보
  - 주문/브로커/LLM provider 예외 연동
  - incident mute/resolved 처리
  - 반복 임계치 기반 알림

## 목표
- 장중에 켜둔 상태에서 발생하는 예외를 DB에 구조적으로 저장한다.
- 저녁에 “무슨 에러가 몇 번 반복됐는지”를 한 번에 볼 수 있게 한다.
- 활동 로그와 분리된 운영용 에러 관측 계층을 둔다.

## 1차 구현 범위
- `error_events`
  - 원시 에러 이벤트 저장
- `error_incidents`
  - fingerprint 기준 집계
- 공통 캡처 서비스
  - `services/error_capture_service.py`
- 1차 연결 포인트
  - 뉴스 소스 polling 실패
  - 스케줄러 뉴스 polling 실패
- 확장 연결 포인트
  - `analysis/llm/llm_factory.py`
    - provider chain 전체 실패 시 capture
  - `services/news_translation_service.py`
    - 번역 실패 후 fallback metadata를 남기는 경로에서 capture
  - `services/manual_trade_service.py`
    - 수동 매도 / 매수취소 / 매도재접수 중 브로커 예외 capture
- 시스템 관측 화면 표시
  - Recent Errors
  - Repeated Incidents

## 왜 분리하나
- `agent_activity_logs`
  - 운영 UI/흐름 추적용
- `error_events`
  - 예외와 원인 분석용
- `error_incidents`
  - 반복 문제와 우선순위 판단용

## 현재 수집 흐름
1. 예외 발생
2. `ErrorCaptureService.capture_exception(...)` 호출
3. 원시 이벤트를 `error_events`에 저장
4. fingerprint 기준으로 `error_incidents`를 upsert
5. 관리자 `시스템 관측` 화면에서 최근 에러와 반복 incident 노출

## 저장 항목
### error_events
- fingerprint
- severity
- component
- operation
- handled
- exception_type
- exception_message
- stacktrace
- cycle_id
- symbol
- provider
- model
- detail

### error_incidents
- fingerprint
- title
- component
- operation
- severity
- status
- first_seen_at
- last_seen_at
- occurrence_count
- exception_type
- last_message
- last_symbol
- last_provider
- owner_note

## fingerprint 정책
- `component + operation + exception_type + normalized message`
- 완전히 같은 stacktrace가 아니어도, 운영적으로 같은 문제면 하나의 incident로 묶는 방향

## 운영 화면에서 보는 법
- `시스템 관측 > Recent Errors`
  - 최근 개별 예외를 시간순으로 확인
- `시스템 관측 > Repeated Incidents`
  - 반복 발생 빈도가 쌓인 incident를 확인
- 저녁 점검 루틴 추천
  - `Repeated Incidents` 상위 항목 확인
  - 같은 fingerprint가 어느 component / operation에서 반복되는지 확인
  - 필요한 경우 `error_events`의 message / stacktrace / detail로 재현 힌트 확보

## 운영 원칙
- validation/expected error와 system failure를 구분한다.
- 민감값은 detail에 그대로 저장하지 않는다.
- 에러가 발생해도 에러 저장 실패가 본 흐름을 막지 않게 한다.
- 시간 필드는 `datetime`으로 저장해서 이후 상태 변경, 집계, 정렬 확장에 대비한다.
- fingerprint는 low-cardinality를 유지하되, 운영적으로 다른 문제를 하나로 뭉개지 않게 component / operation을 포함한다.

## 참고한 기준
- OpenTelemetry exception log attributes
  - https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-logs/
- OpenTelemetry logs data model
  - https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Python logging cookbook
  - https://docs.python.org/3/howto/logging-cookbook.html

## 다음 단계
- 주문/브로커/LLM provider 예외까지 연결 확대
- mute/resolved 상태 변경 API
- threshold 기반 알림
- incident별 재현 메모/해결 메모
