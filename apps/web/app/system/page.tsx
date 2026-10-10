"use client";
import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { useApp } from "@/components/Providers";
import { Button, Card, Chip, H, Skeleton, Stat } from "@/components/ui";
import { Calib } from "@/components/charts";
import { api, getUser } from "@/lib/api";
import { nf0, pct } from "@/lib/format";

const P = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);

export default function System() {
  const { t } = useApp();
  const [s, setS] = useState<any>(null);
  const [ev, setEv] = useState<any>(null);
  const [pf, setPf] = useState<any>(null);
  const [pub, setPub] = useState<any>(null);
  const [calls, setCalls] = useState<any[]>([]);
  const user = getUser();
  const load = () => {
    api("/api/system/status").then(setS);
    api("/api/eval").then(setEv).catch(() => setEv(false));
    api("/api/portfolio").then(setPf).catch(() => {});
    api("/api/fgate/pubkey").then(setPub).catch(() => {});
    api("/api/system/router-calls").then(setCalls).catch(() => {});
  };
  useEffect(load, []);
  async function togglePerimeter() {
    await api("/api/system/perimeter", { method: "POST", json: { on: !s.router.perimeter_mode } });
    load();
  }
  if (!s) return <Shell><Skeleton h={30} w={300} /></Shell>;
  const all = ev?.summary?.all;
  const card = s.model_card;
  const groups = ev ? ["deg=clean", "deg=scan", "deg=photo", "lang=uz", "lang=uzc", "lang=ru", "layout=A", "layout=B", "layout=C"] : [];
  return (
    <Shell>
      <h1 className="serif text-[30px] leading-9">{t("sys.title")}</h1>
      <p className="mt-1 max-w-[72ch] text-[13px] text-muted">{t("sys.sub")}</p>

      <Card className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="max-w-[640px]">
            <div className="flex items-center gap-2"><h2 className="serif text-[19px]">{t("sys.perimeter")}</h2><Chip tone={s.router.perimeter_mode ? "good" : "warn"}>{s.router.perimeter_mode ? "ON — nothing leaves this host" : "OFF — prototype may call an external model"}</Chip></div>
            <p className="mt-1 text-[12.5px] text-muted">{t("sys.perimeter.sub")}</p>
            <p className="mt-1 text-[12.5px] text-muted">Extraction and memo models: <b className="text-ink">{s.router.extraction_model}</b> / <b className="text-ink">{s.router.memo_model}</b> · external {s.router.external_available ? "available" : "off"} · local {s.router.local_available ? "available" : "not configured"}. Every parser, metric, rule and score runs without any model.</p>
          </div>
          <Button variant={s.router.perimeter_mode ? "ghost" : "primary"} disabled={user?.role !== "admin"} title={user?.role !== "admin" ? "Sign in as admin1 to toggle" : ""} onClick={togglePerimeter}>
            {s.router.perimeter_mode ? "Turn off" : "Turn on"}
          </Button>
        </div>
      </Card>

      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Mod name="OCRGate" role="Classify · OCR · extract" ok>
          {all ? <>
            <KV k="Document classification" v={P(all.classification_acc)} /><KV k="Statement rows recovered" v={P(all.stmt_row_recall)} />
            <KV k="Header fields exact" v={P(all.stmt_header_field_acc)} /><KV k="Declaration fields exact" v={P(all.decl_field_acc)} />
            <KV k="Median seconds / case" v={all.sec_per_case_p50.toFixed(1)} />
          </> : <Dim>Run eval/run_eval.py</Dim>}
          <KV k="Engine" v={s.ocr.engine} />
        </Mod>
        <Mod name="Statement" role="Cash-flow analytics (no LLM)" ok>
          {all ? <><KV k="Payment-purpose category accuracy" v={P(all.stmt_category_acc)} /><KV k="Median error, avg inflow" v={P(all.median_rel_err_op_inflow, 2)} /><KV k="Median error, net cash flow" v={P(all.median_rel_err_net_cf, 2)} /></> : null}
        </Mod>
        <Mod name="RevenueGate" role="Declared vs account" ok>
          {all && <KV k="Verdict unchanged by parsing errors" v={P(all.recon_verdict_agreement)} />}
          <Dim>Excludes owner loans and money refunded within 7 days.</Dim>
        </Mod>
        <Mod name="RulesEngine" role="Policy as data" ok>
          <KV k="Rules" v="20 (YAML)" /><KV k="Outcome" v="PASS / REFER / FAIL + evidence" /><Dim>Thresholds are team assumptions, not MKBANK policy.</Dim>
        </Mod>
        <Mod name="Scoring" role="Monotone gradient boosting + SHAP" ok={!!card}>
          {card && <>
            <KV k="AUC (held-out)" v={card.metrics.auc_lightgbm.toFixed(3)} /><KV k="vs logistic / DSCR-only" v={`${card.metrics.auc_logistic_baseline.toFixed(3)} / ${card.metrics.auc_dscr_only_baseline.toFixed(3)}`} />
            <KV k="Trained on" v={`${nf0(card.data.n_sme)} SMEs · ${nf0(card.data.n_transactions)} tx (synthetic)`} />
            <div className="mt-2 flex justify-center"><Calib points={card.calibration} /></div>
          </>}
        </Mod>
        <Mod name="FormalBrief" role="Grounded credit memo" ok>
          <Dim>Every number must be a fact-sheet value and every numeric sentence needs a [F##] citation. Failing drafts are rejected; a deterministic template is the fallback.</Dim>
        </Mod>
        <Mod name="PIIModule" role="Reversible masking before any model call" ok>
          {all ? <><KV k="Identifier recall (tested)" v={P(all.pii_recall, 2)} /><KV k="Items tested" v={nf0(all.pii_items)} /></> : null}
          <Dim>IDs, accounts, phones, PINFL, owner names. Mapping never leaves the host.</Dim>
        </Mod>
        <Mod name="Router" role="One door for every model call" ok>
          <KV k="Calls this session" v={String(s.router_summary.calls)} /><KV k="Spend (price table assumption)" v={`$${s.router_summary.cost_usd.toFixed(4)}`} />
          <KV k="Latency p50 / p95" v={`${s.router_summary.p50_s ?? "—"} / ${s.router_summary.p95_s ?? "—"} s`} />
          <KV k="Unmasked text" v="refused" />
        </Mod>
        <Mod name="FGate" role="Hash-chained audit · Ed25519 dossier" ok={s.chain.ok}>
          <KV k="Chain" v={s.chain.ok ? `✓ ${s.chain.events} events intact` : `✕ broken at #${s.chain.first_bad_event}`} /><KV k="Signing key" v={s.fgate.fingerprint} />
          <Dim>Production: key in an HSM; E-IMZO as the signature integration path.</Dim>
        </Mod>
        <Mod name="Signals" role="Portfolio early warning" ok={!!pf}>
          {pf && <><KV k="Defaults flagged early" v={`${P(pf.test.recall, 0)} (held-out)`} /><KV k="Median lead" v={`${pf.test.median_lead_months.toFixed(0)} months`} /><KV k="False alerts" v={P(pf.test.false_alert_rate_on_survivors, 1)} /></>}
        </Mod>
      </div>

      {ev && (
        <Card className="mt-8" pad={false}>
          <div className="border-b border-line px-5 py-4"><H sub={`${ev.n_cases} synthetic applicants × 3 documents, ${ev.mode}. ${ev.note}`}>Measured quality on our test set</H></div>
          <div className="overflow-x-auto scroll-thin">
            <table className="dense w-full text-[12.5px]">
              <thead><tr><th>Slice</th><th className="text-right">Cases</th><th className="text-right">Doc type</th><th className="text-right">Rows recovered</th><th className="text-right">Row precision</th><th className="text-right">Category</th><th className="text-right">Header</th><th className="text-right">Declaration</th><th className="text-right">Registration</th><th className="text-right">Verdict kept</th><th className="text-right">PII</th><th className="text-right">Flagged to officer</th><th className="text-right">Silent failures</th><th className="text-right">s/case p50</th></tr></thead>
              <tbody>
                {["all", ...groups].map((g) => { const x = ev.summary[g]; if (!x) return null; return (
                  <tr key={g}><td className="font-medium">{g}</td><td className="tnum text-right">{x.n_cases}</td><td className="tnum text-right">{P(x.classification_acc, 0)}</td><td className="tnum text-right">{P(x.stmt_row_recall, 1)}</td><td className="tnum text-right">{P(x.stmt_row_precision, 1)}</td>
                    <td className="tnum text-right">{P(x.stmt_category_acc, 1)}</td><td className="tnum text-right">{P(x.stmt_header_field_acc, 0)}</td><td className="tnum text-right">{P(x.decl_field_acc, 0)}</td><td className="tnum text-right">{P(x.reg_field_acc, 0)}</td>
                    <td className="tnum text-right">{P(x.recon_verdict_agreement, 0)}</td><td className="tnum text-right">{P(x.pii_recall, 1)}</td><td className="tnum text-right">{P(x.flagged_share, 0)}</td><td className="tnum text-right">{P(x.silent_failure_share, 0)}</td><td className="tnum text-right">{x.sec_per_case_p50.toFixed(1)}</td></tr>); })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {ev?.llm && (
        <Card className="mt-6" pad={false}>
          <div className="border-b border-line px-5 py-4"><H sub={`Same ${ev.llm.n_cases} scan and photo cases and seeds as above, rerun with the PII-masked text fallback (${ev.llm.mode}). The model sees OCR text only, never images, and every output is re-validated.`}>What the model adds on degraded documents</H></div>
          <div className="overflow-x-auto scroll-thin">
            <table className="dense w-full text-[12.5px]">
              <thead><tr><th>Slice</th><th>Metric</th><th className="text-right">Rules only</th><th className="text-right">+ LLM fallback</th></tr></thead>
              <tbody>
                {["deg=scan", "deg=photo"].flatMap((g) => [["stmt_row_recall", "Statement rows recovered"], ["stmt_header_field_acc", "Statement header fields"], ["decl_field_acc", "Declaration fields"], ["reg_field_acc", "Registration fields"]].map(([k, label]) => (
                  <tr key={g + k}><td className="font-medium">{g}</td><td>{label}</td><td className="tnum text-right">{P(ev.summary[g][k], 1)}</td><td className="tnum text-right">{P(ev.llm.summary[g][k], 1)}</td></tr>
                )))}
              </tbody>
            </table>
          </div>
          <p className="px-5 py-3 text-[12px] text-muted">Honest reading: the fallback repairs identity and tax fields on photos, but it cannot recover statement rows that OCR never read, so the officer flag stays on. A vision model in the bank&apos;s own perimeter is the designed next step.</p>
        </Card>
      )}
      {calls.length > 0 && (
        <Card className="mt-6" pad={false}>
          <div className="border-b border-line px-5 py-3 text-[13px] font-medium">Recent model calls (Router log)</div>
          <table className="dense w-full text-[12.5px]"><thead><tr><th>Purpose</th><th>Provider</th><th>Model</th><th className="text-right">Tokens in/out</th><th className="text-right">Seconds</th><th className="text-right">Cost</th></tr></thead>
            <tbody>{calls.slice().reverse().slice(0, 12).map((c, i) => <tr key={i}><td>{c.purpose}</td><td>{c.provider}</td><td>{c.model}</td><td className="tnum text-right">{c.tokens_in}/{c.tokens_out}</td><td className="tnum text-right">{c.seconds}</td><td className="tnum text-right">{c.cost_usd > 0 || c.provider === "local" ? `$${c.cost_usd.toFixed(4)}` : "unpriced"}</td></tr>)}</tbody></table>
        </Card>
      )}
      {pub && <Card className="mt-6"><H>FGate public key</H><pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[11px] text-ink-2">{pub.pem}</pre></Card>}
    </Shell>
  );
}

function Mod({ name, role, ok, children }: { name: string; role: string; ok?: boolean; children?: React.ReactNode }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div><div className="serif text-[18px]">{name}</div><div className="text-[12px] text-muted">{role}</div></div>
        <Chip tone={ok ? "good" : "warn"}>{ok ? "live" : "not built"}</Chip>
      </div>
      <div className="mt-3 space-y-1.5">{children}</div>
    </Card>
  );
}
const KV = ({ k, v }: { k: string; v: string }) => <div className="flex items-baseline justify-between gap-3 text-[12.5px]"><span className="text-muted">{k}</span><span className="tnum text-right text-ink">{v}</span></div>;
const Dim = ({ children }: { children: React.ReactNode }) => <p className="pt-1 text-[11.5px] text-muted">{children}</p>;
