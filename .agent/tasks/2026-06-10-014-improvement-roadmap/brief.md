# Brief

## Metadata

- Task ID: `2026-06-10-014-improvement-roadmap`
- Created: `2026-06-10T21:48:31+09:00`
- Repo: `momo-trading`
- Title: Service improvement roadmap with Understand-Anything

## Goal

Understand-Anything 플러그인으로 코드베이스 지식 그래프를 생성하고, 심층 분석을 통해 서비스 개선 로드맵(고쳐야 할 점/추가할 점/나아갈 방향)을 수립하여 docs와 .agent 하네스에 연동한다

## Scope

In scope:

- Understand-Anything 플러그인 설치 및 `/understand --language ko` 실행으로 `.understand-anything/knowledge-graph.json` 생성.
- 4개 영역(아키텍처/트레이딩 도메인/테스트·품질/운영·보안) 병렬 감사 수행.
- `docs/고도화/2026-06-11-service-improvement-roadmap.md` 작성 (고쳐야 할 점 / 추가할 점 / 나아갈 방향 / 우선순위).
- 지식 그래프·로드맵을 `.agent/project-card.md`와 docs 워크플로우에 연동.

Out of scope:

- 발견된 이슈의 실제 코드 수정 (후속 태스크로 분리).
- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- https://github.com/Egonex-AI/Understand-Anything (플러그인 README, SKILL.md)
- docs/audits/2026-04-22-system-wide-trading-audit-findings.md (이전 감사와 중복/진척 비교)
- .agent/project-card.md, AGENTS.md

Plan implications:

- Adopt: Claude Code 플러그인 마켓플레이스 설치(user scope), `/understand` 헤드리스 실행, 산출물은 `.understand-anything/`에 저장.
- Defer: `/understand-dashboard`, auto-update hook 활성화는 그래프 검증 후 결정.
- Reject: 없음.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.understand-anything/knowledge-graph.json` 존재 및 JSON 유효성 확인.
- `venv/bin/python3.13 -m pytest -q` 전체 통과 여부 기록 (감사 입력 데이터).
- `npx vitest run` 결과 기록.
- 로드맵 문서가 docs/고도화 컨벤션(날짜 prefix)을 따르는지 확인.
