# LLM Model/Version Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators choose `Claude Code` or `Codex` separately from the exact model/version used, while preserving a true vendor-default mode and showing a cached official model catalog in the admin UI.

**Architecture:** Keep provider choice, fallback choice, and model choice separate. Add a normalized LLM catalog service that fetches official Anthropic/OpenAI documentation on a TTL cache, annotates each entry with source metadata and certainty, and exposes it through an admin API. Update providers so `DEFAULT` means "do not pass --model", letting the local CLI use its own current default, while custom aliases or pinned versions continue to pass `--model`.

**Tech Stack:** FastAPI, Pydantic settings, local Claude Code CLI, local Codex CLI, vanilla JS admin UI, `pytest`, server-side HTTP fetch/parsing against official docs only.

---

## Scope Notes

- Claude Code is the cleaner case:
  - Official docs and local CLI both document `--model`.
  - Anthropic docs distinguish aliases like `default` / `sonnet` / `opus` from pinned model IDs.
- Codex is the riskier case:
  - Official OpenAI Codex CLI docs support `--model` and config overrides.
  - Official OpenAI Help Center for ChatGPT-plan Codex describes model support differently from developer API model pages.
  - The UI must therefore surface "official docs catalog" as guidance, not as a hard entitlement guarantee.
- The implementation must not silently overwrite current `.env` values in existing installs.
- New installs may default to vendor-default semantics, but existing configured values should continue to work until explicitly changed.

## File Map

- Modify: `core/config.py`
  - Add normalized runtime fields for provider-specific model selection and catalog refresh behavior.
- Modify: `analysis/llm/claude_code_provider.py`
  - Omit `--model` when the operator selected vendor default.
- Modify: `analysis/llm/codex_provider.py`
  - Omit `--model` when the operator selected vendor default.
- Modify: `analysis/llm/llm_factory.py`
  - Report provider/model/default metadata clearly to the admin UI.
- Create: `analysis/llm/model_catalog.py`
  - Fetch, normalize, cache, and validate official provider model metadata.
- Modify: `api/routes/admin.py`
  - Expose settings, catalog, refresh, and optional validation endpoints.
- Modify: `admin/static/index.html`
  - Add provider-specific model selectors and "vendor default" controls.
- Modify: `admin/static/js/app.js`
  - Load catalog, bind selectors, show source metadata, and preserve manual custom entry fallback.
- Modify: `.env.example`
  - Document provider/default/custom model settings.
- Test: `tests/api/test_admin_settings_routes.py`
  - Cover model settings exposure and updates.
- Create: `tests/api/test_admin_llm_catalog_routes.py`
  - Cover catalog shape, fallback behavior, and refresh metadata.
- Test: `tests/analysis/test_codex_provider.py`
  - Cover `DEFAULT` vs explicit model behavior.
- Create: `tests/analysis/test_claude_code_provider.py`
  - Cover `DEFAULT` vs explicit model behavior.
- Test: `tests/analysis/test_llm_factory.py`
  - Cover status payload for provider/model/default state.

### Task 1: Normalize Runtime Settings

**Files:**
- Modify: `core/config.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_settings_routes.py`

- [ ] **Step 1: Write failing settings-route tests for model fields**

Add expectations for:
- `CLAUDE_CODE_MODEL`
- `CLAUDE_CODE_MODEL_TIER1`
- `CLAUDE_CODE_MODEL_TIER2`
- `CODEX_MODEL`
- `CODEX_MODEL_TIER1`
- `CODEX_MODEL_TIER2`

Add expectations that `DEFAULT` is accepted as a legal runtime value.

- [ ] **Step 2: Run the focused settings tests to confirm failure**

Run: `pytest tests/api/test_admin_settings_routes.py -q`
Expected: FAIL because model-setting keys are not yet exposed or validated.

- [ ] **Step 3: Update settings exposure and validation**

Implementation rules:
- Keep current provider fields as-is.
- Accept `DEFAULT` or empty string for model values.
- Do not validate against a hardcoded model-name allowlist.
- Keep runtime updates restart-free, same as current admin settings behavior.

- [ ] **Step 4: Re-run the settings tests**

Run: `pytest tests/api/test_admin_settings_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Sanity-check backward compatibility**

Verify that existing explicit values like `haiku`, `sonnet`, and `gpt-5-codex` still serialize unchanged.

### Task 2: Make Provider Defaults Real Defaults

**Files:**
- Modify: `analysis/llm/claude_code_provider.py`
- Modify: `analysis/llm/codex_provider.py`
- Test: `tests/analysis/test_codex_provider.py`
- Create: `tests/analysis/test_claude_code_provider.py`

- [ ] **Step 1: Write failing provider tests**

Required cases:
- `DEFAULT` or empty string -> command omits `--model`
- explicit alias -> command includes `--model <alias>`
- explicit pinned version -> command includes `--model <pinned-id>`

- [ ] **Step 2: Run provider tests to confirm failure**

Run: `pytest tests/analysis/test_codex_provider.py tests/analysis/test_claude_code_provider.py -q`
Expected: FAIL because providers always pass a model today.

- [ ] **Step 3: Implement model resolution helper**

Rules:
- `DEFAULT` and empty string both mean "no explicit model override".
- Tier-specific field wins over provider-wide field.
- Existing explicit env values still work.
- Codex reasoning-effort override remains intact.

- [ ] **Step 4: Re-run provider tests**

Run: `pytest tests/analysis/test_codex_provider.py tests/analysis/test_claude_code_provider.py -q`
Expected: PASS.

- [ ] **Step 5: Manual CLI smoke checks**

Run lightweight local checks with both CLIs:
- explicit alias
- vendor default mode

Expected:
- command launches successfully when the local account permits the chosen model
- unsupported model errors remain visible and are not swallowed

### Task 3: Build Official Catalog Fetch + Cache Layer

**Files:**
- Create: `analysis/llm/model_catalog.py`
- Modify: `api/routes/admin.py`
- Create: `tests/api/test_admin_llm_catalog_routes.py`
- Test: `tests/analysis/test_llm_factory.py`

- [ ] **Step 1: Write failing catalog-route tests**

Normalized response should include:
- provider id
- entries list
- source URLs
- fetched_at timestamp
- cache_age_sec
- certainty / scope metadata
- stale flag
- local CLI version if available

- [ ] **Step 2: Run the new catalog tests to confirm failure**

Run: `pytest tests/api/test_admin_llm_catalog_routes.py -q`
Expected: FAIL because catalog routes do not exist.

- [ ] **Step 3: Implement provider-specific fetchers**

Anthropic fetcher requirements:
- Pull alias guidance from official Claude Code model-config docs.
- Pull current pinned model IDs from official Anthropic model overview docs.
- Mark aliases as `moving` and pinned versions as `stable`.

OpenAI fetcher requirements:
- Pull Codex CLI configuration capability from official Codex docs.
- Pull current model/snapshot info from official OpenAI model docs.
- Pull ChatGPT-plan Codex support notes from the official OpenAI Help Center.
- Mark entries with scope metadata such as `api-doc`, `chatgpt-plan-doc`, or `cli-doc`.
- If official sources disagree, keep both source references and emit a warning rather than silently picking one.

- [ ] **Step 4: Add TTL caching and graceful fallback**

Rules:
- Cache in memory with a short TTL.
- If fetch fails, return the last successful catalog plus `stale=true`.
- If nothing has ever been fetched, return a minimal built-in seed catalog and surface that it is a fallback.

- [ ] **Step 5: Add optional local validation hook**

Add a lightweight validation mode that tests one selected model against the local CLI on demand.

Rules:
- Do not validate every catalog item automatically.
- Validation result must be shown separately from doc-derived availability.
- A model can be "officially listed" but still fail locally due to account entitlement or CLI version mismatch.

- [ ] **Step 6: Re-run API and factory tests**

Run: `pytest tests/api/test_admin_llm_catalog_routes.py tests/analysis/test_llm_factory.py -q`
Expected: PASS.

### Task 4: Add Admin UI Controls

**Files:**
- Modify: `admin/static/index.html`
- Modify: `admin/static/js/app.js`
- Modify: `api/routes/admin.py`

- [ ] **Step 1: Add failing UI-facing API expectations**

Extend existing admin API tests to require:
- current model mode per provider/tier
- catalog payload availability
- source metadata exposure

- [ ] **Step 2: Add UI controls**

Required controls:
- provider selector (existing)
- provider fallback selector (existing)
- model selector for the active provider
- `기본값 사용` option
- manual custom model/version input
- refresh catalog button
- optional "로컬 CLI로 검증" button

- [ ] **Step 3: Bind UI to catalog + settings**

Rules:
- When provider changes, show that provider's model catalog.
- Always include `기본값 사용` as the first option.
- Preserve manual custom input even if it is not currently in the fetched catalog.
- Show source links and "마지막 동기화 시각".

- [ ] **Step 4: Add discrepancy messaging**

UI copy must distinguish:
- `공식 문서에 있음`
- `로컬 CLI 검증 성공`
- `로컬 CLI 검증 실패`
- `공식 문서 간 범위 차이 있음`

- [ ] **Step 5: Manual browser verification**

Verify in `/admin`:
- provider can change without losing model settings
- choosing `기본값 사용` results in vendor-default semantics
- custom alias/version persists
- catalog refresh updates timestamp and sources

### Task 5: Documentation and Rollout Guardrails

**Files:**
- Modify: `.env.example`
- Optionally modify: `README.md`

- [ ] **Step 1: Document config semantics**

Document:
- provider selection
- fallback selection
- `DEFAULT` / blank behavior
- alias vs pinned version guidance
- "official catalog is advisory; local validation is authoritative for this machine/account"

- [ ] **Step 2: Add rollout notes**

Include:
- existing deployments keep explicit configured models until changed
- new recommended defaults favor vendor-default mode
- dynamic catalog requires outbound access to official docs domains

- [ ] **Step 3: Run the final verification set**

Run:
- `pytest tests/api/test_admin_settings_routes.py tests/api/test_admin_llm_catalog_routes.py tests/analysis/test_codex_provider.py tests/analysis/test_claude_code_provider.py tests/analysis/test_llm_factory.py -q`

Expected: PASS.

## Recommended Implementation Decisions

- Use `DEFAULT` as the UI-visible sentinel and treat empty string equivalently in code.
- Do not auto-rewrite current `.env` values during migration.
- Do not hardcode a closed allowlist of model names.
- Treat official-doc sync as guidance, not entitlement.
- Add provider/scope/source metadata to every catalog entry so the UI can explain why an item is shown.

## Official Source Inputs To Use During Implementation

- Anthropic Claude Code docs:
  - `https://docs.anthropic.com/en/docs/claude-code/model-config`
  - `https://docs.anthropic.com/en/docs/about-claude/models/overview`
  - `https://docs.anthropic.com/en/docs/claude-code/settings`
- OpenAI Codex / model docs:
  - `https://developers.openai.com/codex/cli/reference`
  - `https://developers.openai.com/codex/config-reference`
  - `https://developers.openai.com/api/docs/models/gpt-5-codex`
  - `https://developers.openai.com/api/docs/models`
  - `https://help.openai.com/en/articles/11369540-codex-in-chatgpt-faq`

## Known Risks

- OpenAI's official ChatGPT-plan Codex documentation and developer model pages may not describe the same availability surface.
- Anthropic alias targets move over time by design.
- Local CLI version and account entitlement can invalidate an otherwise "officially documented" model choice.
- Runtime doc fetching can fail or return changed HTML structure; caching and fallback are required.
