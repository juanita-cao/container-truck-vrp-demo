import i18next, { type i18n } from "i18next";
import { initReactI18next } from "react-i18next";
import { en } from "./en";
import { zh } from "./zh";

export type Lang = "en" | "zh";

// 每次调用创建独立实例：测试和用户之间不通过全局状态共享语言（同 TCE）
export async function createI18n(language: Lang): Promise<i18n> {
  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: "en",
    resources: { en: { translation: en }, zh: { translation: zh } },
    interpolation: { escapeValue: false },
    returnNull: false,
  });
  return instance;
}

// 首次进入：URL ?lang= 优先，其次本地偏好，最后浏览器语言（不是中文则英文）
export function detectLanguage(search: string, stored: string | null, navigatorLanguage: string): Lang {
  const q = new URLSearchParams(search).get("lang");
  if (q === "en" || q === "zh") return q;
  if (stored === "en" || stored === "zh") return stored;
  return navigatorLanguage.toLowerCase().startsWith("zh") ? "zh" : "en";
}
