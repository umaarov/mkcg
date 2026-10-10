"use client";
import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { useApp } from "@/components/Providers";
import { Card, Chip, H, Skeleton, Stat } from "@/components/ui";
import { Spark } from "@/components/charts";
import { api } from "@/lib/api";
import { mln, pct } from "@/lib/format";

export default function Portfolio() {
  const { t, lang } = useApp();
  const [p, setP] = useState<any>(null);
  useEffect(() => { api("/api/portfolio").then(setP).catch(() => setP(false)); }, []);
  return (
    <Shell>
      <h1 className="serif text-[30px] leading-9">{t("pf.title")}</h1>
      <p className="mt-1 max-w-[72ch] text-[13px] text-muted">{t("pf.sub")}</p>
      {p === null && <div className="mt-6"><Skeleton h={120} /></div>}
      {p === false && <p className="mt-6 text-muted">Signals have not been built on this server.</p>}
      {p && (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Defaults flagged before they happened" value={pct(p.test.recall, 0)} sub={`${p.test.caught_before_default} of ${p.test.defaults} (held-out half)`} tone="good" />
            <Stat label="Median warning time" value={`${p.test.median_lead_months.toFixed(0)} months`} sub="missed-payment trigger: 0" />
            <Stat label="False alerts on loans that survived" value={pct(p.test.false_alert_rate_on_survivors, 1)} />
            <Stat label="Alert precision" value={pct(p.test.precision, 0)} sub={`threshold ${p.threshold}/100`} />
          </div>
          <Card pad={false}>
            <div className="border-b border-line px-5 py-3"><H sub="Highest early-warning scores among live loans at month 8 after origination. The dashed line is each borrower’s own pre-loan inflow baseline.">Watchlist</H></div>
            <div className="overflow-x-auto scroll-thin">
              <table className="dense w-full text-[13px]">
                <thead><tr><th>Loan</th><th>Borrower</th><th className="text-right">Amount</th><th>Score</th><th>Monthly inflow</th><th>Account balance</th><th>Outcome in synthetic book</th></tr></thead>
                <tbody>
                  {p.watchlist.map((w: any) => (
                    <tr key={w.id}>
                      <td className="font-mono text-[11.5px] text-muted">{w.id}</td>
                      <td>{w.name} <span className="text-muted">{w.form}</span><div className="text-[11px] text-muted">{w.sector}</div></td>
                      <td className="tnum text-right">{mln(w.amount, lang)}</td>
                      <td><Chip tone={w.score >= p.threshold ? "bad" : "warn"}>{w.score}</Chip></td>
                      <td><Spark values={w.inflow} baseline={w.base_inflow} color="var(--accent)" /></td>
                      <td><Spark values={w.balance} baseline={0} color={w.balance[w.balance.length - 1] < 0 ? "var(--bad)" : "var(--ink-2)"} /></td>
                      <td>{w.eventually_defaulted ? <Chip tone="bad">defaulted later</Chip> : <Chip tone="good">survived</Chip>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <H>How to read this</H>
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-ink-2">
              <li>Signals compares each loan’s inflow and balance with the borrower’s own baseline: inflow erosion, cash-buffer drain, volatility, and negative balance.</li>
              <li>The alert threshold ({p.threshold}) was fitted on {p.n_loans / 2} loans and scored on the other {p.n_loans / 2}: recall {pct(p.fit.recall, 0)} on the fit half, {pct(p.test.recall, 0)} on the held-out half.</li>
              <li>{p.caveat}</li>
            </ul>
          </Card>
        </div>
      )}
    </Shell>
  );
}
