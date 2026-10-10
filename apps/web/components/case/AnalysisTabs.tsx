"use client";
import { useMemo } from "react";
import { useApp } from "../Providers";
import { Card, Chip, H, Stat, outcomeTone } from "../ui";
import { FlowChart, HBars } from "../charts";
import { catLabel, mln, nf0, pct, x2 } from "@/lib/format";

function stmtTx(c: any): any[] {
  return c.docs.find((d: any) => d.doc_type === "statement")?.extraction?.transactions || [];
}

export function CashTab({ c }: { c: any }) {
  const { t, lang } = useApp();
  const r = c.result, m = r.metrics, a = r.afford;
  const txs = stmtTx(c);
  const cust = useMemo(() => {
    const map = new Map<string, number>();
    txs.filter((x) => (x.verified_category || x.category) === "sales_receipt" && x.cp_tin).forEach((x) => map.set(x.cp_name || x.cp_tin, (map.get(x.cp_name || x.cp_tin) || 0) + x.credit));
    const tot = [...map.values()].reduce((s, v) => s + v, 0) || 1;
    return [...map.entries()].sort((p, q) => q[1] - p[1]).slice(0, 8).map(([label, v]) => ({ label, value: v / tot }));
  }, [txs]);
  const cats = useMemo(() => {
    const map = new Map<string, number>();
    txs.forEach((x) => { const k = x.verified_category || x.category; map.set(k, (map.get(k) || 0) + (x.debit || 0)); });
    return [...map.entries()].filter(([, v]) => v > 0).sort((p, q) => q[1] - p[1]).slice(0, 8).map(([k, v]) => ({ label: catLabel(k, lang), value: v }));
  }, [txs, lang]);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={t("m.inflow")} value={mln(m.op_inflow_avg, lang)} sub={`${m.active_months}/${m.n_months} active months`} />
        <Stat label={t("m.net")} value={mln(m.net_cf_avg, lang)} sub={`margin ${pct(m.op_margin, 0)}`} tone={m.net_cf_avg <= 0 ? "bad" : undefined} />
        <Stat label={t("m.dscr")} value={x2(a.dscr)} sub={`${t("m.inst")} ${mln(a.installment, lang)}`} tone={a.dscr < 1.1 ? "bad" : a.dscr < 1.3 ? "warn" : "good"} />
        <Stat label={t("m.maxprin")} value={mln(a.max_principal, lang)} sub={`${t("m.maxinst")} ${mln(a.max_installment, lang)}`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <H>{t("chart.flow")}</H>
          <FlowChart months={m.months} inflow={m.monthly_inflow} outflow={m.monthly_op_outflow} lang={lang} />
          <div className="mt-2 flex gap-4 text-[11.5px] text-muted"><span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-accent" />inflow</span><span><i className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: "var(--line-2)" }} />operating outflow</span></div>
        </Card>
        <Card>
          <H>{t("chart.cust")}</H>
          <HBars rows={cust} fmt={(v) => pct(v, 0)} />
        </Card>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <Card>
          <H>{t("chart.cat")}</H>
          <HBars rows={cats} fmt={(v) => mln(v, lang)} tone="var(--ink-2)" />
        </Card>
        <div className="grid grid-cols-2 gap-3 content-start">
          <Stat label={t("m.cv")} value={pct(m.inflow_cv, 0)} tone={m.inflow_cv > 0.7 ? "bad" : m.inflow_cv > 0.35 ? "warn" : undefined} />
          <Stat label={t("m.top1")} value={pct(m.top1_share, 0)} sub={`top-3 ${pct(m.top3_share, 0)}`} tone={m.top1_share > 0.7 ? "bad" : m.top1_share > 0.45 ? "warn" : undefined} />
          <Stat label={t("m.cashout")} value={pct(m.cashout_ratio, 0)} />
          <Stat label={t("m.rt")} value={pct(m.roundtrip_share, 0)} tone={m.roundtrip_share > 0.15 ? "bad" : m.roundtrip_share > 0.05 ? "warn" : undefined} />
          <Stat label={t("m.debt")} value={mln(m.existing_debt_service, lang)} />
          <Stat label={t("m.lowbal")} value={pct(m.low_balance_days_share, 0)} />
        </div>
      </div>
    </div>
  );
}

export function RevenueTab({ c }: { c: any }) {
  const { t, lang } = useApp();
  const rec = c.result.recon;
  const circ = new Set<number>(c.result.metrics.roundtrip_tx || []);
  const tx = stmtTx(c).filter((x) => circ.has(x.idx));
  if (!rec) return <Card><p className="text-muted">No tax declaration was found, so declared revenue cannot be reconciled with the account. The rules engine treats this as a referral.</p></Card>;
  const max = Math.max(rec.declared_total, rec.bank_inflow, 1);
  const tone = rec.verdict === "consistent" ? "good" : rec.severity === "high" ? "bad" : "warn";
  const bars = [
    { label: t("rev.declared"), v: rec.declared_total, color: "var(--info)" },
    { label: t("rev.bank"), v: rec.bank_inflow, color: "var(--accent)" },
    { label: t("rev.adj"), v: rec.bank_inflow_adj, color: "var(--ink-2)" },
  ];
  return (
    <div className="space-y-5">
      <div className={`rounded-xl border p-4 ${tone === "good" ? "border-good/30 bg-good-soft" : tone === "bad" ? "border-bad/30 bg-bad-soft" : "border-warn/30 bg-warn-soft"}`}>
        <div className="serif text-[20px]">{t(`rev.${rec.verdict}`)}</div>
        <div className="mt-0.5 text-[13px] text-ink-2">{t("rev.ratio")}: <b className="tnum">{x2(rec.gap_adj)}</b> · {t("rev.basis")}: <b className="tnum">{mln(rec.underwriting_revenue_basis, lang)}</b></div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <div className="space-y-4">
            {bars.map((b) => (
              <div key={b.label}>
                <div className="mb-1 flex justify-between text-[12.5px]"><span className="text-ink-2">{b.label}</span><span className="tnum">{nf0(b.v)}</span></div>
                <div className="h-3 rounded bg-surface-2"><div className="h-3 rounded" style={{ width: `${(b.v / max) * 100}%`, background: b.color }} /></div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <table className="dense w-full text-[13px]">
            <thead><tr><th>Quarter</th><th className="text-right">Declared</th><th className="text-right">Account</th><th className="text-right">Ratio</th></tr></thead>
            <tbody>
              {Object.entries(rec.quarters).map(([k, q]: any) => (
                <tr key={k}><td>{k.toUpperCase()}</td><td className="tnum text-right">{nf0(q.declared)}</td><td className="tnum text-right">{nf0(q.bank)}</td><td className="tnum text-right">{q.ratio ? x2(q.ratio) : "—"}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[12px] text-muted">Bank figure = customer receipts + cash deposits. Owner loans, other lenders and refunded transfers are excluded.</p>
        </Card>
      </div>
      {tx.length > 0 && (
        <Card pad={false}>
          <div className="border-b border-line px-5 py-3 text-[13px] font-medium">{t("rev.circ")} <Chip tone="bad">{tx.length}</Chip> <span className="ml-2 text-muted tnum">{mln(rec.roundtrip_amount, lang)}</span></div>
          <div className="max-h-[320px] overflow-auto scroll-thin">
            <table className="dense w-full text-[12.5px]">
              <thead><tr><th>Date</th><th>Counterparty</th><th className="text-right">Received</th></tr></thead>
              <tbody>{tx.map((x) => <tr key={x.idx}><td className="tnum">{x.date}</td><td>{x.cp_name}</td><td className="tnum text-right">{nf0(x.credit)}</td></tr>)}</tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

export function RulesTab({ c }: { c: any }) {
  const { t, lang } = useApp();
  const rules = c.result.rules;
  const fmt = (r: any, v: any) => {
    if (v == null) return "—";
    if (typeof v === "boolean") return v ? "yes" : "no";
    if (["top1_share", "roundtrip_share", "inflow_cv", "low_balance_days_share", "cashout_ratio", "non_operating_in_share", "identity_gap_share", "fields_verified_share", "extraction_quality_issues"].includes(r.metric)) return pct(v, 1);
    if (r.metric === "request_amount") return nf0(v);
    return Number(v).toFixed(2).replace(/\.00$/, "");
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="good">{rules.counts.pass_} pass</Chip><Chip tone="warn">{rules.counts.refer} review</Chip><Chip tone="bad">{rules.counts.fail} fail</Chip>
        <span className="text-[12px] text-muted">policy {rules.policy_version}</span>
      </div>
      <Card pad={false}>
        <div className="overflow-x-auto scroll-thin">
          <table className="dense w-full text-[13px]">
            <thead><tr><th>#</th><th>{t("rules.rule")}</th><th></th><th className="text-right">{t("rules.evidence")}</th><th className="text-right">{t("rules.limits")}</th></tr></thead>
            <tbody>
              {rules.results.map((r: any) => (
                <tr key={r.id}>
                  <td className="font-mono text-[11.5px] text-muted">{r.id}</td>
                  <td>{r.label[lang]}<div className="text-[11px] text-muted">{r.hard ? t("rules.hard") : t("rules.soft")}</div></td>
                  <td><Chip tone={outcomeTone(r.outcome)}>{r.outcome}</Chip></td>
                  <td className="tnum text-right">{fmt(r, r.value)}</td>
                  <td className="tnum text-right text-muted">{r.kind === "range" ? `${nf0(r.lo)}–${nf0(r.hi)}` : r.kind === "bool" ? "must hold" : `${fmt(r, r.refer)} / ${fmt(r, r.fail)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="text-[12px] text-muted">{t("rules.note")}</p>
    </div>
  );
}
