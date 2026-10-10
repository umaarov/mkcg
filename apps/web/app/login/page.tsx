"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/components/Providers";
import { Logo } from "@/components/Shell";
import { Button } from "@/components/ui";
import { api, getUser, setUser } from "@/lib/api";
import { LANGS } from "@/lib/i18n";

export default function Login() {
  const { t, lang, setLang } = useApp();
  const router = useRouter();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (getUser()) router.replace("/"); }, [router]);

  async function go(fn: () => Promise<any>) {
    setBusy(true); setErr("");
    try { setUser(await fn()); router.replace("/"); } catch (e: any) { setErr(e.message || "failed"); } finally { setBusy(false); }
  }
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      <div className="relative hidden lg:flex flex-col justify-between bg-[#14211b] p-14 text-[#ecebe3]">
        <Logo size={24} light />
        <div className="max-w-[560px] rise">
          <h1 className="serif text-[46px] leading-[1.08]">{t("login.tag")}</h1>
          <p className="mt-5 text-[15.5px] leading-7 text-[#b9c4bd]">{t("login.sub")}</p>
          <dl className="mt-10 grid grid-cols-3 gap-6 border-t border-white/10 pt-6">
            {[["OCRGate", "uz · ru · scans"], ["RulesEngine", "policy as data"], ["FGate", "signed audit"]].map(([a, b]) => (
              <div key={a}><dt className="text-[13px] font-medium">{a}</dt><dd className="text-[12px] text-[#8fa097]">{b}</dd></div>
            ))}
          </dl>
        </div>
        <p className="text-[11.5px] text-[#8fa097]">{t("ft.disclaimer")}</p>
      </div>
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[380px]">
          <div className="mb-8 flex items-center justify-between lg:hidden"><Logo /></div>
          <div className="mb-6 flex justify-end gap-1">
            {LANGS.map((l) => (
              <button key={l.code} onClick={() => setLang(l.code)} className={`rounded px-2 py-1 text-[11px] font-medium ${lang === l.code ? "bg-ink text-bg" : "text-muted"}`}>{l.label}</button>
            ))}
          </div>
          <h2 className="serif text-[28px]">CreditGateway</h2>
          <p className="mt-1 text-[13px] text-muted">{t("login.notice")}</p>
          <Button className="mt-6 w-full !py-3" disabled={busy} onClick={() => go(() => api("/api/auth/guest", { method: "POST" }))}>{t("login.guest")}</Button>
          <div className="my-6 flex items-center gap-3 text-[11.5px] text-muted"><span className="h-px flex-1 bg-line" />{t("login.or")}<span className="h-px flex-1 bg-line" /></div>
          <form onSubmit={(e) => { e.preventDefault(); go(() => api("/api/auth/login", { method: "POST", json: { username: u, password: p } })); }} className="space-y-3">
            <label className="block text-[12px] text-muted">{t("login.user")}
              <input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" className="mt-1 w-full rounded-lg border border-line-2 bg-surface px-3 py-2 text-[14px] text-ink" /></label>
            <label className="block text-[12px] text-muted">{t("login.pass")}
              <input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" className="mt-1 w-full rounded-lg border border-line-2 bg-surface px-3 py-2 text-[14px] text-ink" /></label>
            {err && <p className="text-[12.5px] text-bad" role="alert">{err}</p>}
            <Button type="submit" variant="ghost" className="w-full" disabled={busy || !u}>{t("login.signin")}</Button>
          </form>
          <div className="mt-6 rounded-lg border border-line bg-surface-2 p-3 text-[12px] text-ink-2">
            <div className="font-medium text-ink">Demo accounts</div>
            <div className="mt-1 tnum">officer1 · committee1 · admin1</div>
            <div className="tnum">password: creditgateway</div>
          </div>
        </div>
      </div>
    </div>
  );
}
