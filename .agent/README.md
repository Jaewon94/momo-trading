# Agent Harness

이 디렉토리는 momo-trading 작업을 위한 repo-local context/harness 영역이다.

목적:

- 프로젝트 컨텍스트를 짧고 최신인 파일로 고정한다.
- 작업별 목표, 제한, 결정, 검증 결과를 `.agent/tasks/<task-id>/`에 남긴다.
- 긴 대화나 임시 로그에 의존하지 않고 다음 작업자가 이어받을 수 있게 한다.

기본 파일:

- `project-card.md`: repo 목적, 주요 명령, 운영 주의사항
- `security-policy.md`: 위험 명령과 승인 경계
- `current-task.json`: 현재 집중 작업 포인터
- `tasks/`: 작업별 artifact

검증:

```bash
python scripts/check_task_harness.py --strict-current
```
