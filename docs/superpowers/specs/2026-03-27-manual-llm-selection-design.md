# Manual LLM Selection For Admin Actions Design

**Date:** 2026-03-27

## Goal

Admin 화면에서 수동 AI 작업을 실행하기 전에 사용자가 `Claude Code` 또는 `Codex`를 선택할 수 있게 한다. `.env`에는 두 provider를 모두 등록해 두고, 자동 파이프라인용 기본 설정과 수동 작업용 선택 설정을 분리한다.

## In Scope

- Admin UI에서 수동 작업용 AI provider 선택
- 선택 상태를 조회/변경하는 Admin API
- 수동 작업에만 적용되는 서버 측 override
- 대상 작업
  - Q&A
  - 수동 사이클 실행
  - 수동 일일 리포트 생성
- activity log와 응답 payload에 사용 provider가 드러나게 개선

## Out Of Scope

- 자동 스캐닝/분석/최종검토 파이프라인의 provider 선택
- Tier1/Tier2 자동 라우팅 정책의 제거
- Claude/Codex 세부 모델명을 UI에서 직접 수정하는 기능
- provider별 프롬프트 튜닝 변경

## Current State

- `.env`에는 `LLM_PROVIDER_TIER1`, `LLM_PROVIDER_TIER2`, fallback 설정이 존재한다.
- `LLMFactory`는 현재 Tier 기반 provider chain만 해석한다.
- Admin 설정 UI는 런타임 mutable settings를 직접 `settings` 객체에 반영한다.
- 수동 AI 작업은 `api/routes/admin.py`에 모여 있다.
  - `POST /api/v1/admin/agent/trigger`
  - `POST /api/v1/admin/reports/generate`
  - `POST /api/v1/admin/qa/ask`

## Design Principles

### 1. 관심사 분리

- `.env` 기반 Tier 설정은 자동 파이프라인의 기본값으로 유지한다.
- 수동 작업 선택은 별도의 "manual override" 책임으로 분리한다.
- UI는 상태를 고르고 보여주는 역할만 한다.
- 실제 provider 결정은 서버가 수행한다.

### 2. SOLID 적용

- Single Responsibility:
  - `LLMFactory`는 provider 실행과 라우팅 해석을 담당한다.
  - 수동 선택 상태 저장/조회는 별도 런타임 설정 계층이 담당한다.
- Open/Closed:
  - 현재는 `AUTOMATIC`, `CLAUDE_CODE`, `CODEX`만 지원하지만, 향후 provider가 늘어도 enum/해석기만 확장하면 된다.
- Dependency Inversion:
  - Admin 라우트는 "현재 수동 실행용 provider를 해석하는 서비스"를 통해 provider를 얻고, 구체 설정 필드에 직접 의존하지 않는다.

### 3. TDD 우선

다음 순서를 고정한다.

1. 수동 선택 상태 조회/변경 API 테스트
2. `LLMFactory`의 수동 override 해석 테스트
3. Q&A가 수동 선택 provider를 우선 사용하는 테스트
4. 수동 사이클/리포트 생성이 override 컨텍스트를 전달하는 테스트
5. 최소 구현

## Recommended UX

## Settings Section

Admin 사이드바 `설정` 영역에 새 섹션을 추가한다.

- 라벨: `수동 작업 AI`
- 설명: `Q&A / 수동 사이클 / 리포트 생성에만 적용`
- 선택 옵션
  - `자동`
  - `Claude Code`
  - `Codex`

## Interaction Flow

1. 사용자가 화면에서 수동 작업 AI를 선택한다.
2. 선택값은 런타임 설정 API로 저장된다.
3. 사용자가 `Q&A`, `수동 사이클 실행`, `리포트 생성` 중 하나를 실행한다.
4. 서버는 현재 수동 작업 override를 읽는다.
5. override가 `AUTOMATIC`이면 기존 Tier 규칙을 사용한다.
6. override가 특정 provider면 해당 작업의 LLM 호출은 그 provider를 우선 사용한다.

## Why Not A Modal

- 사용자는 "작업 전에 옵션으로 선택"을 원한다.
- 매 실행마다 모달이 뜨면 반복 작업 피로도가 크다.
- 현재 Admin UI는 사이드바 설정 + 액션 버튼 구조라 사전 선택형이 더 자연스럽다.

## Backend Architecture

## New Runtime Setting

수동 작업 전용 설정 필드를 추가한다.

- 예시 필드명: `MANUAL_LLM_PROVIDER`
- 허용값:
  - `AUTOMATIC`
  - `CLAUDE_CODE`
  - `CODEX`

이 값은 `.env` 기본값을 가질 수 있지만, 핵심은 Admin API로 런타임 변경 가능해야 한다.

## LLM Resolution

`LLMFactory`에 수동 작업용 provider 해석 API를 추가한다.

- 예시 메서드
  - `resolve_manual_provider(default_tier: LLMTier) -> LLMProvider | None`
  - `generate_manual(prompt, system_prompt, default_tier=LLMTier.TIER1, ...)`

동작 규칙:

- `MANUAL_LLM_PROVIDER=AUTOMATIC`
  - 기존 Tier chain 사용
- `MANUAL_LLM_PROVIDER=CLAUDE_CODE`
  - Claude를 primary로 사용
  - 필요하면 기존 fallback chain 또는 동일 provider 단독 실행 정책 적용
- `MANUAL_LLM_PROVIDER=CODEX`
  - Codex를 primary로 사용

## Route Integration

### Q&A

- 현재 `generate_tier1()` 직접 호출
- 변경 후 `generate_manual(..., default_tier=TIER1)` 사용

### 수동 일일 리포트 생성

- 일일 리포트 서비스 내부 LLM 호출이 수동 API에서 시작된 경우 manual override를 적용할 수 있어야 한다.
- 가장 단순한 방법은 서비스 메서드 인자로 `manual_provider_override`를 전달하는 것이다.

### 수동 사이클 실행

- 수동 사이클은 비동기 task로 실행된다.
- trigger 시점의 선택값이 작업 시작 순간에 캡처되어야 한다.
- 따라서 `run_cycle()` 진입 전에 override 컨텍스트를 인자로 넘기거나, 수동 실행 전용 entrypoint를 만든다.

## Logging And Observability

- Activity log summary/detail에 사용된 provider를 기록한다.
- 가능하면 model도 포함한다.
- `/admin/llm/status`에 자동 Tier 정보와 별개로 현재 수동 작업 선택값을 포함한다.

## API Shape

기존 설정 API를 확장한다.

- `GET /api/v1/admin/settings`
  - `MANUAL_LLM_PROVIDER` 포함
- `PUT /api/v1/admin/settings`
  - `MANUAL_LLM_PROVIDER` 업데이트 허용
- `GET /api/v1/admin/llm/status`
  - `manual_selection` 블록 추가

## Frontend Shape

현재 `loadSettings()`와 `updateSetting()` 패턴을 재사용한다.

- 신규 `select#set-manual-llm-provider`
- 초기 로드 시 서버값 반영
- 변경 시 PUT 요청
- `loadLLMStatus()`에서 현재 manual selection과 provider 설명 렌더링

## Best-Practice Notes

- Anthropic Claude Code는 세션 중 `/model` 또는 시작 시 `--model`로 모델 선택이 가능하며, 설정 우선순위가 명확하다. 따라서 앱은 "호출 시점에 어떤 provider/model을 쓸지 결정"하는 wrapper 구조를 갖는 것이 자연스럽다.
- OpenAI Codex도 실행 시점 model 지정이 가능하므로, UI에서 선택한 값을 서버가 CLI 호출 직전에 적용하는 방식이 적절하다.
- FastAPI는 dependency/system boundaries를 통해 공통 해석 로직을 공유하기 좋으므로, 라우트가 설정 객체를 직접 해석하지 않고 작은 해석 계층을 두는 편이 유지보수성이 높다.

References:

- Anthropic CLI reference: https://docs.anthropic.com/en/docs/claude-code/cli-reference
- Anthropic model configuration: https://docs.anthropic.com/en/docs/claude-code/model-config
- Anthropic settings: https://docs.anthropic.com/en/docs/claude-code/settings
- OpenAI Codex getting started: https://help.openai.com/en/articles/11096431-openai-codex-ci-getting-started
- FastAPI dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/

## Testing Strategy

### Unit Tests

- `tests/analysis/test_llm_factory.py`
  - 수동 선택이 `AUTOMATIC`일 때 기존 tier chain 유지
  - 수동 선택이 `CLAUDE_CODE`일 때 Claude 우선
  - 수동 선택이 `CODEX`일 때 Codex 우선

### API Tests

- `tests/api/test_admin_settings_routes.py` 또는 기존 admin test 파일 확장
  - settings GET/PUT에 `MANUAL_LLM_PROVIDER` 반영
  - `/admin/llm/status`에 manual selection 노출
- `tests/api/test_admin_qa_routes.py`
  - Q&A가 수동 선택 provider를 사용

### Service/Agent Tests

- 수동 리포트 생성 시 override 전달
- 수동 사이클 trigger 시 override snapshot 전달

## Risks

- 수동 사이클은 내부적으로 여러 Tier 호출을 포함하므로, "수동 작업에서 Codex 선택"이 Tier2 최종검토까지 모두 덮는지 명확히 정의해야 한다.
- trigger 후 비동기 실행이므로 선택값을 전역 mutable state로 늦게 읽으면 다른 사용자의 선택 변경이 섞일 수 있다.
- 따라서 수동 사이클은 "실행 시작 시점 snapshot"이 필수다.

## Final Decision

1. 수동 작업 범위만 우선 지원한다.
2. 선택 방식은 Admin 화면에서 미리 고르는 사전 선택형으로 한다.
3. 자동 작업 Tier 설정은 그대로 유지한다.
4. 수동 작업은 별도 override를 통해 provider를 결정한다.
5. 구현은 TDD로 진행한다.
