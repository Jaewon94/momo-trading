# Decision Record

## Decision

1. Understand-Anything 플러그인을 user scope로 설치하고(`claude plugin install understand-anything`), `/understand --language ko`를 헤드리스로 실행해 `.understand-anything/`에 지식 그래프를 생성한다.
2. 개선 로드맵은 플러그인 출력에만 의존하지 않고, 4개 영역(아키텍처/트레이딩 도메인/테스트·품질/운영·보안) 병렬 심층 감사를 별도로 수행해 통합한다.
3. 로드맵 문서는 `docs/고도화/2026-06-11-service-improvement-roadmap.md`에 기존 날짜-prefix 컨벤션으로 작성한다.
4. 연동: `.agent/project-card.md`에 지식 그래프·로드맵 참조 추가, `docs/workflows/code-commit-harness.md`에 `/understand-diff` 선택 단계 추가.
5. 감사 중 발견된 깨진 테스트 9건을 전부 수정했다 (소스 코드는 건드리지 않음 — 전부 테스트 파일만):
   - vitest 1건: `test_position_detail_state.test.js` — 커밋 `ad0eb6e`의 의도된 UI 변경(실현손익 metrics → heroMeta)에 못 따라간 stale test. 새 카드 구조로 기대값 갱신.
   - pytest `test_holding_policy.py` 1건: 픽스처 `entry_at=2026-05-27` 고정 → 6/11에 보유 15일이 되며 MAX_HOLD_DAYS_MID에 걸린 시한폭탄. 상대 날짜(now-2일)로 변경.
   - pytest `test_holdings_precheck_service.py` 1건: mid-long 정책 전환(-3% 하드코딩 제거, horizon 미기재 STABLE_SHORT → MID 추론 -7%) 이전 기대값. 손실률을 -8%로 조정해 의도(손실 SELL은 LLM 유지)는 보존.
   - pytest `test_news_polling_service.py` 5건: 나중에 추가된 뉴스 소스(investing, seeking_alpha)의 모킹 누락으로 **실제 HTTP 호출** 발생, 실데이터 18건이 검증에 섞임. `_mock_empty_news_sources` 헬퍼 추가로 차단.
   - pytest `test_llm_factory.py` 1건: MANUAL_LLM_MODEL override 경로에서 `_build_provider`가 캐시(페이크) 대신 실제 프로바이더를 생성해 **실제 LLM CLI 실행**. 프로바이더 생성자를 monkeypatch로 페이크화.

## Rationale

- 플러그인 그래프는 구조 이해/시각화/영향도 분석에 유용하지만, "돈을 잃을 수 있는 결함" 수준의 도메인 감사는 직접 코드를 읽는 병렬 에이전트 감사가 더 깊다 → 두 접근을 병행.
- 코드 결함 수정은 보호 영역(매매 로직)에 닿으므로 이 태스크에서는 로드맵 수립까지만 하고, 실제 수정은 Phase별 후속 태스크로 분리 (vitest stale test 수정만 예외 — 매매 동작에 영향 없는 테스트 기대값 정렬).
- 0-falsy 의심도 검토했으나 `formatSignedKrW(0)`은 "0원"을 반환하므로 소스 버그가 아니라 테스트가 구버전 카드 레이아웃을 참조하는 것이 원인.

## Deferred

- 로드맵 Phase 0~3의 실제 구현 (각각 별도 태스크로 등록 예정).
- `/understand-dashboard` 상시 활용 및 auto-update hook 활성화 여부.
- `.understand-anything/` git 커밋 여부 (그래프 크기 확인 후 결정).

## Risks

- 헤드리스 `/understand` 실행이 세션 사용량 한도에 걸려 1회 중단됨 (2:40am 리셋 후 재개). 그래프 미완성 시 intermediate 캐시에서 이어서 실행 가능.
- 감사 결과 중 P0 보안 항목(admin API 무인증 + 0.0.0.0 바인딩)은 로드맵 문서에만 있고 아직 미수정 상태 — 사용자 확인 후 최우선 처리 필요.
- 운영/보안 감사 에이전트의 안전 분류기가 일시 불가 상태였음 — 해당 에이전트 결과는 읽기 전용 감사 보고이며, 파일 변경이 없음을 git status로 확인할 것.
