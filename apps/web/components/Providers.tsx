"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Lang, tr } from "@/lib/i18n";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; theme: string; toggleTheme: () => void };
const C = createContext<Ctx>({ lang: "en", setLang: () => {}, t: (k) => k, theme: "light", toggleTheme: () => {} });
export const useApp = () => useContext(C);

export function Providers({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  const [theme, setTheme] = useState("light");
  useEffect(() => {
    try {
      const l = localStorage.getItem("cg_lang") as Lang | null;
      if (l && ["en", "uz", "ru"].includes(l)) setLangState(l);
    } catch {}
    setTheme(document.documentElement.dataset.theme || "light");
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("cg_lang", l); } catch {}
    document.documentElement.lang = l;
  }, []);
  const toggleTheme = useCallback(() => {
    const n = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = n;
    setTheme(n);
    try { localStorage.setItem("cg_theme", n); } catch {}
  }, []);
  const t = useCallback((k: string) => tr(k, lang), [lang]);
  return <C.Provider value={{ lang, setLang, t, theme, toggleTheme }}>{children}</C.Provider>;
}
