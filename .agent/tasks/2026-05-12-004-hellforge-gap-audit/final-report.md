# Final Report

## 상태

완료.

## 완료 요약

hellforge를 다시 훑고, 공식 문서/베스트 프랙티스/논문까지 확인해서 추가할 부분이 있는지 판단했다.

추가로 반영한 내용:

- `docs/workflows/hellforge-gap-audit.md`: 적용/보류/외부 근거/결론 기록
- `.agent/security-policy.md`: LLM untrusted context와 deterministic broker/order guardrail 정책 추가
- `.agent/domain-packs/trading-system/README.md`: LLM context guardrail과 prompt-injection review trigger 추가
- `scripts/check_docs_consistency.py`: 위 정책이 빠지면 검증 실패하도록 보강

## 확인한 외부 기준

- OpenAI Agents SDK Guardrails / Human-in-the-loop
- Anthropic Claude Code Security / Hooks / Subagents
- NCSC prompt injection guidance
- OWASP Top 10 for LLM Applications
- OWASP Secrets Management Cheat Sheet
- GitHub Actions workflow syntax
- GitHub secret scanning push protection
- NIST SSDF SP 800-218
- 12-Factor App config
- A Survey of Context Engineering for Large Language Models

## 판단

지금 추가해야 할 실질적 보강은 하나였다.

LLM이 보는 뉴스, 공시, 웹 텍스트, 이슈/PR 댓글, broker message, 모델 출력은 모두 untrusted context로 취급해야 한다. 그리고 LLM 판단이 주문/취소/강제청산으로 바로 이어지면 안 되고, deterministic risk/cash/holding/pending/session/user-policy guardrail을 반드시 통과해야 한다.

CI, GitHub push protection, Claude hooks, Discord/OpenACP, runtime adapter는 유용하지만 지금 자동으로 붙이는 것은 과하다. 특히 CI/CD와 hooks는 실행 환경/권한을 바꾸므로 별도 승인 작업으로 분리하는 게 맞다.

## 검증 결과

- `python scripts/check_docs_consistency.py`: passed
- `python scripts/check_markdown_links.py AGENTS.md .agent docs/workflows/hellforge-gap-audit.md docs/workflows/code-commit-harness.md .github`: passed
- `.venv313/bin/python -m pytest tests/scripts/test_check_task_harness.py tests/scripts/test_task_harness.py tests/scripts/test_guard_git_command.py tests/scripts/test_docs_harness_checks.py tests/scripts/test_change_harness.py -q`: 19 passed
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-12-004-hellforge-gap-audit`: passed

## 남은 위험

- GitHub push protection은 repo 설정이라 코드만으로 켤 수 없다.
- CI workflow는 아직 없다. 추가하려면 보호 영역 변경으로 보고 별도 승인 후 진행해야 한다.
- 정책은 추가됐지만, 기존 trading runtime 코드가 모든 지점에서 이 정책을 완벽히 구현하는지는 별도 코드 감사가 필요하다.

## 다음 추천

- 다음 단계로는 “LLM 입력/출력에서 broker-affecting path가 deterministic guardrail을 실제로 모두 통과하는지” 코드 감사를 별도 task로 진행하는 것이 가장 가치가 높다.
