"""Decision dossier: everything an auditor needs to re-trace a decision, signed by FGate."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .db import Case
from .datagen.render import FONT_DIR
from .modules.fgate import chain
from .modules.scoring import model as scorer

VERSION = "creditgateway-0.1"


def build(case: Case) -> dict:
    docs = []
    for d in case.docs:
        p = Path(d.path)
        sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""
        fields = [dict(key=f["key"], value=f.get("verified_value") if f.get("verified_value") not in (None, "") else f["value"],
                       extracted=f["value"], confidence=f["conf"], source=f.get("source"), verified_by=f.get("verified_by"),
                       page=f.get("page"), bbox=f.get("bbox")) for f in (d.extraction or {}).get("fields", [])]
        docs.append(dict(filename=d.filename, sha256=sha, type=d.doc_type, lang=d.lang, route=d.source, pages=d.pages,
                         validations=(d.extraction or {}).get("validations", []),
                         methods=(d.extraction or {}).get("methods", {}).get("path"), fields=fields,
                         n_transactions=len((d.extraction or {}).get("transactions", []))))
    r = case.result or {}
    card = scorer.model_card()
    ver = chain.verify_chain()
    return dict(
        version=VERSION, case_id=case.id, created=case.created.isoformat(), applicant=case.applicant, tin=case.tin,
        request=dict(amount=case.amount, term=case.term), documents=docs,
        metrics=r.get("metrics"), affordability=r.get("afford"), revenue_reconciliation=r.get("recon"),
        rules=r.get("rules"), score=r.get("score"), facts=r.get("facts"), memo=r.get("memo"),
        identity=r.get("identity"), verified=r.get("verified"), decision=case.decision,
        model=dict(kind="LightGBM monotone", synthetic_training=True, auc_test=(card or {}).get("metrics", {}).get("auc_lightgbm"),
                   n_train_sme=(card or {}).get("data", {}).get("n_sme")),
        policy_version=(r.get("rules") or {}).get("policy_version"),
        audit_head=dict(hash=ver["head"], events=ver["events"], chain_ok=ver["ok"]),
    )


def pdf_bytes(signed: dict, lang: str = "en") -> bytes:
    for name, f in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf")):
        try:
            pdfmetrics.getFont(name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f)))
    d = signed["dossier"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 48

    def line(txt, font="DV", size=9, dy=14, x=44):
        nonlocal y
        if y < 60:
            c.showPage()
            y = h - 48
        c.setFont(font, size)
        c.drawString(x, y, txt[:120])
        y -= dy

    line("CreditGateway · Decision dossier", "DVB", 14, 22)
    line(f"Case {d['case_id']} · created {d['created'][:19]} · {d['version']}", size=8.5)
    line(f"Applicant: {d['applicant']}   Taxpayer ID: {d['tin']}")
    line(f"Request: {d['request']['amount']:,.0f} UZS over {d['request']['term']} months".replace(",", " "), dy=18)
    rules = d.get("rules") or {}
    line(f"System recommendation: {rules.get('recommendation')}   (policy {rules.get('policy_version')})", "DVB", 10, 16)
    sc = d.get("score") or {}
    if sc.get("available"):
        line(f"Model: default probability {sc['pd'] * 100:.1f}% · band {sc['band']} · trained on synthetic data", dy=16)
    dec = d.get("decision")
    if dec:
        line(f"Human decision: {dec['outcome']} by {dec['by']} ({dec['role']}) at {dec['at'][:19]}" + (" · OVERRIDE" if dec.get("override") else ""), "DVB", 10, 14)
        if dec.get("reason"):
            line(f"Reason: {dec['reason']}", dy=18)
    line("Rules", "DVB", 10, 14)
    for r in rules.get("results", []):
        line(f"{r['id']}  {r['outcome']:<6}  {r['label']['en']}  [{r['metric']}={_fmt(r['value'])}]", size=8, dy=11)
    y -= 6
    line("Documents (SHA-256)", "DVB", 10, 14)
    for doc in d["documents"]:
        line(f"{doc['filename']}  {doc['type']}  {doc['sha256'][:40]}…", size=8, dy=11)
    y -= 6
    line("Integrity", "DVB", 10, 14)
    line(f"Audit chain head: {d['audit_head']['hash'][:48]}…  events: {d['audit_head']['events']}  chain ok: {d['audit_head']['chain_ok']}", size=8, dy=11)
    line(f"Dossier SHA-256: {signed['sha256'][:48]}…", size=8, dy=11)
    line(f"Ed25519 signature key fingerprint: {signed['key_fingerprint']}", size=8, dy=11)
    line("Verify the JSON dossier at /api/fgate/verify. This PDF is a human-readable summary of the signed JSON.", size=8, dy=11)
    c.save()
    return buf.getvalue()


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)
