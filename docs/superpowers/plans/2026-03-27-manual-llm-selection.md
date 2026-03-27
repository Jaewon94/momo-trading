# Manual LLM Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin에서 수동 AI 작업 실행 전에 `자동/Claude Code/Codex`를 선택하고, 그 선택이 `Q&A`, `수동 사이클 실행`, `리포트 생성`에만 적용되도록 만든다.

**Architecture:** 자동 파이프라인용 Tier 설정과 별개로 수동 작업 전용 runtime override를 추가한다. UI는 설정 조회/변경만 담당하고, 실제 provider 해석은 서버의 작은 해석 계층과 `LLMFactory`가 담당한다. 수동 사이클은 실행 시점 snapshot을 받아 비동기 실행 중 설정 경합을 피한다.

**Tech Stack:** FastAPI, Pydantic Settings, pytest/pytest-asyncio, vanilla JS Admin UI, existing Claude Code/Codex CLI providers

---

## File Structure

- Modify: `core/config.py`
  - 수동 작업 전용 provider 설정 필드 추가
- Modify: `analysis/llm/llm_factory.py`
  - 수동 override 해석과 수동 generate entrypoint 추가
- Modify: `api/routes/admin.py`
  - settings/llm-status 확장, 수동 작업 API에 override 적용
- Modify: `services/daily_report_service.py`
  - 수동 리포트용 provider override 주입 경로 추가
- Modify: `agent/trading_agent.py`
  - 수동 사이클 실행용 provider snapshot 인자 추가
- Modify: `admin/static/index.html`
  - 수동 작업 AI 선택 UI 추가
- Modify: `admin/static/js/app.js`
  - 설정 로드/업데이트/상태 표시/액션 설명 반영
- Modify or Create: `tests/analysis/test_llm_factory.py`
  - 수동 override 해석 테스트 추가
- Modify or Create: `tests/api/test_admin_settings_routes.py`
  - settings/llm-status API 테스트
- Modify or Create: `tests/api/test_admin_qa_routes.py`
  - Q&A 수동 provider 적용 테스트
- Modify or Create: `tests/api/test_admin_manual_actions.py`
  - 수동 사이클/리포트 override 전달 테스트

### Task 1: Add Manual Provider Setting Contract

**Files:**
- Modify: `core/config.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_settings_routes.py`

- [ ] **Step 1: Write the failing settings API test**

```python
async def test_admin_settings_exposes_manual_llm_provider(async_client):
    response = await async_client.get("/api/v1/admin/settings")
    assert response.status_code == 200
    assert "MANUAL_LLM_PROVIDER" in response.json()["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_admin_settings_routes.py::test_admin_settings_exposes_manual_llm_provider -v`
Expected: FAIL because `MANUAL_LLM_PROVIDER` is missing from settings payload.

- [ ] **Step 3: Write the failing update test**

```python
async def test_admin_settings_updates_manual_llm_provider(async_client):
    response = await async_client.put("/api/v1/admin/settings", json={"MANUAL_LLM_PROVIDER": "CODEX"})
    assert response.status_code == 200

    settings_response = await async_client.get("/api/v1/admin/settings")
    assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "CODEX"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/api/test_admin_settings_routes.py::test_admin_settings_updates_manual_llm_provider -v`
Expected: FAIL because updates reject unknown setting.

- [ ] **Step 5: Implement minimal config and admin settings support**

Implementation notes:
- Add `MANUAL_LLM_PROVIDER: str = "AUTOMATIC"` to `Settings`
- Add it to `MUTABLE_SETTINGS`
- Return it from `/admin/settings`
- Allow update validation for `AUTOMATIC`, `CLAUDE_CODE`, `CODEX`

- [ ] **Step 6: Run settings tests to verify they pass**

Run: `pytest tests/api/test_admin_settings_routes.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/config.py api/routes/admin.py tests/api/test_admin_settings_routes.py
git commit -m "feat: add manual llm provider runtime setting"
```

### Task 2: Add Manual Provider Resolution To LLMFactory

**Files:**
- Modify: `analysis/llm/llm_factory.py`
- Test: `tests/analysis/test_llm_factory.py`

- [ ] **Step 1: Write the failing AUTOMATIC resolution test**

```python
@pytest.mark.asyncio
async def test_llm_factory_manual_generate_uses_tier_defaults_when_automatic(monkeypatch):
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "AUTOMATIC")
    ...
    result, provider = await factory.generate_manual("hello", default_tier=LLMTier.TIER1)
    assert provider == "CODEX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_llm_factory.py::test_llm_factory_manual_generate_uses_tier_defaults_when_automatic -v`
Expected: FAIL because `generate_manual` does not exist.

- [ ] **Step 3: Write the failing explicit provider tests**

```python
@pytest.mark.asyncio
async def test_llm_factory_manual_generate_forces_claude(monkeypatch):
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CLAUDE_CODE")
    ...
    assert provider == "CLAUDE_CODE"

@pytest.mark.asyncio
async def test_llm_factory_manual_generate_forces_codex(monkeypatch):
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CODEX")
    ...
    assert provider == "CODEX"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/analysis/test_llm_factory.py -k manual_generate -v`
Expected: FAIL because manual resolution path is absent.

- [ ] **Step 5: Implement minimal manual resolution path**

Implementation notes:
- Add a small parser for manual setting
- Keep existing `generate()` untouched for automatic pipeline usage
- Add `generate_manual(..., default_tier=...)`
- Add `manual_selection` info to `get_llm_status()`

- [ ] **Step 6: Run LLM factory tests to verify they pass**

Run: `pytest tests/analysis/test_llm_factory.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add analysis/llm/llm_factory.py tests/analysis/test_llm_factory.py
git commit -m "feat: add manual llm provider resolution"
```

### Task 3: Apply Manual Selection To Q&A

**Files:**
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_qa_routes.py`

- [ ] **Step 1: Write the failing Q&A override test**

```python
async def test_admin_qa_uses_manual_llm_provider(async_client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CODEX")
    called = {}

    async def fake_generate_manual(prompt, system_prompt="", default_tier=None, **kwargs):
        called["default_tier"] = default_tier
        return "answer", "CODEX"

    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_manual", fake_generate_manual)
    response = await async_client.post("/api/v1/admin/qa/ask", json={"question": "요약해줘"})
    assert response.status_code == 200
    assert response.json()["data"]["llm_provider"] == "CODEX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_admin_qa_routes.py::test_admin_qa_uses_manual_llm_provider -v`
Expected: FAIL because route still calls `generate_tier1`.

- [ ] **Step 3: Implement minimal Q&A change**

Implementation notes:
- Swap `generate_tier1` for `generate_manual`
- Use `default_tier=LLMTier.TIER1`
- Keep Q&A prompt construction unchanged

- [ ] **Step 4: Run Q&A tests to verify they pass**

Run: `pytest tests/api/test_admin_qa_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/admin.py tests/api/test_admin_qa_routes.py
git commit -m "feat: apply manual llm selection to admin qa"
```

### Task 4: Apply Manual Selection To Manual Report Generation

**Files:**
- Modify: `services/daily_report_service.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_manual_actions.py`

- [ ] **Step 1: Write the failing manual report test**

```python
async def test_manual_report_generation_passes_manual_provider(async_client, monkeypatch):
    captured = {}

    async def fake_generate_daily_report(target_date=None, manual_provider_override=None):
        captured["manual_provider_override"] = manual_provider_override
        return None

    monkeypatch.setattr("services.daily_report_service.daily_report_service.generate_daily_report", fake_generate_daily_report)
    await async_client.post("/api/v1/admin/reports/generate")
    assert captured["manual_provider_override"] == "CODEX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_admin_manual_actions.py::test_manual_report_generation_passes_manual_provider -v`
Expected: FAIL because route/service do not pass override.

- [ ] **Step 3: Implement minimal report override threading**

Implementation notes:
- Extend service signature with optional `manual_provider_override`
- Use override only for route-originated manual generation path
- Leave scheduled/automatic report generation unchanged

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_admin_manual_actions.py -k report -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/admin.py services/daily_report_service.py tests/api/test_admin_manual_actions.py
git commit -m "feat: apply manual llm selection to report generation"
```

### Task 5: Apply Manual Selection Snapshot To Manual Cycle Trigger

**Files:**
- Modify: `agent/trading_agent.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_manual_actions.py`

- [ ] **Step 1: Write the failing manual cycle snapshot test**

```python
async def test_manual_cycle_trigger_captures_manual_provider(async_client, monkeypatch):
    captured = {}

    async def fake_run_cycle(*, manual_provider_override=None):
        captured["manual_provider_override"] = manual_provider_override

    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    await async_client.post("/api/v1/admin/agent/trigger")
    assert captured["manual_provider_override"] == "CLAUDE_CODE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_admin_manual_actions.py::test_manual_cycle_trigger_captures_manual_provider -v`
Expected: FAIL because trigger does not pass snapshot.

- [ ] **Step 3: Implement minimal cycle snapshot support**

Implementation notes:
- Add optional `manual_provider_override` parameter to `run_cycle`
- Pass snapshot from trigger route before `asyncio.create_task`
- Ensure analysis/review calls inside that run use the snapshot instead of global mutable state

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_admin_manual_actions.py -k cycle -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/admin.py agent/trading_agent.py tests/api/test_admin_manual_actions.py
git commit -m "feat: snapshot manual llm selection for manual cycles"
```

### Task 6: Expose Status In LLM Status API

**Files:**
- Modify: `analysis/llm/llm_factory.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_settings_routes.py`

- [ ] **Step 1: Write the failing status test**

```python
async def test_llm_status_includes_manual_selection(async_client):
    response = await async_client.get("/api/v1/admin/llm/status")
    assert response.status_code == 200
    assert "manual_selection" in response.json()["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_admin_settings_routes.py::test_llm_status_includes_manual_selection -v`
Expected: FAIL because status payload lacks manual selection.

- [ ] **Step 3: Implement minimal status extension**

Implementation notes:
- Include current manual selection
- Include resolved label/options if helpful for UI

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_admin_settings_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/llm/llm_factory.py api/routes/admin.py tests/api/test_admin_settings_routes.py
git commit -m "feat: expose manual llm selection status"
```

### Task 7: Add Admin UI For Manual LLM Selection

**Files:**
- Modify: `admin/static/index.html`
- Modify: `admin/static/js/app.js`
- Test: manual verification notes in plan

- [ ] **Step 1: Add the failing UI expectation to the plan checklist**

Manual verification target:
- Settings area shows `수동 작업 AI`
- Current selection loads from API
- Changing selection persists without refresh
- Action labels remain unchanged

- [ ] **Step 2: Implement minimal UI**

Implementation notes:
- Add select element in settings section
- Reuse `loadSettings()` and `updateSetting()`
- Extend `loadLLMStatus()` to show manual selection text
- Keep copy explicit: `Q&A / 수동 사이클 / 리포트 생성에만 적용`

- [ ] **Step 3: Verify UI manually**

Run:
- Open `/admin`
- Change selection between `자동`, `Claude Code`, `Codex`
- Refresh page and confirm persistence
- Execute a manual Q&A and confirm returned provider matches selection

Expected: selection is visible, persists, and affects manual actions only.

- [ ] **Step 4: Commit**

```bash
git add admin/static/index.html admin/static/js/app.js
git commit -m "feat: add manual llm selection controls to admin"
```

### Task 8: Regression Test Pass

**Files:**
- Test only: existing suites touching admin/llm/manual actions

- [ ] **Step 1: Run focused regression tests**

Run:
```bash
pytest tests/analysis/test_llm_factory.py tests/api/test_admin_settings_routes.py tests/api/test_admin_qa_routes.py tests/api/test_admin_manual_actions.py -v
```

Expected: PASS

- [ ] **Step 2: Run broader admin-related regression**

Run:
```bash
pytest tests/api/test_admin_account_routes.py tests/main/test_lifespan_startup.py -v
```

Expected: PASS

- [ ] **Step 3: Review for SOLID / separation concerns**

Checklist:
- Routes do not implement provider decision logic inline
- Automatic tier config path still works untouched
- Manual cycle uses snapshot, not late global read
- UI does not hardcode backend business rules beyond labels/options

- [ ] **Step 4: Commit final integration**

```bash
git add .
git commit -m "feat: support manual llm selection for admin actions"
```

## Notes For Execution

- Prefer adding a tiny helper abstraction instead of sprinkling `if settings.MANUAL_LLM_PROVIDER == ...` across routes.
- Keep automatic and manual entrypoints separate to avoid accidental behavior drift.
- If manual cycle override propagation becomes invasive, extract a lightweight execution context object instead of threading raw strings everywhere.
