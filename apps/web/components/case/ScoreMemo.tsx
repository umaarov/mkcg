"use client";
import { useEffect, useMemo, useState } from "react";
import { useApp } from "../Providers";
import { Button, Card, Chip, H, Stat, bandTone, recTone } from "../ui";
import { Gauge } from "../charts";
import { api } from "@/lib/api";
import { mln, nf0, pct, x2 } from "@/lib/format";

const FEAT_FMT: Record<string, (v: number) => string> = {
  dscr: x2, loan_to_annual_inflow: x2, inflow_cv: (v) => pct(v, 0), trend_ratio: x2, top1_share: (v) => pct(v, 0), hhi: x2, gap_dev: x2,
  roundtrip_share: (v) => pct(v, 0), cashout_ratio: (v) => pct(v, 0), owner_transfer_ratio: (v) => pct(v, 0), non_operating_in_share: (v) => pct(v, 0),
  low_balance_days_share: (v) => pct(v, 0), op_margin: (v) => pct(v, 0), existing_ds_ratio: (v) => pct(v, 0), cash_deposit_share: (v) => pct(v, 0),
  active_months: (v) => v.toFixed(0), business_age_months: (v) => v.toFixed(0), log_avg_inflow: (v) => nf0(Math.exp(v)),
};

export function ScoreTab({ c }: { c: any }) {
  const { t, lang } = useApp();
  const sc = c.result.score;
  const [card, setCard] = useState<any>(null);
  const [amount, setAmount] = useState(c.amount);
  const [term, setTerm] = useState(c.term);
  const [wi, setWi] = useState<any>(null);
  useEffect(() => { api("/api/system/status").then((s) => setCard(s.model_card)).catch(() => {}); }, []);
  useEffect(() => {
    const h = setTimeout(() => api(`/api/cases/${c.id}/whatif`, { method: "POST", json: { amount, term } }).then(setWi).catch(() => {}), 250);
    return () => clearTimeout(h);
  }, [amount, term, c.id]);
  if (!sc?.available) return <Card><p className="text-muted">Scoring model is not available.</p></Card>;
  const maxC = Math.max(...sc.reasons.map((r: any) => Math.abs(r.contribution)), 0.01);
  const rl = (lang === "en" ? "en" : lang) as "en" | "uz" | "ru";
  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
      <div className="space-y-5">
        <Card>
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted">{t("score.pd")}</div>
              <div className="serif tnum text-[44px] leading-[48px]">{pct(sc.pd, 1)}</div>
            </div>
            <Chip tone={bandTone(sc.band)}>Band {sc.band}</Chip>
          </div>
          <div className="mt-3"><Gauge value={sc.pd} bands={card?.band_cutoffs || [0.046, 0.142, 0.323, 0.611]} label={pct(sc.pd, 1)} /></div>
          <p className="mt-5 text-[12px] text-muted">{t("score.caveat")}</p>
        </Card>
        <Card>
          <H>{t("score.reasons")}</H>
          <ul className="space-y-3">
            {sc.reasons.map((r: any) => {
              const up = r.direction === "raises_risk";
              const txt = typeof r.text === "string" ? r.text : (r.text[lang] ?? r.text.en);
              return (
                <li key={r.feature}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[13.5px]">{txt}</span>
                    <span className="tnum whitespace-nowrap text-[12px] text-muted">{(FEAT_FMT[r.feature] || ((v: number) => v.toFixed(2)))(r.value)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-surface-2"><div className="h-1.5 rounded-full" style={{ width: `${(Math.abs(r.contribution) / maxC) * 100}%`, background: up ? "var(--bad)" : "var(--good)" }} /></div>
                    <span className={`text-[11px] ${up ? "text-bad" : "text-good"}`}>{up ? t("score.up") : t("score.down")}</span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-[11.5px] text-muted">SHAP attributions from a monotone-constrained gradient-boosting model.</p>
        </Card>
      </div>
      <div className="space-y-5">
        <Card>
          <H>{t("score.whatif")}</H>
          <div className="space-y-4">
            <label className="block text-[12px] text-muted">{t("q.amount")}: <b className="tnum text-ink">{nf0(amount)}</b>
              <input type="range" min={5_000_000} max={300_000_000} step={5_000_000} value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" /></label>
            <label className="block text-[12px] text-muted">{t("q.term")}: <b className="tnum text-ink">{term}</b>
              <input type="range" min={6} max={48} step={6} value={term} onChange={(e) => setTerm(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" /></label>
          </div>
          {wi && (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <Stat label={t("m.inst")} value={mln(wi.afford.installment, lang)} />
              <Stat label={t("m.dscr")} value={x2(wi.afford.dscr)} tone={wi.afford.dscr < 1.1 ? "bad" : wi.afford.dscr < 1.3 ? "warn" : "good"} />
              <Stat label={t("score.pd")} value={pct(wi.score.pd, 1)} sub={`Band ${wi.score.band}`} />
              <div className="rounded-lg border border-line px-4 py-3"><div className="text-[11px] uppercase tracking-wide text-muted">{t("col.rec")}</div>
                <div className="mt-1"><Chip tone={recTone(wi.recommendation)}>{t(`rec.${wi.recommendation}`)}</Chip></div>
                {wi.failing.length > 0 && <div className="mt-1 text-[11px] text-muted">fails {wi.failing.join(", ")}</div>}</div>
            </div>
          )}
          <p className="mt-3 text-[12px] text-muted">{t("m.maxprin")}: <b className="tnum text-ink">{mln(c.result.afford.max_principal, lang)}</b> ({c.term} {t("common.months")})</p>
        </Card>
        {card && (
          <Card>
            <H>Model card</H>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
              <dt className="text-muted">Training set</dt><dd className="tnum">{nf0(card.data.n_sme)} synthetic SMEs · {nf0(card.data.n_transactions)} tx</dd>
              <dt className="text-muted">AUC (held-out)</dt><dd className="tnum">{card.metrics.auc_lightgbm.toFixed(3)}</dd>
              <dt className="text-muted">Logistic baseline</dt><dd className="tnum">{card.metrics.auc_logistic_baseline.toFixed(3)}</dd>
              <dt className="text-muted">DSCR-only baseline</dt><dd className="tnum">{card.metrics.auc_dscr_only_baseline.toFixed(3)}</dd>
              <dt className="text-muted">KS</dt><dd className="tnum">{card.metrics.ks_lightgbm.toFixed(3)}</dd>
            </dl>
            <p className="mt-3 text-[11.5px] text-muted">{card.caveat}</p>
          </Card>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------
export function MemoTab({ c, reload }: { c: any; reload: () => void }) {
  const { t, lang } = useApp();
  const [ml, setMl] = useState<"en" | "uz" | "ru">(lang);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [router, setRouter] = useState<any>(null);
  const memo = c.result.memo?.[ml];
  const facts: any[] = c.result.facts;
  const byId = useMemo(() => Object.fromEntries(facts.map((f) => [f.id, f])), [facts]);
  useEffect(() => { api("/api/system/status").then((s) => setRouter(s.router)).catch(() => {}); }, []);
  useEffect(() => { if (!memo) gen(false); /* eslint-disable-next-line */ }, [ml]);
  async function gen(llm: boolean) {
    setBusy(true);
    try { await api(`/api/cases/${c.id}/memo`, { method: "POST", json: { lang: ml, use_llm: llm } }); reload(); } finally { setBusy(false); }
  }
  const canLlm = router && (router.external_available || router.local_available);
  const render = (txt: string) => txt.split(/(\[F\d+\])/g).map((p, i) => {
    const m = p.match(/^\[(F\d+)\]$/);
    return m ? <button key={i} className={`cite ${sel === m[1] ? "on" : ""}`} onClick={() => setSel(m[1])}>{m[1]}</button> : <span key={i}>{p}</span>;
  });
  return (
    <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-muted">{t("memo.lang")}</span>
            {(["en", "uz", "ru"] as const).map((l) => <button key={l} onClick={() => setMl(l)} className={`rounded px-2 py-1 text-[11px] font-medium ${ml === l ? "bg-ink text-bg" : "border border-line text-muted"}`}>{l.toUpperCase()}</button>)}
          </div>
          <div className="flex items-center gap-2">
            {memo && <Chip tone={memo.writer === "llm" ? "accent" : "neutral"}>{memo.writer === "llm" ? t("memo.writer.llm") : t("memo.writer.template")}</Chip>}
            {memo?.verifier && <Chip tone={(memo.verifier.ok ?? true) ? "good" : "bad"} title={JSON.stringify(memo.verifier.violations || [])}>{t("memo.verifier")}: {(memo.verifier.ok ?? true) ? "0 violations" : `${memo.verifier.violations.length} violations`}</Chip>}
            <Button variant="soft" disabled={busy || !canLlm} title={canLlm ? "" : "No model configured: running offline with the deterministic writer"} onClick={() => gen(true)}>{busy ? t("common.loading") : t("memo.rewrite")}</Button>
          </div>
        </div>
        {!memo ? <p className="text-muted">{t("common.loading")}</p> : (
          <article className="max-w-[72ch] space-y-5 serif text-[16.5px] leading-[1.7]">
            {memo.sections.map((s: any, i: number) => (
              <section key={i}>{s.title && <h3 className="mb-1 font-sans text-[11px] font-semibold uppercase tracking-wider text-muted">{s.title}</h3>}
                {s.text.split("\n").map((ln: string, j: number) => <p key={j} className={ln.startsWith("•") ? "pl-3 text-[15px]" : ""}>{render(ln)}</p>)}</section>
            ))}
          </article>
        )}
        {memo?.note && <p className="mt-4 text-[12px] text-muted">{memo.note}</p>}
        <p className="mt-4 text-[12px] text-muted">{t("memo.hint")}</p>
      </Card>
      <Card pad={false}>
        <div className="border-b border-line px-5 py-3 text-[13px] font-medium">{t("memo.facts")}</div>
        <div className="max-h-[640px] overflow-auto scroll-thin">
          <table className="dense w-full text-[12.5px]">
            <tbody>
              {facts.map((f) => (
                <tr key={f.id} id={f.id} onClick={() => setSel(f.id)} className="cursor-pointer" style={sel === f.id ? { background: "var(--accent-soft)" } : undefined}>
                  <td className="w-10 font-mono text-[11px] text-muted">{f.id}</td>
                  <td>{f.label[ml]}</td>
                  <td className="tnum text-right whitespace-nowrap">{f.display}<span className="text-muted"> {f.unit === "UZS" ? "" : f.unit === "%" ? "" : f.unit}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
