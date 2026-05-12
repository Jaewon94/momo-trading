# Task Artifacts

각 작업은 `.agent/tasks/<task-id>/` 아래에 독립된 artifact를 둔다.

Task ID 형식:

```text
YYYY-MM-DD-NNN-short-slug
```

필수 파일:

- `brief.md`
- `state.json`
- `run-log.json`
- `test-plan.md`
- `decision-record.md`
- `quality-scorecard.md`

검증:

```bash
python scripts/check_task_harness.py --strict-current
```
