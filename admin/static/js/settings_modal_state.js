export const SETTINGS_TABS = ["operating", "strategy", "news", "llm", "system"];

export function normalizeSettingsTab(tab = "") {
  return SETTINGS_TABS.includes(tab) ? tab : SETTINGS_TABS[0];
}
