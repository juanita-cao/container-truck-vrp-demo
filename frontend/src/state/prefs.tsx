import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { detectLanguage, type Lang } from "../i18n";

export interface Prefs { lang: Lang; dataset: string; instance: string | null; company: string | null }
interface Ctx extends Prefs {
  setLang: (l: Lang) => void; setDataset: (d: string) => void; setInstance: (i: string | null) => void; setCompany: (c: string | null) => void;
  recent: RecentRun[]; addRecent: (r: RecentRun) => void;
}
export interface RecentRun { run_id: string; instance: string; dataset: string; method: string; at: string }

const KEY = "drayage.prefs.v1";
const RKEY = "drayage.recent.v1";
const safe = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* 隐私模式等：页面照常工作 */ } },
};

function load(): Prefs {
  let stored: Partial<Prefs> = {};
  try { stored = JSON.parse(safe.get(KEY) ?? "{}"); } catch { /* ignore */ }
  const q = new URLSearchParams(window.location.search);
  return {
    lang: detectLanguage(window.location.search, stored.lang ?? null, navigator.language),
    dataset: "demo_sg",                      // 界面只面向新加坡演示
    instance: q.get("instance") ?? stored.instance ?? null,
    company: stored.company ?? null,
  };
}

const PrefsContext = createContext<Ctx | null>(null);
export function PrefsProvider({ children }: { children: ReactNode }) {
  const [p, setP] = useState<Prefs>(load);
  const [recent, setRecent] = useState<RecentRun[]>(() => { try { return JSON.parse(safe.get(RKEY) ?? "[]"); } catch { return []; } });
  useEffect(() => { safe.set(KEY, JSON.stringify(p)); document.documentElement.lang = p.lang === "zh" ? "zh-CN" : "en"; }, [p]);
  const addRecent = useCallback((r: RecentRun) => setRecent((cur) => {
    const next = [r, ...cur.filter((x) => x.run_id !== r.run_id)].slice(0, 12);
    safe.set(RKEY, JSON.stringify(next));
    return next;
  }), []);
  const value = useMemo<Ctx>(() => ({
    ...p, recent, addRecent,
    setLang: (lang) => setP((s) => ({ ...s, lang })),
    setDataset: (dataset) => setP((s) => ({ ...s, dataset, instance: null })),
    setInstance: (instance) => setP((s) => ({ ...s, instance })),
    setCompany: (company) => setP((s) => ({ ...s, company })),
  }), [p, recent, addRecent]);
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}
export function usePrefs(): Ctx {
  const c = useContext(PrefsContext);
  if (!c) throw new Error("PrefsProvider missing");
  return c;
}
