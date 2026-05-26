# Final Report

## Summary

- 원인: 스캐너 프롬프트와 후보 점수가 여전히 초단기/급등 후보를 강하게 밀어 올렸고, 실제 리스크 가드는 연속 손실 `PROBATION` 상태에서 2~10% 등락률 회복 후보만 허용하고 있었다.
- 조치: 시장 스캔을 중기/장기 편향으로 바꾸고, 후보 점수에 정책 적합성(`policy_buy_eligible`)을 추가했으며, 활성 probation에서는 과열 후보를 선별 후 제거하고 정책 적합 후보를 보강하도록 했다.
- 결과: 재시작 후 10:23:51 스캔에서 `PROBATION` 활성, 연속 손실 5회, 선호 등락률 2~10% 정책이 기록됐고, 선정 후보 6개가 모두 `policy_eligible=True`였다.
- 추가 원인: 연속 손실은 닫힌 승리 BUY가 있어야 초기화되는데, 기존 `PROBATION`은 보유 중이면 차단하고 단일 약세 장중 신호도 차단해서 회복 기회를 과하게 줄였다.
- 추가 조치: 연속 손실 가드는 유지하되 `PROBATION`을 축소 진입 복구 레인으로 완화했다. 기존 보유, 반복 손실 패턴, 단일 약세 장중 신호는 경고로 낮추고, 일일 cap, 2~10% 밴드 위반, 복합 약세 장중 신호는 계속 차단한다.
- 후속 정합성 조치: 남아 있던 Tier1 종목 분석 프롬프트의 "단기 매매 전문" 문구를 중기/장기 스윙 중심으로 정리했고, 사용자 승인 후 라이브 `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS`를 코드 기본값과 같은 `2`로 재적용했다.
- 재시작 정합성 조치: 재시작 후 기존 보유분의 AI 손절/익절 임계값이 메모리 감시기에 복원되지 않아 기본값 폴백 경고가 날 수 있는 경로를 수정했다. 보유 점검은 이제 DB에 저장된 open TradeResult의 stop/take/trailing 값을 먼저 복원한 뒤 판단한다.

## Runtime Verification

- Runtime: final restart is running in `momo-runtime-20260520h` tmux session, PID `88595`.
- Health/system: API health OK, scheduler OK, agent OK, autonomy `AUTONOMOUS`, effective order mode `FULL`; latest cycle `2026-05-20T15:09:45+09:00`.
- Broker/order: 2026-05-20 10:25:17 KST KIWOOM BUY order `0069525` for `376930` was accepted and confirmed.
- Current position check: `376930` 노을 360주 open position, trade horizon `MID`; DB entry price was reconciled from `1093` to broker average `1086` after explicit approval.
- Live setting alignment: protected runtime setting `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` was changed from `1` to `2` through the admin confirmation flow; settings API now reports `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS=2`.
- Prompt alignment: live LLM activity after restart contains the new Tier1 system prompt: 중기/장기 스윙 중심, MID/LONG 우선, SHORT 전술은 예외.
- Reconciliation: runtime integrity OK after final restart; broker pending orders 0, DB pending confirms 0, broker/DB order reconciliation OK.
- Current PnL check after final restart: `376930` 노을 360주, broker avg `1086`, current `1068`, unrealized PnL `-9,948` KRW (`-2.54%`); `084650` 랩지노믹스 73주, broker avg `1363`, current `1360`, unrealized PnL `-1,066` KRW (`-1.07%`).
- Latest decision check: after live cap alignment, the 14:59 KST cycle produced a Tier2-approved BUY for `084650` 랩지노믹스; final risk check passed, order `0149110` was submitted, and fill confirmation recorded 73주 @ `1,363` KRW.
- End-of-day holding check: 15:10 smart liquidation review returned HOLD for both `084650` and `376930`; no sell order was submitted.

## Verification Commands

- `.venv313/bin/python -m pytest tests/services/test_candidate_scoring_service.py tests/agent/test_market_scanner.py -q` -> 10 passed.
- `.venv313/bin/python -m pytest tests/agent tests/services/test_candidate_scoring_service.py -q` -> 118 passed.
- `.venv313/bin/python -m pytest tests/analysis -q` -> 54 passed.
- `.venv313/bin/python -m pytest tests/services -q` -> 237 passed.
- `.venv313/bin/python -m pytest tests/trading tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/agent/test_market_scanner.py tests/services/test_candidate_scoring_service.py -q` -> 138 passed.
- `.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py -q` -> 17 passed.
- `.venv313/bin/python -m pytest tests/strategy tests/trading tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/agent/test_market_scanner.py tests/services/test_candidate_scoring_service.py -q` -> 174 passed.
- `python scripts/check_runtime_integrity.py --days 7` -> OK.
- `python -m py_compile strategy/trading_guard.py core/config.py agent/market_scanner.py services/candidate_scoring_service.py trading/adapters/kiwoom_adapter.py` -> passed.
- `.venv313/bin/python -m pytest tests/analysis/test_stock_analysis_prompt.py tests/services/test_deterministic_prompt_context_service.py -q` -> 3 passed.
- `python -m py_compile analysis/llm/prompts/stock_analysis.py` -> passed.
- `python scripts/change_harness.py analysis/llm/prompts/stock_analysis.py tests/analysis/test_stock_analysis_prompt.py` -> medium risk, no protected broker/runtime area in code change.
- `python -m py_compile scheduler/scheduler.py` -> passed.
- `.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py::test_holdings_check_restores_persisted_ai_exit_thresholds_after_restart -q` -> 1 passed.
- `.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q` -> 82 passed.
- `python scripts/change_harness.py scheduler/scheduler.py tests/scheduler/test_scheduler_runtime_paths.py` -> medium risk, scheduler change.
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-20-002-scanner-probation-alignment` -> passed.
- `git diff --check` -> passed.

## Remaining Notes

- `start.sh -d` did not stay attached in this execution environment, so the runtime was kept in the background with tmux.
- `.env.example` was updated to show the intended `LOSS_STREAK_RECOVERY_MODE=PROBATION`; runtime already had this setting active.
- Kiwoom BUY fill inference now uses broker holding average/blended average when a filled order leaves the pending book before a direct fill price is available.
- The consecutive-loss guard is still necessary as an automated-trading risk control, but the previous release path was too sticky. The revised code allows controlled reduced-size recovery attempts instead of requiring a closed profit first and blocking most new opportunities.
- The 14:59 KST BUY order was close to the afternoon session transition, but fill confirmation completed before final verification. Subsequent monitoring should focus on normal stop/take-profit behavior and end-of-day handling.
- Live activity before this final fix showed old `AI 손절/익절 미설정` warnings for `376930` after restart. The code path is now covered by focused tests and final runtime integrity is OK; direct live restore logging depends on the next `_holdings_check` execution after the final restart.
