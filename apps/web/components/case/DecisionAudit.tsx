"use client";
import { useEffect, useState } from "react";
import { useApp } from "../Providers";
import { Button, Card, Chip, H, recTone } from "../ui";
import { api, download, getUser } from "@/lib/api";
import { dt } from "@/lib/format";

export function DecisionTab({ c, reload }: { c: any; reload: () => void }) {
  const { t } = useApp();
  const user = getUser();
  const [outcome, setOutcome] = useState<"approve" | "decline" | "escalate">("approve");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const rec = c.result.rules.recommendation;
  const verified = c.result.verified;
  const dec = c.decision;
  const override = (outcome === "approve" && (rec === "REFER" || rec === "DECLINE")) || (outcome === "decline" && rec === "APPROVE");
  const needCommittee = outcome === "approve" && (rec === "REFER" || rec === "DECLINE") && user?.role === "officer";

  async function submit() {
    setBusy(true); setErr("");
    try { await api(`/api/cases/${c.id}/decision`, { method: "POST", json: { outcome, reason } }); reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
      <Card>
        <H>{t("dec.title")}</H>
        <div className="mb-4 flex items-center gap-2 text-[13px]"><span className="text-muted">{t("col.rec")}:</span><Chip tone={recTone(rec)}>{t(`rec.${rec}`)}</Chip><span className="text-[12px] text-muted">{c.result.rules.reason}</span></div>
        {dec ? (
          <div className="rounded-lg border border-line bg-surface-2 p-4">
            <div className="flex items-center gap-2"><Chip tone={dec.outcome === "approve" ? "good" : dec.outcome === "decline" ? "bad" : "warn"}>{t(`dec.${dec.outcome}`)}</Chip>{dec.override && <Chip tone="warn">override</Chip>}</div>
            <p className="mt-2 text-[13px]">{dec.by} ({dec.role}) · {dt(dec.at)}</p>
            {dec.reason && <p className="mt-1 text-[13px] text-ink-2">“{dec.reason}”</p>}
          </div>
        ) : (
          <>
            {!verified && <p className="mb-3 rounded-lg bg-warn-soft px-3 py-2 text-[12.5px] text-warn">{t("dec.needver")}</p>}
            <div className="grid grid-cols-3 gap-2">
              {(["approve", "decline", "escalate"] as const).map((o) => (
                <button key={o} onClick={() => setOutcome(o)} className={`rounded-lg border px-3 py-2.5 text-[13px] font-medium transition ${outcome === o ? "border-accent bg-accent-soft text-accent" : "border-line hover:bg-surface-2"}`}>{t(`dec.${o}`)}</button>
              ))}
            </div>
            <label className="mt-4 block text-[12px] text-muted">{t("dec.reason")}
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-line-2 bg-surface px-3 py-2 text-[13.5px] text-ink" /></label>
            {override && <p className="mt-2 text-[12px] text-warn">This goes against the system view and will be recorded as an override.</p>}
            {needCommittee && <p className="mt-1 text-[12px] text-bad">{t("dec.four")}</p>}
            {err && <p className="mt-2 text-[12.5px] text-bad" role="alert">{err}</p>}
            <Button className="mt-4" disabled={busy || !verified} onClick={submit}>{busy ? t("common.loading") : t("dec.title")}</Button>
          </>
        )}
      </Card>
      <Card>
        <H>{t("dec.dossier")}</H>
        <p className="text-[13px] text-ink-2">Canonical JSON of the whole case — document hashes, verified fields, metrics, rules, score, memo, decision, and the audit-chain head — signed with Ed25519 by FGate.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => download(`/api/cases/${c.id}/dossier`, `dossier-${c.id}.json`)}>{t("dec.json")}</Button>
          <Button variant="ghost" onClick={() => download(`/api/cases/${c.id}/dossier.pdf`, `dossier-${c.id}.pdf`, "POST")}>{t("dec.pdf")}</Button>
        </div>
        <p className="mt-3 text-[12px] text-muted">Anyone can check a downloaded dossier on the “{t("nav.verify")}” page without logging in.</p>
      </Card>
    </div>
  );
}

export function AuditTab({ c }: { c: any }) {
  const { t } = useApp();
  const [ev, setEv] = useState<any[] | null>(null);
  const [chain, setChain] = useState<any>(null);
  useEffect(() => {
    api(`/api/cases/${c.id}/audit`).then(setEv).catch(() => setEv([]));
    api("/api/fgate/verify-chain").then(setChain).catch(() => {});
  }, [c.id, c.status]);
  return (
    <div className="space-y-4">
      {chain && <div className="flex items-center gap-3 text-[13px]"><Chip tone={chain.ok ? "good" : "bad"}>{chain.ok ? "✓ hash chain intact" : "✕ chain broken"}</Chip><span className="text-muted tnum">{chain.events} events · head {chain.head.slice(0, 16)}…</span></div>}
      <Card pad={false}>
        <table className="dense w-full text-[12.5px]">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th><th>Hash</th></tr></thead>
          <tbody>
            {ev?.map((e) => (
              <tr key={e.id}>
                <td className="tnum whitespace-nowrap text-muted">{dt(e.ts)}</td><td>{e.actor}</td><td><Chip>{e.action}</Chip></td>
                <td className="max-w-[360px] truncate text-muted" title={JSON.stringify(e.payload)}>{JSON.stringify(e.payload)}</td>
                <td className="font-mono text-[11px] text-muted">{e.hash.slice(0, 12)}…<span className="text-line-2"> ← {e.prev_hash.slice(0, 6)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
