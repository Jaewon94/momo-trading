# Final Report

Understand-Anything 플러그인 기반 코드베이스 지식 그래프 생성과 전체 시스템 감사를
완료하고, 서비스 개선 로드맵을 수립해 docs/.agent 하네스에 연동했다. 소스 코드는
변경하지 않았으며(테스트 파일 4개 + 문서만 수정), 발견 이슈의 실제 수정은
로드맵 Phase 0~3 후속 태스크로 분리했다.

## Changed

- `.understand-anything/` (신규)
  - `knowledge-graph.json` (1.3MB): 노드 1,646 / 엣지 3,554 / 레이어 10 / 투어 14단계,
    전체 한국어. 598개 파일 fingerprint 베이스라인으로 증분 업데이트 지원.
  - 검증 이슈 0건 (경고 36건은 빈 `__init__.py` 등 무해한 고아 노드).
- `docs/고도화/2026-06-11-service-improvement-roadmap.md` (신규)
  - 4개 영역(아키텍처/트레이딩 도메인/테스트·품질/운영·보안) 감사 통합 로드맵.
  - P0 보안 4건, P1 매매 결함 9건, P2 운영 7건, P3 구조 6건 + 기능 공백/방향성/Phase 계획.
- `.agent/project-card.md`
  - 지식 그래프 디렉토리와 로드맵 문서 진입점 추가.
- `docs/workflows/code-commit-harness.md`
  - Pre-Edit에 `/understand-diff` 변경 영향도 확인 선택 단계 추가.
- 테스트 수정 (소스 무변경, 깨져 있던 9건 전부 수리):
  - `tests/frontend/test_position_detail_state.test.js`: 커밋 `ad0eb6e` UI 변경 미반영 stale test.
  - `tests/strategy/test_holding_policy.py`: `entry_at=2026-05-27` 고정 날짜 시한폭탄 → 상대 날짜.
  - `tests/services/test_holdings_precheck_service.py`: mid-long 정책 전환 이전 기대값 → -8% 손실로 조정.
  - `tests/services/test_news_polling_service.py`: investing/seeking_alpha 모킹 누락으로 실제 HTTP 호출
    발생 → `_mock_empty_news_sources` 헬퍼로 차단 (5개 테스트).
  - `tests/analysis/test_llm_factory.py`: 모델 override 경로에서 실제 LLM CLI 실행 → 프로바이더 생성자 패치.

## Behavior Impact

- Intended live order behavior change: none.
- 브로커/운영 DB/스케줄러 상태 무변경. 감사는 전부 읽기 전용으로 수행.
- 시크릿 미열람·미출력.

## Verification

- `venv/bin/python3.13 -m pytest tests/strategy/test_holding_policy.py tests/services/test_holdings_precheck_service.py tests/services/test_news_polling_service.py tests/analysis/test_llm_factory.py -q`: 58 passed
- `npx vitest run tests/frontend/test_position_detail_state.test.js`: 10 passed
- 전체 스위트 (수정 전 기준): pytest 1009 passed / 8 failed (실패 8건이 전부 이번 수정 대상), vitest 143/1
- `knowledge-graph.json` JSON 파싱 + 구조 검증: passed
- `venv/bin/python3.13 scripts/task_harness.py verify`: harness_tests 포함 통과 확인
  (시스템 python으로 실행 시 pytest 부재로 harness_tests 실패 — 로드맵 O6 venv 파손 이슈)

## Known Issues / Follow-ups

- 로드맵 P0 보안 이슈(admin API 무인증 + 0.0.0.0 바인딩, kis-mcp 노출, LLM 키 평문 저장)는
  미수정 상태로 최우선 후속 태스크 필요.
- 헤드리스 `claude -p` 실행이 세션 한도와 충돌해 3회 재시도로 완료 (운영 메모 저장됨).
- `.understand-anything/` git 커밋 여부는 사용자 결정 대기 (1.3MB — 커밋 시 팀 공유 가능).
