import { ConfigProvider } from "@arco-design/web-react";
import enUS from "@arco-design/web-react/es/locale/en-US";
import zhCN from "@arco-design/web-react/es/locale/zh-CN";
import type { i18n } from "i18next";
import { useEffect, useState } from "react";
import { I18nextProvider } from "react-i18next";
import { Navigate, Route, Routes } from "react-router-dom";
import { createI18n } from "./i18n";
import { AppLayout } from "./layouts/AppLayout";
import { ComparePage } from "./pages/ComparePage";
import { GuidePage } from "./pages/GuidePage";
import { InputPage } from "./pages/InputPage";
import { LoginPage } from "./pages/LoginPage";
import { PlanPage } from "./pages/PlanPage";
import { PricePage } from "./pages/PricePage";
import { ReplayPage } from "./pages/ReplayPage";
import { WeekPage } from "./pages/WeekPage";
import { usePrefs } from "./state/prefs";

export function App() {
  const { lang } = usePrefs();
  const [inst, setInst] = useState<i18n | null>(null);
  useEffect(() => {
    let alive = true;
    createI18n(lang).then((i) => { if (alive) setInst(i); });
    return () => { alive = false; };
  }, []);                                   // 实例只创建一次，语言变化时 changeLanguage
  useEffect(() => { inst?.changeLanguage(lang); }, [lang, inst]);
  if (!inst) return null;
  return (
    <I18nextProvider i18n={inst}>
      <ConfigProvider locale={lang === "zh" ? zhCN : enUS}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppLayout />}>
            <Route path="/guide" element={<GuidePage />} />
            <Route path="/input" element={<InputPage />} />
            <Route path="/week" element={<WeekPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/plan" element={<PlanPage />} />
            <Route path="/replay" element={<ReplayPage />} />
            <Route path="/price" element={<PricePage />} />
            <Route path="*" element={<Navigate to="/replay" replace />} />
          </Route>
        </Routes>
      </ConfigProvider>
    </I18nextProvider>
  );
}
