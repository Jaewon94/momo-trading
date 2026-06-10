# Trading Policy Change Checklist

자동매매 정책 변경 전후에 사용하는 체크리스트다. 기능 추가, 리팩터링,
runtime setting 변경, 프롬프트 변경 모두 이 기준으로 분류한다.

## 1. Scope

변경 전 task brief에 아래를 적는다.

- policy owner: `scanner`, `pre_analysis`, `llm_prompt`, `exposure`,
  `risk_manager`, `trading_guard`, `order_submission`, `holding_exit`,
  `runtime_settings`, `broker_reconciliation`
- affected side: `BUY`, `SELL`, `HOLDING_EXIT`, `ORDER_SUBMISSION`,
  `CANDIDATE`
- protected area: broker action, runtime DB, migration, liquidation,
  order placement, credential, CI/CD 중 해당 여부
- behavior impact: size increase, size reduction, buy block, sell block,
  forced sell, delayed sell, runtime setting mutation

## 2. Owner And Priority

아래 질문에 답하지 못하면 구현하지 않는다.

- 이 정책이 최종 판단 owner인가, 보조 evidence인가?
- 이 정책이 다른 정책을 override하는가?
- BUY-only 정책이 SELL 또는 holding review를 막지 않는가?
- 수량/가격/horizon/threshold를 바꾸면 previous/final value를 기록하는가?
- runtime setting default와 live override 중 무엇이 source of truth인가?

## 3. Tests

최소 검증:

- owner layer unit test
- caller parity test 또는 integration test
- runtime setting validation test, setting을 추가/변경한 경우
- trace/reason code test, block 또는 adjustment를 추가/변경한 경우
- sell path regression test, BUY gate를 건드린 경우

## 4. Documentation

아래 중 해당 파일을 같이 업데이트한다.

- `docs/architecture/trading-policy-governance.md`
- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `.agent/tasks/<task-id>/decision-record.md`
- LLM prompt contract, horizon/exit semantics가 바뀐 경우
- admin/settings 문서 또는 UI label, runtime setting 의미가 바뀐 경우

## 5. Verification

기본:

```bash
python scripts/check_task_harness.py --strict-current
python scripts/task_harness.py verify <task-id>
```

매매 판단, 주문 제출, 체결 확인, 보유 점검, broker adapter, repository/model,
관리자 거래 API를 바꾼 경우:

```bash
python scripts/check_runtime_integrity.py --days 7
```

실패하면 threshold 튜닝으로 덮지 말고 원인 owner를 먼저 기록한다.

## 6. Release Notes

최종 보고에는 아래를 남긴다.

- changed policy owner
- behavior changed or behavior-preserving refactor
- tests run
- runtime integrity result or reason not run
- remaining risk and rollback path
