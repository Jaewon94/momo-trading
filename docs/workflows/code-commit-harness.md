# Code And Commit Harness

이 문서는 momo-trading에서 코드 작성과 커밋 직전 검증을 어떻게 하네스로 다룰지 정의한다.

## Pre-Edit

코드 작성 전에 확인할 것:

- `.agent/project-card.md`
- `.agent/security-policy.md`
- `.agent/current-task.json`
- 관련 service/repository/strategy/admin UI 기존 패턴
- 변경 위험도: broker, DB, migration, order placement, liquidation, API key, runtime provider, CI/CD는 고위험

새 기능, 전략 변경, DB/브로커 영향, 외부 API 변경은 task brief의 Research Gate에 근거를 남긴다.

## During Implementation

기본 흐름:

1. 관련 파일을 `rg`로 찾는다.
2. 가능한 경우 실패 테스트 또는 재현 케이스를 먼저 만든다.
3. 기존 helper, service, adapter, repository 패턴을 우선 사용한다.
4. trading business rule은 UI나 route handler에 넣지 않고 service/domain layer에서 테스트 가능하게 둔다.
5. secret, token, local path, port, provider 선택값을 코드에 하드코딩하지 않는다.

## Pre-Commit

커밋 전 기준:

```bash
python scripts/task_harness.py verify <task-id>
```

현재 verify는 다음을 실행한다.

- `git diff --check`
- `python -m py_compile` for harness scripts
- `python scripts/guard_git_command.py scan-secrets`
- `python scripts/check_task_harness.py --strict-current`
- `python scripts/check_markdown_links.py AGENTS.md .agent docs/workflows/code-commit-harness.md`
- `python scripts/check_docs_consistency.py`
- harness unit tests

작업별 domain test는 `test-plan.md`와 final report에 별도로 기록한다.

## Change Classification

변경 파일 기준으로 risk, reviewer, verification hint를 확인한다.

```bash
python scripts/change_harness.py agent/decision_maker.py strategy/risk_manager.py
```

분류 결과가 `high` 또는 `blocked`이면 task brief, decision record, test plan에 승인/검증 기준을 명시한다.

## Commit Approval

하네스는 commit을 자동 실행하지 않는다.

- `git commit`: 사용자 승인 필요
- `git push`: 별도 사용자 승인 필요
- force push to protected branch: 차단
- PR 생성, merge, deploy, migration: 별도 승인 필요

명령 분류:

```bash
python scripts/guard_git_command.py check-command --command "git commit -m 'feat(harness): 코드 커밋 하네스 추가'"
python scripts/guard_git_command.py check-command --command "git push --force origin main"
```

## Optional Local Hooks

로컬 hook은 source of truth가 아니라 스크립트를 호출하는 얇은 연결이다. 설치는 사용자가 원할 때만 한다.

```bash
cat > .git/hooks/pre-commit <<'SH'
#!/bin/sh
python scripts/task_harness.py verify "$(python - <<'PY'
import json
from pathlib import Path
print(json.loads(Path(".agent/current-task.json").read_text())["task_id"])
PY
)"
SH
chmod +x .git/hooks/pre-commit
```

이 hook 파일은 repo에 커밋하지 않는다.
