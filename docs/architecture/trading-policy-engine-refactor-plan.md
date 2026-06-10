# Trading Policy Engine Refactor Plan

Task: `2026-06-10-002-policy-governance-refactor`

## Executive Summary

현재 문제는 개별 조건값 하나가 잘못됐다기보다, 매수 후보 필터, LLM 판단,
노출 보정, 리스크 수량 조정, 브로커 주문 가능성, 보유/매도 이벤트 정책이
서로 다른 파일에서 각자 판단하고 집행한다는 구조 문제다.

이번 리팩터링의 목표는 기능 변경이 아니라 정책 소유권과 결합 순서를 먼저
중앙화하는 것이다. 1차 구현은 기존 동작을 그대로 감싸서 동일한 결과와 더
좋은 trace를 만들고, 이후 단계에서만 중복 로직을 안전하게 이동한다.

핵심 방향:

- `TradingAgent`와 `DecisionMaker`는 orchestration과 enforcement에 집중한다.
- 정책 판단은 `TradingPolicyEngine`이 공통 context를 받아 공통 decision/effect
  계약으로 반환한다.
- 하드 안전장치는 `deny-overrides` 방식으로 명시한다.
- BUY 차단 정책이 SELL 안전청산을 실수로 막지 않도록 side별 결합 규칙을 둔다.
- 수량, 가격, horizon, threshold를 바꾸는 모든 정책은 이전값과 최종값, owner,
  reason code를 남긴다.

## Sources Reviewed

| Source | 적용할 점 |
| --- | --- |
| [Open Policy Agent docs](https://www.openpolicyagent.org/docs/latest/) | 정책 판단을 애플리케이션 코드와 분리하고, decision을 데이터로 다루는 방식이 맞다. OPA 자체 도입은 아직 과하다. |
| [OPA policy testing](https://www.openpolicyagent.org/docs/latest/policy-testing) | 정책은 결과만 보지 말고 입력 context와 expected decision을 fixture로 고정해 회귀 테스트해야 한다. |
| [OASIS XACML 3.0 Core Specification](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.pdf) | PDP/PEP 분리, deny-overrides, permit-overrides, first-applicable 같은 결합 알고리즘 개념을 내부 정책 엔진에 적용한다. |
| [SEC Market Access Rule release](https://www.sec.gov/news/press/2010/2010-210.htm) | 주문 제출 전 risk management control, preset limits, supervisory procedure가 필요하다는 원칙은 자동매매에도 그대로 적용된다. |
| [FINRA Regulatory Notice 15-09](https://www.finra.org/rules-guidance/notices/15-09) | 알고리즘 전략은 개발, 테스트, 배포, 변경관리, 사후 모니터링이 하나의 통제 프로세스여야 한다. |
| [Microsoft domain analysis for microservices](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis) | business capability와 bounded context 기준으로 정책 owner를 나눠야 한다. 단순 파일 위치가 owner가 되면 안 된다. |
| [AWS Well-Architected Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html) | 운영 절차와 변경 검증은 코드처럼 관리해야 하며, 관찰 가능성과 반복 가능한 검증이 필요하다. |
| [Feature toggles paper, arXiv:1907.06157](https://arxiv.org/abs/1907.06157) | 런타임 토글은 소유자, 수명주기, 충돌 가능성을 관리하지 않으면 기술부채가 된다. |

## Current Code Policy Map

| Policy area | Current owner | Decision/effect today | Risk |
| --- | --- | --- | --- |
| 시장 후보 폭 | `agent/market_scanner.py`, `services/candidate_scoring_service.py` | broker ranking을 모아 `SCANNER_MAX_CANDIDATES`만큼 점수화하고, LLM이 selected를 고른 뒤 deterministic policy가 보정한다. | 후보 정책, recovery/probation 정책, LLM 선별 정책이 한 흐름에 섞여 있다. |
| Tier1 전처리 | `services/pre_analysis_gate_service.py` | 현금 부족, 데이터 부족, 강한 bearish 후보를 Tier1 전에 skip한다. | BUY 후보 제거 정책인데 전체 policy trace와 결합되지 않는다. |
| Tier1 fast gate | `services/deterministic_tier1_fast_gate_service.py` | 점수 기반으로 Tier1 LLM 호출을 HOLD skip한다. 공격 성향에서 threshold를 완화한다. | risk appetite를 자체 해석하므로 exposure/risk layer와 해석이 달라질 수 있다. |
| Tier2 전 최종 deterministic gate | `services/deterministic_final_gate_service.py` | confidence, RR, stop loss, buying power로 Tier2 전 차단한다. | RR과 broker buying power가 risk manager와 일부 중복된다. |
| 비용/뉴스 gate | `agent/trading_agent.py`, `services/news_signal_service.py` | Tier1 cost gate, final cost gate, news gate를 BUY 전에 적용한다. | LLM 전/후 비용 gate가 별도 함수라 동일 정책인지 한눈에 확인하기 어렵다. |
| 공격적 노출 보정 | `strategy/exposure_policy.py`, `agent/trading_agent.py` | 이미 승인된 BUY 수량을 목표 노출까지 올린 뒤 risk manager에 넘긴다. | 수량 증가 정책이 다른 수량 축소 정책과 중앙 조합되지 않는다. |
| 계좌/전략 guard | `strategy/trading_guard.py` | 일손실, 계좌 drawdown, LLM runtime, 연속손실, 기대값을 평가한다. 경우에 따라 runtime `TRADING_ENABLED`를 끈다. | BUY guard인데 runtime mutation side effect가 있어 순수 정책 판단과 운영 조치가 섞여 있다. |
| risk sizing | `strategy/risk_manager.py` | 일일 한도, RR, 변동성 sizing, 단일 주문, 현금, 최소 현금, 포지션 비중을 검사하고 수량을 직접 바꾼다. | 최근 개선으로 adjustment는 남기지만 여전히 `TradeSignal` mutation이 직접 발생한다. |
| broker/order gate | `agent/decision_maker.py`, `core/order_submission.py`, `core/post_liquidation_guard.py` | pending BUY, order submission mode, post-liquidation BUY block, existing pending order를 주문 직전에 확인한다. | 최종 주문 gate라 반드시 필요하지만 upstream 정책들과 같은 reason taxonomy를 쓰지 않는다. |
| 보유/매도 이벤트 | `agent/trading_agent.py`, `strategy/position_exit_policy.py`, `strategy/holding_policy.py` | stop loss/take profit 이벤트는 LLM 없이 매도할 수 있고, horizon별 최소보유와 분할손절을 적용한다. | 일부 매도는 AI 판단이 아니므로 AI policy와 exit policy의 관계를 명확히 해야 한다. |
| runtime setting validation | `core/runtime_settings.py`, `core/config.py`, `api/routes/admin.py` | 변경 가능 setting 목록과 일부 range validation을 관리한다. | setting owner, priority, test coverage, rollout status가 한 곳에 없다. |
| LLM prompt contract | `analysis/llm/prompts/*.py` | 중장기 기준과 horizon 의미를 prompt에 기록한다. | prompt 정책과 deterministic 정책이 동시에 바뀌는지 검증하는 장치가 약하다. |

## Target Architecture

### 1. Common Types

새 package 후보:

```text
strategy/policy/
  __init__.py
  types.py
  context.py
  engine.py
  registry.py
  settings_catalog.py
  trace.py
```

초기 타입:

```python
class PolicyAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ADJUST = "ADJUST"
    DEFER = "DEFER"
    OBSERVE = "OBSERVE"

class PolicyScope(str, Enum):
    CANDIDATE = "CANDIDATE"
    BUY = "BUY"
    SELL = "SELL"
    HOLDING_EXIT = "HOLDING_EXIT"
    ORDER_SUBMISSION = "ORDER_SUBMISSION"
```

`PolicyContext`에는 아래 입력만 모은다.

- cycle id, symbol, market, side, strategy type, horizon
- account snapshot, holdings snapshot, broker buying power
- market regime, candidate scanner evidence, chart evidence, news evidence
- LLM Tier1/Tier2 output
- runtime settings snapshot
- current `TradeSignal` value

`PolicyDecision`은 반드시 아래를 포함한다.

- `owner`: 예, `risk_manager`, `order_submission`, `holding_exit`
- `scope`: `BUY`, `SELL`, `CANDIDATE`, `HOLDING_EXIT`
- `action`: `ALLOW`, `BLOCK`, `ADJUST`, `DEFER`, `OBSERVE`
- `priority`: 결합 순서
- `reason_code`: machine-readable code
- `reason`: Korean operator-facing reason
- `effects`: quantity/price/horizon/threshold/runtime side effect 후보
- `inputs_hash` 또는 compact input summary

`PolicyEffect`는 mutation을 직접 실행하지 않고 아래처럼 반환한다.

- `field`: `suggested_quantity`, `suggested_price`, `stop_loss`, `target_exposure_pct`
- `before`
- `after`
- `effect_type`: `RAISE`, `REDUCE`, `SET`, `CLEAR`
- `requires_enforcement`: enforcement layer가 실제 적용해야 하는지 여부

### 2. Decision Point And Enforcement Point

내부 용어:

- `TradingPolicyEngine`: PDP, 즉 정책 판단점이다.
- `TradingAgent`, `DecisionMaker`, event handlers: PEP, 즉 집행점이다.

원칙:

- engine은 broker 주문을 내지 않는다.
- engine은 DB/runtime setting을 직접 mutate하지 않는다.
- kill switch처럼 운영 상태 변경이 필요한 경우도 먼저 `PolicyEffect`로 반환하고,
  별도 승인된 enforcement helper가 실행한다.
- 1차 리팩터링에서는 기존 side effect를 유지하되 trace에 표시하고, 2차에서
  side effect 분리를 진행한다.

### 3. Combining Rules

명시적인 결합 규칙을 둔다.

1. `hard_safety_deny_overrides`
   - `TRADING_ENABLED=false`, `ORDER_SUBMISSION_MODE=READ_ONLY`, 계좌 drawdown kill
     switch 같은 hard block은 모델 출력보다 우선한다.
   - 단, `SELL_ONLY`는 BUY만 막고 SELL은 허용한다.
2. `side_specific_buy_gate`
   - candidate, fast gate, cost gate, news gate, exposure alignment, buy risk sizing은 BUY에만 적용한다.
   - 이 gate들이 SELL 또는 holding review를 막으면 policy bug로 본다.
3. `exit_policy_first_applicable`
   - stop loss, take profit, trailing, holding review 같은 exit trigger는 첫 번째 명확한 trigger를 기록하되,
     horizon min-hold와 staged exit policy가 최종 action/quantity를 조정한다.
4. `adjustments_compose`
   - 수량 증가 effect는 risk sizing보다 먼저 적용한다.
   - 수량 축소 effect는 가장 보수적인 최종 수량을 채택한다.
   - broker buying power는 마지막 cap으로 적용한다.
5. `observe_does_not_block`
   - shadow/rollout/probation 관측 decision은 trace에는 남기지만 order path를 바꾸지 않는다.

## Refactor Phases

### Phase 0: Freeze And Trace, No Behavior Change

목표:

- 기존 정책 순서를 문서와 fixture로 고정한다.
- 정책이 내린 block/adjust/allow를 공통 trace로 남긴다.
- 실제 매매 결과는 바꾸지 않는다.

Status:

- 2026-06-10 implemented initial trace infrastructure in `strategy/policy/`.
- Existing scanner/LLM/risk/order/exit behavior was not intentionally changed.
- `policy_trace` is now additive metadata for representative gate/log paths,
  not a central decision engine yet.

작업:

- Done: `PolicyDecision`, `PolicyEffect`, `PolicyTrace` 타입 추가.
- Done: `TradingAgent._analyze_and_trade`의 주요 gate 결과를 `PolicyTrace`로 감싸는 adapter 추가.
- Done: `RiskManager.check` 결과의 `adjustments`와 `ExposureAlignmentDecision`을 같은 trace schema로 변환.
- Done: event sell path의 stop loss/take profit decision도 같은 trace에 넣는다.
- Done: 현재 문서와 테스트 fixture를 `tests/strategy/policy/`에 추가한다.
- Remaining: broker buying-power adjustment, order reservation shadow/enforce,
  and scanner candidate scoring can be folded into the same trace in a later
  small patch if needed.

검증:

- 기존 `tests/agent/test_trading_agent_cycles.py`
- 기존 `tests/agent/test_decision_maker.py`
- 기존 `tests/strategy/test_trading_guard.py`
- 기존 `tests/strategy/test_position_exit_policy.py`
- 신규 policy trace snapshot test

### Phase 1: Settings Catalog

목표:

- runtime setting이 어느 정책 owner에 속하는지 한 곳에서 관리한다.

Status:

- 2026-06-10 implemented metadata-only catalog in
  `strategy/policy/settings_catalog.py`.
- Every key in `core.runtime_settings.MUTABLE_SETTINGS` is classified with
  owner, scope, risk, mutability, source, and notes.
- Admin API response metadata remains deferred.

작업:

- Done: `strategy/policy/settings_catalog.py`에 setting metadata 추가.
- Done: 필드: `key`, `owner`, `scope`, `risk`, `mutable`, `source`, `notes`.
- Done: `core.runtime_settings.MUTABLE_SETTINGS`와 catalog 불일치 검증 테스트 추가.
- Deferred: admin settings 응답에 owner/risk metadata를 붙이는 것은 별도 단계로 둔다.

검증:

- catalog와 `MUTABLE_SETTINGS` 동기화 테스트.
- admin settings validation 테스트 유지.

### Phase 2: Engine Wrapper

목표:

- 기존 gate 함수 호출 순서는 유지하되 `TradingPolicyEngine.evaluate_buy_path`,
  `evaluate_order_submission`, `evaluate_exit_event`로 진입점을 묶는다.

Status:

- 2026-06-10 implemented behavior-preserving facade in
  `strategy/policy/engine.py`.
- `TradingAgent` buy-path gate calls now go through `TradingPolicyEngine` for
  pre-analysis, Tier1 fast gate, final deterministic gate, cost gate, news gate,
  exposure alignment, and risk manager trace decisions.
- `DecisionMaker` order-submission policy trace paths now go through the engine
  facade while preserving order request construction and broker call behavior.
- Stop-loss/take-profit event trace decisions now use `evaluate_exit_event`.
- Pure mutation removal remains deferred to Phase 3.

작업:

- Done: `TradingAgent`에서 pre gate, fast gate, final gate, cost gate, news gate,
  exposure alignment, risk manager 호출을 engine facade 뒤로 이동한다.
- Done: `DecisionMaker`의 order gate는 `evaluate_order_submission` adapter를 통해 trace를 받는다.
- Done: event stop/take-profit은 `evaluate_exit_event` adapter를 통해 min-hold/staged exit trace를 받는다.

검증:

- 기존 unit/API tests 동일 통과.
- trace에는 모든 기존 reason code가 보존되어야 한다.

### Phase 3: Pure Evaluators

목표:

- 수량/가격/horizon/threshold mutation을 직접 하지 않고 effect로 반환한다.

Status:

- 2026-06-10 implemented Phase 3a for quantity sizing mutation separation.
- `RiskManager.check` no longer mutates `TradeSignal.suggested_quantity`
  directly for guard-based quantity reductions; it returns `adjusted_quantity`
  and adjustment effects for the caller to enforce.
- Aggressive exposure alignment no longer mutates quantity inside the evaluator
  helper; `TradingAgent` applies the returned final quantity at the buy-path
  enforcement point before risk and broker buying-power checks.
- Final order quantity parity is covered by a focused `_analyze_and_trade`
  regression test.
- 2026-06-10 implemented Phase 3c for runtime kill-switch effect split.
- `TradingGuard` now emits explicit `runtime_effects` for `TRADING_ENABLED=false`
  and applies them through `_enforce_runtime_effects`, preserving existing
  kill-switch behavior.
- 2026-06-10 implemented Phase 3b for trade threshold policy split.
- `_resolve_trade_thresholds` now computes stop-loss/take-profit/trailing-stop
  values without writing to `event_detector`; `_enforce_trade_thresholds` owns
  the write.
- `_apply_trade_thresholds` remains as a compatibility wrapper that preserves
  existing caller behavior.

작업:

- Done: `RiskManager.check`에서 guard-based `TradeSignal` quantity 직접 mutation 제거.
- Done: `TradingAgent._apply_aggressive_exposure_alignment`은 quantity decision/effect를 반환하고 caller가 적용.
- Done: `TradingAgent._apply_trade_thresholds`는 threshold policy와 event detector enforcement를 분리.
- Done: kill switch runtime update는 runtime effect로 분리한 뒤 enforcement helper가 실행.

검증:

- mutation parity tests.
- order request parity tests.
- broker call mock으로 실제 주문 파라미터 동일성 검증.

### Phase 4: Policy Registry And Generated Docs

목표:

- 새 정책이 추가될 때 owner, priority, scope, settings, tests를 빠뜨리면 CI에서 잡는다.

Status:

- 2026-06-10 implemented metadata-only registry in
  `strategy/policy/registry.py`.
- `docs/architecture/trading-policy-governance.md` now includes a
  registry-generated policy table.
- Registry tests cover priority order, settings catalog owner coverage,
  required test path existence, and governance doc sync.

작업:

- Done: `strategy/policy/registry.py`에 canonical policy order 선언.
- Done: registry에서 `docs/architecture/trading-policy-governance.md`의 policy owner 표를 생성/검증한다.
- Deferred: prompt contract 변경과 deterministic policy 변경의 추가 자동 체크는 별도 CI 확장으로 둔다.

검증:

- registry completeness test.
- docs consistency test.

## Immediate Implementation Plan

다음 실제 코드 작업은 아래 순서로 진행한다.

1. `strategy/policy/types.py`와 trace adapter만 추가한다.
2. behavior-changing condition은 하나도 바꾸지 않는다.
3. 기존 gate return을 `PolicyDecision`으로 감싸는 helper를 만든다.
4. 신규 테스트는 "기존 결과 동일, trace만 추가"를 검증한다.
5. runtime server 재시작 전 `check_runtime_integrity.py --days 7`로 읽기 전용 점검한다.
6. 정상 확인 후에만 다음 phase로 넘어간다.

## Change Control Rules

정책 변경 PR 또는 task는 반드시 아래를 기록한다.

- policy owner
- affected side: BUY, SELL, HOLDING_EXIT, ORDER_SUBMISSION, CANDIDATE
- behavior impact: increase size, reduce size, block buy, allow sell, force/accelerate sell
- affected runtime settings
- expected trace reason code
- focused tests
- rollback path

## Code, Docs, Agent Alignment

동시에 맞춰야 하는 파일:

- `AGENTS.md`: 정책 변경 시 governance/checklist를 먼저 보도록 안내한다.
- `docs/architecture/trading-policy-governance.md`: priority와 ownership 원칙을 유지한다.
- `docs/workflows/trading-policy-change-checklist.md`: 작업자가 실제 변경 전 점검할 체크리스트다.
- `.agent/tasks/<task-id>/decision-record.md`: 현재 task에서 왜 그렇게 설계했는지 기록한다.
- LLM prompt files: horizon/exit semantics가 바뀌면 deterministic policy 문서와 같이 업데이트한다.
- tests: policy owner별 focused tests와 trace parity tests를 추가한다.

## Non-Goals

이번 계획 문서 작성 단계에서 하지 않는다.

- broker 주문 로직 변경
- runtime DB migration
- 손절/익절 threshold 튜닝
- 후보 수 확대 같은 전략 행동 변경
- OPA 같은 외부 policy engine 도입
- live runtime setting 변경

## Open Risks

- 기존 로직 일부는 runtime DB와 broker snapshot을 읽기 때문에 순수 함수로 바로 옮기기 어렵다.
- `TradingAgent`가 너무 많은 정책 owner를 직접 호출하므로 Phase 2는 작게 나눠야 한다.
- stop loss/take profit 이벤트는 AI 판단이 아닌 fast path라서, 중앙 trace가 없으면 사용자가 계속 "왜 빨리 팔았는지"를 추적하기 어렵다.
- runtime setting override가 코드 default보다 우선하므로, settings catalog가 없으면 재시작 후 의도와 실제 동작이 다시 어긋날 수 있다.

## Acceptance Criteria For Refactor Implementation

- 기존 unit tests가 통과한다.
- BUY 후보가 막힌 경우 어떤 layer가 막았는지 하나의 trace에서 보인다.
- BUY 수량이 바뀐 경우 이전/최종 수량과 owner가 보인다.
- SELL은 BUY-only gate 때문에 막히지 않는다.
- 중장기 horizon의 최소보유/분할청산 정책이 exit event와 LLM review 양쪽에서 같은 owner로 기록된다.
- runtime setting 하나를 추가하면 owner와 validation/test가 없는 상태로 merge되지 않는다.
