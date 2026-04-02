export function buildCodexAuthLabel(codex = {}) {
  const authBits = [];
  if (codex?.auth?.logged_in) {
    authBits.push("로그인됨");
  } else {
    authBits.push("로그인 확인 필요");
  }
  if (codex?.auth?.auth_mode) {
    authBits.push(codex.auth.auth_mode);
  }
  return authBits.join(" · ");
}

export function buildCodexUsageCopy(codex = {}) {
  return {
    supportedLabel: "공식 지원: 로그인 상태 확인, 플랜별 일반 사용량 정책 안내",
    unsupportedLabel: "공식 미지원: 로컬 잔여 사용량 퍼센트, 정확한 리셋 타이머",
    detail:
      codex?.official?.availability_reason ||
      "OpenAI 공식 문서상 플랜별 사용량 정책은 안내되지만, local environment usage는 제공되지 않습니다.",
  };
}

export function buildClaudeUsageCopy() {
  return {
    supportedLabel: "공식 지원: 5시간/7일 사용률, 리셋 시각, 컨텍스트 잔량",
    appUsageLabel: "현재 서버 실행 누적 호출",
    appCostLabel: "현재 서버 실행 누적 비용",
    historyLabel: "로컬 히스토리 세션",
  };
}
