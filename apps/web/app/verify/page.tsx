"use client";
import { useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { useApp } from "@/components/Providers";
import { Button, Card, Chip } from "@/components/ui";

export default function Verify() {
  const { t } = useApp();
  const [txt, setTxt] = useState("");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  async function check(body = txt) {
    setBusy(true); setRes(null);
    try {
      const r = await fetch("/api/fgate/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body });
      setRes(await r.json());
    } catch (e: any) { setRes({ valid: false, error: e.message }); } finally { setBusy(false); }
  }
  function tamper() {
    try {
      const j = JSON.parse(txt);
      j.dossier.request.amount = (j.dossier.request.amount || 0) + 1;
      const s = JSON.stringify(j, null, 1);
      setTxt(s); check(s);
    } catch { setRes({ valid: false, error: "paste a valid dossier first" }); }
  }
  return (
    <Shell>
      <div className="mx-auto max-w-[780px]">
        <h1 className="serif text-[30px] leading-9">{t("vf.title")}</h1>
        <p className="mt-1 text-[13px] text-muted">{t("vf.sub")}</p>
        <Card className="mt-6">
          <textarea value={txt} onChange={(e) => setTxt(e.target.value)} rows={12} spellCheck={false} placeholder='{"dossier": {...}, "signature": "...", "sha256": "..."}'
            className="w-full rounded-lg border border-line-2 bg-surface-2 p-3 font-mono text-[12px] text-ink" />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button disabled={!txt || busy} onClick={() => check()}>{t("vf.check")}</Button>
            <Button variant="ghost" onClick={() => file.current?.click()}>Upload .json</Button>
            <Button variant="ghost" disabled={!txt} onClick={tamper} title="Changes the requested amount by 1 UZS and re-verifies">Tamper test</Button>
            <input ref={file} type="file" accept=".json" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setTxt(await f.text()); }} />
          </div>
          {res && (
            <div className={`mt-4 rounded-lg p-4 ${res.valid ? "bg-good-soft text-good" : "bg-bad-soft text-bad"}`} role="status">
              <div className="serif text-[20px]">{res.valid ? "Signature valid — the dossier is exactly what FGate signed." : "Signature invalid — the content was changed or was not signed by this server."}</div>
              <div className="mt-1 text-[12px] opacity-80">{res.key_fingerprint && `key ${res.key_fingerprint}`} {res.error && `(${res.error})`}</div>
            </div>
          )}
        </Card>
      </div>
    </Shell>
  );
}
