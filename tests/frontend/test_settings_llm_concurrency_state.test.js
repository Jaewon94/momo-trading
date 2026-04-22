import { describe, expect, test } from 'vitest';

import {
  buildNewsTranslationConcurrencyFieldState,
  buildTierConcurrencyFieldState,
} from '../../admin/static/js/settings_llm_concurrency_state.js';

describe('settings_llm_concurrency_state', () => {
  test('keeps concurrency editable for non-codex providers', () => {
    expect(
      buildTierConcurrencyFieldState({ tier: 'tier1', provider: 'CLAUDE_CODE' }),
    ).toEqual({
      disabled: false,
      helpText: 'Tier1 호출을 동시에 몇 개까지 허용할지 정합니다.',
      helpTone: 'neutral',
    });
  });

  test('disables concurrency input and shows codex guidance', () => {
    expect(
      buildTierConcurrencyFieldState({ tier: 'tier2', provider: 'CODEX' }),
    ).toEqual({
      disabled: true,
      helpText: 'Codex는 안정성을 위해 실제로 1개씩 직렬 실행됩니다. 이 병렬 값은 Codex 검토 경로에 직접 적용되지 않습니다.',
      helpTone: 'warn',
    });
  });

  test('disables news translation concurrency for codex and ollama', () => {
    expect(
      buildNewsTranslationConcurrencyFieldState({ provider: 'CODEX' }),
    ).toEqual({
      disabled: true,
      helpText: 'Codex는 안정성을 위해 실제로 1개씩 직렬 실행됩니다. 이 병렬 값은 Codex 뉴스 번역 경로에 직접 적용되지 않습니다.',
      helpTone: 'warn',
    });

    expect(
      buildNewsTranslationConcurrencyFieldState({ provider: 'OLLAMA' }),
    ).toEqual({
      disabled: true,
      helpText: 'Ollama는 뉴스 번역을 항상 1개씩 처리합니다. 이 병렬 값은 Ollama 뉴스 번역 경로에 직접 적용되지 않습니다.',
      helpTone: 'warn',
    });
  });
});
