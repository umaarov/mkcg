"use client";
import { useMemo, useState } from "react";
import { useApp } from "../Providers";
import { Bar, Button, Card, Chip, H } from "../ui";
import { DocViewer, Hl } from "../DocViewer";
import { api } from "@/lib/api";
import { CATEGORY_LABEL, catLabel, nf0 } from "@/lib/format";

const FIELD_LABEL: Record<string, string> = {
  holder: "Account holder", tin: "Taxpayer ID (STIR/INN)", account: "Account number", bank: "Bank", period_start: "Period start", period_end: "Period end",
  opening: "Opening balance", closing: "Closing balance", taxpayer: "Taxpayer", rev_q1: "Revenue, quarter 1", rev_q2: "Revenue, quarter 2",
  rev_total: "Revenue, total", tax_rate: "Tax rate %", tax_amount: "Tax amount", employees: "Employees", submitted: "Submitted",
  org_name: "Organisation", reg_date: "Registered", activity: "Activity", director: "Director", pinfl: "PINFL", address: "Address", phone: "Phone",
};
const TYPE_TONE: Record<string, any> = { statement: "info", declaration: "accent", registration: "neutral", unknown: "warn" };

export function DocsTab({ c, reload }: { c: any; reload: () => void }) {
  const { t, lang } = useApp();
  const docs: any[] = c.docs;
  const [di, setDi] = useState(Math.max(0, docs.findIndex((d) => d.doc_type === "statement")));
  const [page, setPage] = useState(0);
  const [hl, setHl] = useState<Hl>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [txEdits, setTxEdits] = useState<Record<string, string>>({});
  const [onlyLow, setOnlyLow] = useState(false);
  const [limit, setLimit] = useState(60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const doc = docs[di];
  const ex = doc?.extraction || {};
  const fields: any[] = ex.fields || [];
  const txs: any[] = ex.transactions || [];
  const circ = new Set<number>(c.result?.metrics?.roundtrip_tx || []);
  const locked = c.status === "DECIDED";
  const lowFields = fields.filter((f) => f.conf < 0.85 && !f.verified_by);
  const lowTx = txs.filter((x) => x.conf < 0.85 && !x.verified_by);
  const shown = useMemo(() => (onlyLow ? txs.filter((x) => x.conf < 0.85 || circ.has(x.idx)) : txs), [txs, onlyLow]); // eslint-disable-line
  const nLow = docs.reduce((a, d) => a + (d.extraction?.fields || []).filter((f: any) => f.conf < 0.85 && !f.verified_by).length + (d.extraction?.transactions || []).filter((x: any) => x.conf < 0.85 && !x.verified_by).length, 0);

  const focus = (pg: number, bbox: number[] | null, tone?: any) => { setPage(pg); setHl({ page: pg, bbox, tone }); };

  async function confirm() {
    setBusy(true); setErr("");
    try {
      const corrections: any[] = [], tx_categories: any[] = [];
      Object.entries(edits).forEach(([k, v]) => { const [d, key] = k.split("::"); corrections.push({ doc_id: Number(d), key, value: v }); });
      Object.entries(txEdits).forEach(([k, v]) => { const [d, idx] = k.split("::"); tx_categories.push({ doc_id: Number(d), idx: Number(idx), category: v }); });
      await api(`/api/cases/${c.id}/verify`, { method: "POST", json: { corrections, tx_categories, accept_all_low: true } });
      setEdits({}); setTxEdits({}); reload();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap gap-2">
          {docs.map((d, i) => (
            <button key={d.id} onClick={() => { setDi(i); setPage(0); setHl(null); }}
              className={`rounded-lg border px-3 py-2 text-left text-[12.5px] transition ${i === di ? "border-accent bg-accent-soft" : "border-line bg-surface hover:bg-surface-2"}`}>
              <div className="flex items-center gap-2"><span className="font-medium">{d.filename}</span><Chip tone={TYPE_TONE[d.doc_type]}>{d.doc_type}</Chip></div>
              <div className="mt-1 text-[11.5px] text-muted">{d.lang || "—"} · {d.source === "ocr" ? `OCR ${d.ocr_conf.toFixed(0)}%` : "text layer"} · {d.pages}p · {d.seconds}s</div>
            </button>
          ))}
        </div>
        {doc && (
          <Card pad={false}>
            <div className="border-b border-line px-4 py-3"><div className="text-[13px] font-medium">{t("doc.checks")}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(ex.validations || []).map((v: any) => (
                  <Chip key={v.rule} tone={v.ok ? "good" : "bad"} title={v.detail}>{v.ok ? "✓" : "✕"} {v.rule.replace(/_/g, " ")}</Chip>
                ))}
                {ex.methods?.path && <Chip tone="neutral">route: {ex.methods.path}</Chip>}
                {ex.methods?.stats && <Chip tone={ex.methods.stats.repaired ? "warn" : "neutral"}>{ex.methods.stats.repaired} chain-repaired rows</Chip>}
              </div>
            </div>
            <div className="max-h-[420px] overflow-auto scroll-thin">
              <table className="dense w-full text-[13px]">
                <thead><tr><th>{t("doc.field")}</th><th>{t("doc.value")}</th><th>{t("doc.conf")}</th><th>{t("doc.source")}</th></tr></thead>
                <tbody>
                  {fields.map((f) => {
                    const k = `${doc.id}::${f.key}`;
                    const val = edits[k] ?? String(f.verified_value ?? f.value);
                    const low = f.conf < 0.85 && !f.verified_by;
                    return (
                      <tr key={f.key} className="cursor-pointer" onClick={() => focus(f.page, f.bbox, low ? "warn" : "accent")}>
                        <td className="text-ink-2">{FIELD_LABEL[f.key] || f.key}</td>
                        <td>
                          <input value={val} disabled={locked} onClick={(e) => e.stopPropagation()} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })}
                            className={`tnum w-full rounded border bg-transparent px-1.5 py-0.5 ${edits[k] !== undefined ? "border-accent" : "border-transparent hover:border-line-2"} text-ink`} />
                        </td>
                        <td className="w-24"><div className="flex items-center gap-2"><Bar value={f.conf} tone={f.conf >= 0.85 ? "good" : f.conf >= 0.6 ? "warn" : "bad"} /><span className="tnum text-[11px] text-muted">{Math.round(f.conf * 100)}</span></div></td>
                        <td>{f.verified_by ? <Chip tone="good">verified</Chip> : <Chip tone={f.source === "rule" ? "neutral" : "warn"}>{f.source}</Chip>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
        {doc?.doc_type === "statement" && (
          <Card pad={false}>
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <div className="text-[13px] font-medium">{t("doc.tx")} <span className="text-muted tnum">({txs.length})</span></div>
              <label className="flex items-center gap-2 text-[12px] text-muted"><input type="checkbox" checked={onlyLow} onChange={(e) => setOnlyLow(e.target.checked)} />{t("doc.onlylow")}</label>
            </div>
            <div className="max-h-[460px] overflow-auto scroll-thin">
              <table className="dense w-full text-[12.5px]">
                <thead><tr><th>#</th><th>Date</th><th>Counterparty / purpose</th><th className="text-right">Debit</th><th className="text-right">Credit</th><th>Category</th></tr></thead>
                <tbody>
                  {shown.slice(0, limit).map((x) => {
                    const low = x.conf < 0.85 && !x.verified_by;
                    const isCirc = circ.has(x.idx);
                    const k = `${doc.id}::${x.idx}`;
                    return (
                      <tr key={x.idx} className="cursor-pointer" onClick={() => focus(x.page, x.bbox, low ? "warn" : isCirc ? "bad" : "accent")}
                        style={low ? { background: "var(--warn-soft)" } : isCirc ? { background: "var(--bad-soft)" } : undefined}>
                        <td className="tnum text-muted">{x.idx + 1}</td>
                        <td className="tnum whitespace-nowrap">{x.date}</td>
                        <td className="max-w-[300px]"><div className="truncate" title={x.desc}>{x.cp_name || x.desc}</div>
                          {(low || isCirc || x.flags?.length > 0) && <div className="mt-0.5 flex gap-1">{isCirc && <Chip tone="bad">circular</Chip>}{low && <Chip tone="warn">check</Chip>}{x.flags?.map((fl: string) => <Chip key={fl}>{fl.replace(/_/g, " ")}</Chip>)}</div>}</td>
                        <td className="tnum text-right">{x.debit ? nf0(x.debit) : ""}</td>
                        <td className="tnum text-right">{x.credit ? nf0(x.credit) : ""}</td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <select disabled={locked} value={txEdits[k] ?? x.verified_category ?? x.category} onChange={(e) => setTxEdits({ ...txEdits, [k]: e.target.value })}
                            className="max-w-[150px] rounded border border-transparent bg-transparent py-0.5 text-[12px] hover:border-line-2">
                            {Object.keys(CATEGORY_LABEL).map((cat) => <option key={cat} value={cat}>{catLabel(cat, lang)}</option>)}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {shown.length > limit && <div className="p-3 text-center"><Button variant="ghost" onClick={() => setLimit(limit + 100)}>Show more ({shown.length - limit})</Button></div>}
            </div>
          </Card>
        )}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-4">
          <div className="flex-1 min-w-[220px]">
            {c.result?.verified ? <Chip tone="good">✓ {t("case.verified")}</Chip> : <div className="text-[12.5px] text-warn">{t("case.unverified")} <span className="tnum">({nLow})</span></div>}
            {err && <div className="mt-1 text-[12.5px] text-bad">{err}</div>}
          </div>
          <Button disabled={busy || locked} onClick={confirm}>{busy ? t("common.loading") : t("case.verify")}</Button>
        </div>
      </div>
      <div className="min-w-0 xl:sticky xl:top-20 xl:h-[calc(100vh-110px)]">
        {doc && <DocViewer cid={c.id} docId={doc.id} pages={doc.pages} pageSizes={ex.page_sizes || []} page={page} onPage={setPage} hl={hl} />}
      </div>
    </div>
  );
}
