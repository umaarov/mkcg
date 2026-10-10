"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { useApp } from "@/components/Providers";
import { Button, Card, Chip, H, Skeleton, bandTone, recTone } from "@/components/ui";
import { api } from "@/lib/api";
import { dt, mln, nf0 } from "@/lib/format";

type Sample = { key: string; lang: string; layout: string; degrade: string | null; title: Record<string, string> };

const ROUTE: Record<string, string> = { null: "digital PDF", scan: "scanned", photo: "phone photo" };
const DOCLANG: Record<string, string> = { uz: "Uzbek (Latin)", uzc: "Uzbek (Cyrillic)", ru: "Russian" };

export default function Queue() {
  const { t, lang } = useApp();
  const router = useRouter();
  const [cases, setCases] = useState<any[] | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [amount, setAmount] = useState("120000000");
  const [term, setTerm] = useState("24");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api("/api/cases").then(setCases).catch(() => setCases([]));
  useEffect(() => {
    load();
    api("/api/samples").then(setSamples).catch(() => {});
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  async function start(key: string, body: any) {
    setBusy(key); setErr("");
    try {
      const r = await api("/api/cases/sample", { method: "POST", json: { ...body, lang } });
      router.push(`/cases/${r.id}`);
    } catch (e: any) { setErr(e.message); setBusy(""); }
  }
  async function upload() {
    setBusy("upload"); setErr("");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("amount", amount); fd.append("term", term); fd.append("lang", lang);
      const r = await api("/api/cases", { method: "POST", body: fd });
      router.push(`/cases/${r.id}`);
    } catch (e: any) { setErr(e.message); setBusy(""); }
  }

  return (
    <Shell>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-6 min-w-0">
          <div>
            <h1 className="serif text-[30px] leading-9">{t("q.title")}</h1>
          </div>
          <Card pad={false}>
            <div className="overflow-x-auto scroll-thin">
              <table className="dense w-full text-[13px]">
                <thead><tr>
                  <th>{t("col.id")}</th><th>{t("col.applicant")}</th><th className="text-right">{t("col.amount")}</th>
                  <th>{t("col.status")}</th><th>{t("col.rec")}</th><th>{t("col.band")}</th><th>{t("col.created")}</th>
                </tr></thead>
                <tbody>
                  {cases === null && [0, 1, 2].map((i) => <tr key={i}><td colSpan={7}><Skeleton h={18} /></td></tr>)}
                  {cases?.length === 0 && <tr><td colSpan={7} className="py-10 text-center text-muted">{t("q.empty")}</td></tr>}
                  {cases?.map((c) => (
                    <tr key={c.id} className="cursor-pointer" onClick={() => router.push(`/cases/${c.id}`)}>
                      <td className="font-mono text-[12px]"><Link href={`/cases/${c.id}`} className="text-accent hover:underline">{c.id}</Link></td>
                      <td className="max-w-[260px] truncate">{c.applicant || <span className="text-muted">—</span>}{c.sample && <span className="ml-2 text-[11px] text-muted">{c.sample}</span>}</td>
                      <td className="tnum text-right">{mln(c.amount, lang)} <span className="text-muted">/ {c.term}{t("common.months")}</span></td>
                      <td><Chip tone={c.status === "DECIDED" ? "accent" : c.status === "FAILED" ? "bad" : c.status === "ANALYZED" ? "info" : "neutral"}>{t(`st.${c.status}`)}</Chip></td>
                      <td>{c.recommendation ? <Chip tone={recTone(c.recommendation)}>{t(`rec.${c.recommendation}`)}</Chip> : <span className="text-muted">—</span>}</td>
                      <td>{c.band ? <Chip tone={bandTone(c.band)}>{c.band}</Chip> : <span className="text-muted">—</span>}</td>
                      <td className="text-muted tnum whitespace-nowrap">{dt(c.created)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div>
            <H sub={t("q.samples.sub")}>{t("q.samples")}</H>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {samples.map((s) => (
                <button key={s.key} disabled={!!busy} onClick={() => start(s.key, { archetype: s.key })}
                  className="group rounded-xl border border-line bg-surface p-4 text-left transition hover:border-accent hover:shadow-sm disabled:opacity-50">
                  <div className="text-[14px] font-medium text-ink group-hover:text-accent">{s.title[lang]}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Chip>{DOCLANG[s.lang]}</Chip>
                    <Chip tone={s.degrade ? "warn" : "neutral"}>{ROUTE[String(s.degrade)]}</Chip>
                  </div>
                  <div className="mt-3 text-[12px] text-muted">{busy === s.key ? t("common.loading") : `${t("common.open")} →`}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-4">
          <Card>
            <H sub={t("q.upload.sub")}>{t("q.upload")}</H>
            <div role="button" tabIndex={0} onClick={() => fileRef.current?.click()} onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); setFiles([...files, ...Array.from(e.dataTransfer.files)].slice(0, 6)); }}
              className="cursor-pointer rounded-lg border border-dashed border-line-2 bg-surface-2 px-4 py-8 text-center text-[13px] text-muted hover:border-accent">
              {files.length ? <ul className="space-y-0.5 text-ink">{files.map((f) => <li key={f.name} className="truncate">{f.name}</li>)}</ul> : t("q.drop")}
            </div>
            <input ref={fileRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg" className="hidden"
              onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 6))} />
            <div className="mt-3 grid grid-cols-2 gap-3">
              <label className="text-[12px] text-muted">{t("q.amount")}
                <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="tnum mt-1 w-full rounded-lg border border-line-2 bg-surface px-3 py-2 text-[13px] text-ink" /></label>
              <label className="text-[12px] text-muted">{t("q.term")}
                <input value={term} onChange={(e) => setTerm(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="tnum mt-1 w-full rounded-lg border border-line-2 bg-surface px-3 py-2 text-[13px] text-ink" /></label>
            </div>
            <Button className="mt-4 w-full" disabled={!files.length || !!busy || !amount || !term} onClick={upload}>{busy === "upload" ? t("common.loading") : t("q.start")}</Button>
            {err && <p className="mt-2 text-[12.5px] text-bad" role="alert">{err}</p>}
          </Card>
          <Card>
            <div className="text-[13px] font-medium">{t("q.random")}</div>
            <p className="mt-1 text-[12px] text-muted">Generates a fresh synthetic applicant (new seed, random layout and language).</p>
            <div className="mt-3 flex gap-2">
              <Button variant="soft" disabled={!!busy} onClick={() => start("r1", {})}>Clean PDFs</Button>
              <Button variant="soft" disabled={!!busy} onClick={() => start("r2", { degrade: "scan" })}>Scanned</Button>
            </div>
          </Card>
        </aside>
      </div>
    </Shell>
  );
}
