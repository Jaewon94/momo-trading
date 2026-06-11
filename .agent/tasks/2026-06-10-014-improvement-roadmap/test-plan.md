# Test Plan

Task: `2026-06-10-014-improvement-roadmap`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
venv/bin/python3.13 -m pytest -q -p no:cacheprovider   # 전체 스위트 (감사 입력 데이터)
npx vitest run                                          # 프론트엔드 전체
npx vitest run tests/frontend/test_position_detail_state.test.js  # 수정한 테스트
python -c "import json; json.load(open('.understand-anything/knowledge-graph.json')); print('graph OK')"
```

## Manual Checks

- Confirm protected operations were not run without approval. (브로커/DB/서버 상태 변경 없음 — 감사는 전부 읽기 전용)
- `docs/고도화/2026-06-11-service-improvement-roadmap.md`의 모든 file:line 근거가 감사 에이전트 보고에서 온 것인지 확인.
- `.agent/project-card.md`와 `docs/workflows/code-commit-harness.md`의 추가 문구가 기존 문서 톤과 일치하는지 확인.
