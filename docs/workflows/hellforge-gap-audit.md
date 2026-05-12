# Hellforge Gap Audit

Date: 2026-05-12

Purpose: hellforge를 다시 훑어본 뒤 momo-trading에 이미 적용한 것, 추가로 적용한 것, 지금은 보류할 것을 정리한다.

## Applied

### Context And Task Artifacts

- `AGENTS.md`
- `.agent/project-card.md`
- `.agent/security-policy.md`
- `.agent/current-task.json`
- `.agent/tasks/<task-id>/`
- `scripts/check_task_harness.py`
- `scripts/task_harness.py`

Reason: 긴 대화에 의존하지 않고 작업 목표, 결정, 검증 결과를 파일로 남기는 것이 momo-trading 운영에 바로 필요하다.

### Code And Commit Harness

- `scripts/guard_git_command.py`
- `scripts/check_markdown_links.py`
- `scripts/check_docs_consistency.py`
- `docs/workflows/code-commit-harness.md`
- `task_harness.py verify`

Reason: commit/push 승인 경계, secret scan, docs consistency, pre-commit readiness를 repo-local script로 강제할 수 있다.

### Risk, Role, And Trading Domain Pack

- `scripts/change_harness.py`
- `.agent/domain-packs/trading-system/README.md`
- `.agent/templates/council-report.md`
- `.agent/templates/handoff.md`
- `.agent/templates/incident.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/trading_change.md`

Reason: momo-trading은 매매, 브로커, DB, LLM runtime, admin UI가 섞여 있어 파일 변경만 봐도 reviewer와 검증 방향을 분류할 필요가 있다.

## Reviewed And Deferred

### Runtime Adapter Contract

Hellforge reference:

- `docs/architecture/runtime-adapter-design.md`
- `hellforge/services/runtimes.py`

Decision: defer.

Reason:

- momo-trading already has app-level LLM provider/runtime selection code.
- Hellforge runtime adapter is for running coding agents, not trading analysis providers.
- Adding a second runtime catalog now would duplicate existing LLM settings unless a separate "coding agent orchestration" feature is started.

Trigger to revisit:

- We decide to run Codex/Claude/Gemini as repo maintenance workers from inside a separate control plane.
- We need same-task multi-runtime comparison for coding tasks, not stock analysis.

### Discord/OpenACP Control Plane

Hellforge reference:

- `docs/workflows/openacp-discord-preflight.md`
- `docs/workflows/discord-readonly-mvp.md`
- `discord_bot/`

Decision: defer.

Reason:

- momo-trading currently needs local operational safety more than a Discord command surface.
- A control plane would introduce secrets, authorization, deployment, and incident-response obligations.
- Read-only status checks can remain local/admin UI until a separate operator workflow is requested.

Trigger to revisit:

- We want remote approval buttons, task status threads, or incident alerts outside the admin UI.

### GitHub Issue / PR / Release Automation

Hellforge reference:

- `docs/workflows/github-issue-pr-release.md`
- `hellforge/adapters/github_cli.py`
- `hellforge/services/pull_requests.py`

Decision: partially applied, automation deferred.

Applied:

- PR template
- trading change issue template
- commit/push/PR approval policy in docs

Deferred:

- automatic issue creation
- automatic commit/push/PR
- CI status collection
- release/deploy orchestration

Reason:

- Commit, push, PR, merge, deploy, and migration are approval boundaries.
- CI/CD changes are protected and should be a separate task.

Trigger to revisit:

- User explicitly asks to connect GitHub issue/PR automation or CI.

### Documentation System

Hellforge reference:

- `docs/documentation/documentation-system.md`
- `templates/documentation-audit-report.md`

Decision: partially applied.

Applied:

- docs consistency check
- markdown link check
- workflow docs for code/commit harness
- final reports in task artifacts

Deferred:

- full docs index system
- documentation audit report template
- broad stale-doc scanner for all historical docs

Reason:

- momo-trading has many Korean enhancement/audit docs already; imposing the full hellforge docs tree would create churn.
- Current harness docs are enough for operational use.

Trigger to revisit:

- Docs become hard to navigate or CI should enforce all doc links.

### Repo Registry / Multi-Repo Management

Hellforge reference:

- `.agent/repos.json`
- `.agent/repos/`
- `repo_registry.py`

Decision: not applicable now.

Reason:

- This workspace task targets one repo, `momo-trading`.
- A registry becomes useful only when one harness controls multiple target repos.

Trigger to revisit:

- We want a parent control repo to operate several projects.

### Claude Settings / Hooks

Hellforge reference:

- `.claude/settings.json`
- Claude Code hook notes

Decision: defer.

Reason:

- Editing tool-specific local permission hooks changes developer environment behavior.
- Current repo-level scripts provide the source of truth without coupling to one coding agent.

Trigger to revisit:

- User explicitly asks to install local Claude/Codex hooks.

## Remaining Useful Follow-Ups

1. CI integration: run `scripts/check_task_harness.py`, `scripts/guard_git_command.py scan-secrets`, docs checks, and focused tests in GitHub Actions.
2. Worktree workflow: add optional helper for task branch/worktree creation if concurrent coding work becomes frequent.
3. Runtime audit: map momo-trading's existing LLM provider settings against hellforge's runtime capability vocabulary, but only for trading analysis providers.
4. Documentation audit: add a broader stale-doc/link audit if docs become a maintenance problem.

## External Research Check

Checked on 2026-05-12:

- OpenAI Agents SDK Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- OpenAI Agents SDK Human-in-the-loop: https://openai.github.io/openai-agents-python/human_in_the_loop/
- Anthropic Claude Code Security: https://docs.anthropic.com/en/docs/claude-code/security
- Anthropic Claude Code Hooks: https://docs.anthropic.com/en/docs/claude-code/hooks
- Anthropic Claude Code Subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- NCSC prompt injection guidance: https://www.ncsc.gov.uk/blog-post/prompt-injection-is-not-sql-injection
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- GitHub Actions workflow syntax: https://docs.github.com/actions/reference/workflows-and-actions/workflow-syntax
- GitHub secret scanning push protection: https://docs.github.com/code-security/secret-scanning/protecting-pushes-with-secret-scanning
- NIST SSDF SP 800-218: https://www.nist.gov/publications/secure-software-development-framework-ssdf-version-11-recommendations-mitigating-risk
- 12-Factor App config: https://www.12factor.net/config
- A Survey of Context Engineering for Large Language Models: https://huggingface.co/papers/2507.13334

Research implications:

- Context engineering should manage retrieval, processing, and lifecycle context, not just prompt text. The repo now has project card, task brief, run log, final report, and domain pack artifacts.
- Prompt injection cannot be treated as fully solved by prompts. The trading policy now treats all external text and model output as untrusted.
- Tool guardrails matter more than agent-level prompt rules when actions have side effects. Broker/order actions must remain behind deterministic checks and user-configured policy.
- Human-in-the-loop is appropriate for commit/push/PR/deploy/migration and destructive DB/broker operations. Normal auto-trading can still run only within preconfigured deterministic constraints.
- Secret scanning should exist locally and, later, in GitHub push protection/CI. Local scan is implemented; GitHub push protection is a repo setting and cannot be enabled from code alone.
- CI is useful but protected. It should be a separate approved task, not silently added during harness setup.

Additional change made from this research:

- `.agent/security-policy.md` now includes explicit LLM/untrusted context and deterministic broker guardrail rules.
- `.agent/domain-packs/trading-system/README.md` now includes LLM context guardrails and prompt-injection review triggers.

## Conclusion

No additional hellforge component should be copied wholesale right now. The useful repo-local parts have been applied. External best-practice review suggests one important policy hardening: treat all external LLM context and model output as untrusted, and require deterministic broker/order guardrails. That hardening has been added.
