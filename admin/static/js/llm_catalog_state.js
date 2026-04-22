function formatCatalogDateTime(ts) {
  if (!ts) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(ts));
  } catch {
    return ts;
  }
}

export function buildCatalogMetaText(catalog) {
  if (!catalog) {
    return "공식 모델 목록 불러오는 중...";
  }

  const parts = [];
  if (catalog.fetched_at) {
    parts.push(`동기화 ${formatCatalogDateTime(catalog.fetched_at)}`);
  } else {
    parts.push("내장 seed 목록 사용 중");
  }
  if (catalog.stale) parts.push("이전 동기화 캐시 사용 중");
  if (catalog.fetch_error) parts.push(`일부 참고 문서 접근 실패: ${catalog.fetch_error}`);
  return parts.join(" · ");
}

export function buildCatalogErrorCopy(error) {
  const message = error?.message || "알 수 없는 오류";
  return `공식 모델 목록 새로고침 실패: ${message}`;
}
