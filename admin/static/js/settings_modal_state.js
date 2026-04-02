export const SETTINGS_TABS = ["operating", "strategy", "llm", "system"];

export function normalizeSettingsTab(tab = "") {
  return SETTINGS_TABS.includes(tab) ? tab : SETTINGS_TABS[0];
}
