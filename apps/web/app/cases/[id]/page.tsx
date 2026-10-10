"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { useApp } from "@/components/Providers";
import { Chip, Skeleton, Tabs, bandTone, recTone } from "@/components/ui";
import { DocsTab } from "@/components/case/DocsTab";
import { CashTab, RevenueTab, RulesTab } from "@/components/case/AnalysisTabs";
import { MemoTab, ScoreTab } from "@/components/case/ScoreMemo";
import { AuditTab, DecisionTab } from "@/components/case/DecisionAudit";
import { api } from "@/lib/api";
import { mln, nf0, pct } from "@/lib/format";

type Tab = "docs" | "cash" | "revenue" | "rules" | "score" | "memo" | "decision" | "audit";

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const { t, lang } = useApp();
  const router = useRouter();
  const [c, setC] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("docs");
  const [err, setErr] = useState("");

  const load = useCallback(() => api(`/api/cases/${id}`).then(setC).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!c || !["UPLOADED", "EXTRACTING", "ANALYZING"].includes(c.status)) return;
    const h = setInterval(load, 1200);
    return () => clearInterval(h);
  }, [c, load]);

  if (err) return <Shell><p className="text-bad">{err}</p><Link href="/" className="text-accent">← {t("common.back")}</Link></Shell>;
  if (!c) return <Shell><Skeleton h={28} w={280} /><div className="mt-6"><Skeleton h={300} /></div></Shell>;
  const r = c.result || {};
  const ready = r.rules && r.metrics;
  const working = ["UPLOADED", "EXTRACTING", "ANALYZING"].includes(c.status);

  const tabs: { id: Tab; label: string; badge?: React.ReactNode }[] = [
    { id: "docs", label: t("tab.docs"), badge: ready && !r.verified ? <span className="h-1.5 w-1.5 rounded-full bg-warn" /> : undefined },
    ...(ready ? [
      { id: "cash" as Tab, label: t("tab.cash") },
      { id: "revenue" as Tab, label: t("tab.revenue"), badge: r.recon && r.recon.verdict !== "consistent" ? <span className="h-1.5 w-1.5 rounded-full bg-bad" /> : undefined },
      { id: "rules" as Tab, label: t("tab.rules"), badge: <span className="tnum text-[10.5px] text-muted">{r.rules.counts.refer + r.rules.counts.fail || ""}</span> },
      { id: "score" as Tab, label: t("tab.score") },
      { id: "memo" as Tab, label: t("tab.memo") },
      { id: "decision" as Tab, label: t("tab.decision") },
      { id: "audit" as Tab, label: t("tab.audit") },
    ] : []),
  ];

  return (
    <Shell wide>
      <div className="mb-5">
        <Link href="/" className="text-[12px] text-muted hover:text-ink">← {t("nav.queue")}</Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="serif text-[28px] leading-8">{c.applicant || c.id}</h1>
              <Chip tone={c.status === "DECIDED" ? "accent" : c.status === "FAILED" ? "bad" : "info"}>{t(`st.${c.status}`)}</Chip>
            </div>
            <div className="mt-1 text-[12.5px] text-muted tnum">
              {c.id} · {c.tin && <>STIR {c.tin} · </>}{t("case.req")}: <b className="text-ink">{nf0(c.amount)} {t("common.uzs")}</b> / {c.term} {t("common.months")}
            </div>
          </div>
          {ready && (
            <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
              <div><div className="text-[10.5px] uppercase tracking-wide text-muted">{t("col.rec")}</div><div className="mt-0.5"><Chip tone={recTone(r.rules.recommendation)}>{t(`rec.${r.rules.recommendation}`)}</Chip></div></div>
              {r.score?.available && <div className="border-l border-line pl-3"><div className="text-[10.5px] uppercase tracking-wide text-muted">PD</div><div className="serif tnum text-[20px] leading-6">{pct(r.score.pd, 1)} <Chip tone={bandTone(r.score.band)}>{r.score.band}</Chip></div></div>}
              <div className="border-l border-line pl-3"><div className="text-[10.5px] uppercase tracking-wide text-muted">DSCR</div><div className="serif tnum text-[20px] leading-6">{r.afford.dscr.toFixed(2)}</div></div>
            </div>
          )}
        </div>
        {c.steps?.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted" aria-label={t("case.pipeline")}>
            {c.steps.map((s: any, i: number) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-md bg-surface-2 px-2 py-1"><span className="text-good">✓</span>{s.name}<span className="tnum opacity-70">{s.seconds}s</span></span>
            ))}
            {working && <span className="inline-flex items-center gap-2 rounded-md bg-accent-soft px-2 py-1 text-accent"><span className="h-2 w-2 animate-pulse rounded-full bg-accent" />{t(`st.${c.status}`)}</span>}
          </div>
        )}
        {working && !c.steps?.length && <div className="mt-4 inline-flex items-center gap-2 rounded-md bg-accent-soft px-2.5 py-1.5 text-[12px] text-accent"><span className="h-2 w-2 animate-pulse rounded-full bg-accent" />{t(`st.${c.status}`)}</div>}
        {c.status === "FAILED" && <p className="mt-3 rounded-lg bg-bad-soft px-3 py-2 text-[13px] text-bad">{r.error}</p>}
        {c.docs.some((d: any) => d.source === "ocr" && (d.ocr_conf < 80 || (d.extraction?.validations || []).some((v: any) => !v.ok))) && (
          <p className="mt-3 rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-warn" role="status">
            Low-quality scan or photo detected (OCR confidence {Math.min(...c.docs.filter((d: any) => d.source === "ocr").map((d: any) => d.ocr_conf)).toFixed(0)}%, failed checks). Figures may be incomplete — retake the photo flat and well lit, or upload the digital PDF. Review every highlighted field before relying on the analysis.
          </p>
        )}
        {r.missing_documents?.length > 0 && <p className="mt-3 rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-warn">Missing documents: {r.missing_documents.join(", ")} — the system will refer this case.</p>}
      </div>
      {c.docs.length > 0 && (
        <>
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
          <div className="mt-5 rise" key={tab}>
            {tab === "docs" && c.docs.some((d: any) => d.extraction?.fields) && <DocsTab c={c} reload={load} />}
            {ready && tab === "cash" && <CashTab c={c} />}
            {ready && tab === "revenue" && <RevenueTab c={c} />}
            {ready && tab === "rules" && <RulesTab c={c} />}
            {ready && tab === "score" && <ScoreTab c={c} />}
            {ready && tab === "memo" && <MemoTab c={c} reload={load} />}
            {ready && tab === "decision" && <DecisionTab c={c} reload={load} />}
            {ready && tab === "audit" && <AuditTab c={c} />}
          </div>
        </>
      )}
    </Shell>
  );
}
