export function getCatalogProvider(catalog, provider) {
  return catalog?.providers?.find((item) => item.id === provider) || null;
}

export function buildProviderModelEntries(providerCatalog, currentValue, defaultSuffix = "[기본값]") {
  const entries = providerCatalog?.entries
    ? [...providerCatalog.entries]
    : [{ value: "DEFAULT", label: "기본값 사용" }];

  if (currentValue && !entries.some((item) => item.value === currentValue)) {
    entries.push({
      value: currentValue,
      label: `${currentValue} (custom)`,
      kind: "custom",
      stability: "custom",
      source_scope: "manual",
      source_url: "",
    });
  }

  return entries.map((item) => ({
    ...item,
    label:
      item.value === "DEFAULT"
        ? (item.label || "기본값 사용")
        : item.value,
    suffix:
      item.kind === "snapshot"
        ? " [고정]"
        : item.value === "DEFAULT"
          ? ` ${defaultSuffix}`
          : "",
  }));
}

export function buildProviderModelSourceText(providerCatalog, entries, currentValue) {
  const selected = entries.find((item) => item.value === currentValue);
  const sourceBits = [];
  if (selected?.source_scope) sourceBits.push(`출처: ${selected.source_scope}`);
  if (selected?.stability) sourceBits.push(`성격: ${selected.stability}`);
  if (providerCatalog?.cli_version) sourceBits.push(`CLI ${providerCatalog.cli_version}`);
  return sourceBits.join(" · ");
}

export function getProviderModelPlaceholder(provider) {
  if (provider === "CODEX") return "예: gpt-5-codex / gpt-5.4";
  if (provider === "OLLAMA") return "예: llama3.1:8b / qwen2.5:14b";
  return "예: sonnet / claude-sonnet-4-6";
}
