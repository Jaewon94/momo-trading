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

### Change Impact Map (Optional)

Understand-Anything 지식 그래프(`.understand-anything/knowledge-graph.json`)가 있으면, 고위험 영역(broker, order placement, liquidation, migration)을 수정하기 전에 `/understand-diff`로 변경 영향 범위를 확인할 수 있다. 그래프가 오래되었으면 `/understand`로 갱신한다. 전체 구조 탐색은 `/understand-dashboard`를 사용한다.

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

## Runtime Integrity

`task_harness.py verify`는 커밋 전 코드/문서 하네스이고, 실행 중인 브로커·운영 DB의 상태를 자동으로 정리하거나 대사하지 않는다.

매매 판단, 주문 제출, 체결 확인, 보유 점검, 브로커 adapter, repository/model, 관리자 거래 API를 바꾸는 경우에는 서버가 떠 있는 환경에서 read-only 런타임 무결성 게이트를 별도로 실행한다.

```bash
python scripts/check_runtime_integrity.py --days 7
```

이 명령은 다음을 확인한다.

- `GET /api/v1/health`
- `GET /api/v1/admin/system/status`
- `GET /api/v1/admin/settings`
- `GET /api/v1/admin/trades/reconciliation`
- `GET /api/v1/admin/trades/lifecycle-integrity?days=7`

기본 기준은 전체 runtime status `OK`만 통과다. `WARN` 또는 `FAIL`은 서버/스케줄러 상태, 위험 관리자 액션 확인, 브로커 pending 주문과 DB `PENDING_CONFIRM`, 브로커 실제 보유, DB open BUY lot, SELL 연결, 체결 확인 실패 중 하나가 깨진 상태이므로 변경을 "운영 안전"으로 보고하지 않는다.

서버를 의도적으로 띄우지 않는 순수 코드 리뷰에서는 실행하지 못한 이유를 task run log와 최종 보고에 남긴다. 서버가 떠 있는데 이 게이트가 실패하면 DB repair, broker reconciliation, 또는 런타임 안전 모드 전환은 별도 승인 경계로 다룬다.

관리자 쓰기 API 중 주문, 취소, DB 정합성 repair, 운영 기준선 reset, 런타임 매매/위험 설정 변경, credential 변경, 스케줄러 start/stop, 수동 agent cycle처럼 브로커나 운영 DB에 영향을 주는 액션은 UI 확인만으로 충분하지 않다. 서버 측 confirmation token을 요구해야 하고, 조회/점검 성격의 엔드포인트는 기본 dry-run이어야 한다.

## Change Classification

변경 파일 기준으로 risk, reviewer, verification hint를 확인한다.

```bash
python scripts/change_harness.py agent/decision_maker.py strategy/risk_manager.py
```

분류 결과가 `high` 또는 `blocked`이면 task brief, decision record, test plan에 승인/검증 기준을 명시한다. `change_harness.py`가 `python scripts/check_runtime_integrity.py --days 7`을 checks에 포함하면, 해당 변경은 운영 데이터 무결성 확인까지 완료되어야 안전하다고 본다.

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
