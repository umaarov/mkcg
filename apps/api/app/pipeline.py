"""Case pipeline: extraction -> verification -> analysis, with a step log and audit events."""
from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .db import Case, Document, now, session
from .modules.fgate import chain
from .modules.formalbrief import memo as memo_mod
from .modules.formalbrief.facts import build_facts
from .modules.ocrgate.common import best_label, norm_text, sim
from .modules.ocrgate.extract import extract_document
from .modules.ocrgate.llm_extract import llm_fallback
from .modules.revenuegate.reconcile import reconcile
from .modules.rulesengine.engine import evaluate, load_policy
from .modules.router import gateway
from .modules.scoring import features as F
from .modules.scoring import model as scorer
from .modules.statement.analytics import affordability, compute_metrics

POOL = ThreadPoolExecutor(max_workers=3)
AS_OF = date.fromisoformat(load_policy()["as_of"])


def _step(case: Case, name: str, t0: float, **info):
    steps = list(case.steps or [])
    steps.append(dict(name=name, seconds=round(time.time() - t0, 2), at=now().isoformat(), **info))
    case.steps = steps


def submit_extraction(case_id: str):
    POOL.submit(run_extraction, case_id)


def run_extraction(case_id: str):
    try:
        with session() as s:
            case = s.get(Case, case_id)
            case.status = "EXTRACTING"
            case.steps = []
            docs = list(case.docs)
            s.commit()
            t_all = time.time()
            for d in docs:
                t0 = time.time()
                res, _pages = extract_document(Path(d.path), d.filename, llm=llm_fallback)
                d.doc_type, d.lang, d.source, d.pages = res.doc_type, res.lang, res.source, res.pages
                d.ocr_conf, d.seconds = res.ocr_conf, res.seconds
                d.extraction = dict(fields=[f.to_dict() for f in res.fields], transactions=[t.to_dict() for t in res.transactions],
                                    validations=res.validations, methods=res.methods, llm_used=res.llm_used,
                                    page_sizes=[[p.width, p.height] for p in _pages])
                _step(case, f"OCRGate: {d.filename}", t0, doc_type=res.doc_type, source=res.source, pages=res.pages,
                      rows=len(res.transactions), llm=res.llm_used)
                s.commit()
            chain.append("system", "extraction_done", case_id, dict(docs=[d.filename for d in docs], seconds=round(time.time() - t_all, 2)))
            _prefill_case(case)
            s.commit()
        run_analysis(case_id)
    except Exception as e:  # noqa: BLE001
        with session() as s:
            case = s.get(Case, case_id)
            case.status = "FAILED"
            case.result = dict(error=str(e), trace=traceback.format_exc()[-1500:])
        chain.append("system", "failed", case_id, dict(error=str(e)[:200]))


def _prefill_case(case: Case):
    for d in case.docs:
        for f in (d.extraction or {}).get("fields", []):
            if f["key"] in ("holder", "org_name", "taxpayer") and not case.applicant:
                case.applicant = str(f["value"])
            if f["key"] == "tin" and not case.tin:
                case.tin = str(f["value"])


def _field(doc: Document, key: str):
    for f in (doc.extraction or {}).get("fields", []):
        if f["key"] == key:
            return f.get("verified_value", f["value"]) if f.get("verified_value") not in (None, "") else f["value"]
    return None


def _core(name: str) -> str:
    n = norm_text(name)
    for w in ("mchj", "ооо", "мчж", "xk", "хк", "чп", "yatt", "ятт", "ип", '"', "«", "»"):
        n = n.replace(w, " ")
    return " ".join(n.split())


def _quality_issues(st: Document) -> float:
    """Share of statement rows that needed chain repair, had no readable date, or were dropped; plus OCR weakness."""
    stats = (st.extraction.get("methods") or {}).get("stats") or {}
    rows = max(stats.get("rows", 0), 1)
    flagged = sum(1 for t in st.extraction.get("transactions", []) if any(f in t.get("flags", []) for f in (
        "amount_repaired_from_balance", "balance_repaired_from_amount", "amount_missing", "date_inferred", "date_interpolated")))
    share = (flagged + stats.get("unparsed", 0) * 0) / rows
    if st.source == "ocr" and st.ocr_conf < 75:
        share = max(share, 0.12)       # weak OCR: treat as a data-quality failure even when the chain looks tidy
    return round(share, 4)


def run_analysis(case_id: str):
    try:
        with session() as s:
            case = s.get(Case, case_id)
            case.status = "ANALYZING"
            s.commit()
            t0 = time.time()
            docs = {d.doc_type: d for d in case.docs if d.doc_type in ("statement", "declaration", "registration")}
            missing = [t for t in ("statement", "declaration", "registration") if t not in docs]
            result: dict = dict(missing_documents=missing)
            if "statement" not in docs or not docs["statement"].extraction.get("transactions"):
                case.status = "NEEDS_REVIEW"
                case.result = dict(result, error="no bank statement with transactions could be extracted")
                _step(case, "Statement", t0, ok=False)
                s.commit()
                return
            st = docs["statement"]
            txs = st.extraction["transactions"]
            rows = [dict(date=t["date"], debit=t["debit"], credit=t["credit"], balance=t["balance"],
                         category=t.get("verified_category") or t["category"], cp_tin=t.get("cp_tin", "")) for t in txs]
            opening = float(_field(st, "opening") or txs[0]["balance"] - txs[0]["credit"] + txs[0]["debit"])
            closing = float(_field(st, "closing") or txs[-1]["balance"])
            p_start = _field(st, "period_start") or min(t["date"] for t in txs)[:8] + "01"
            p_end = _field(st, "period_end") or max(t["date"] for t in txs)
            metrics = compute_metrics(rows, opening, closing, str(p_start), str(p_end))
            _step(case, "Statement", t0, rows=len(rows), months=metrics["n_months"])
            t1 = time.time()
            pol = load_policy()
            aff = affordability(metrics, case.amount, case.term, pol["pricing"]["annual_rate"], pol["pricing"]["max_payment_share"])
            decl = {}
            if "declaration" in docs:
                for k in ("rev_q1", "rev_q2", "rev_total"):
                    v = _field(docs["declaration"], k)
                    if v is not None:
                        decl[k] = float(v)
            recon = reconcile(decl, metrics) if decl.get("rev_total") else None
            _step(case, "RevenueGate", t1, verdict=(recon or {}).get("verdict", "no declaration"))
            # identity & consistency
            tins = {str(_field(d, "tin")) for d in docs.values() if _field(d, "tin")}
            names_ = [(_field(docs["statement"], "holder")), (_field(docs.get("registration"), "org_name")) if "registration" in docs else None,
                      (_field(docs.get("declaration"), "taxpayer")) if "declaration" in docs else None]
            names_ = [n for n in names_ if n]
            name_ok = all(sim(_core(a), _core(b)) > 0.7 for a in names_ for b in names_)
            identity_ok = len(tins) <= 1 and name_ok
            reg_date = _field(docs["registration"], "reg_date") if "registration" in docs else None
            age = ((AS_OF - date.fromisoformat(str(reg_date))).days / 30.4) if reg_date else None
            all_fields = [f for d in docs.values() for f in d.extraction.get("fields", [])]
            low = [f for f in all_fields if f["conf"] < 0.85 and not f.get("verified_by")]
            low_tx = [t for t in txs if t["conf"] < 0.85 and not t.get("verified_by")]
            verified_share = 1.0 if case.result.get("verified") else (0.0 if (low or low_tx) else 1.0)
            rec_for_feat = recon or dict(gap_adj=1.0, verdict="consistent", declared_total=0.0, bank_inflow=metrics["op_inflow_total"],
                                    underwriting_revenue_basis=metrics["op_inflow_total"], roundtrip_amount=metrics.get("roundtrip_amount", 0.0))
            feats = F.build(metrics, aff, rec_for_feat, age if age is not None else 0.0)
            t2 = time.time()
            sc = scorer.score(feats)
            _step(case, "Scoring", t2, pd=round(sc.get("pd", 0), 4), band=sc.get("band"))
            t3 = time.time()
            stmt_validations = {v["rule"]: v["ok"] for v in st.extraction.get("validations", [])}
            ctx_rules = dict(
                request_amount=case.amount, request_term=case.term, business_age_months=age,
                active_months=metrics["active_months"], dscr=aff["dscr"], loan_to_annual_inflow=aff["loan_to_annual_inflow"],
                top1_share=metrics["top1_share"], gap_adj=(recon or {}).get("gap_adj"), roundtrip_share=metrics["roundtrip_share"],
                inflow_cv=metrics["inflow_cv"], trend_ratio=metrics["trend_ratio"],
                low_balance_days_share=metrics["low_balance_days_share"], cashout_ratio=metrics["cashout_ratio"],
                non_operating_in_share=metrics["non_operating_in_share"],
                identity_gap_share=abs(opening + metrics["total_credit"] - metrics["total_debit"] - closing) / max(metrics["total_credit"], 1.0),
                identity_consistent=identity_ok,
                statement_age_days=(AS_OF - date.fromisoformat(str(p_end))).days, fields_verified_share=verified_share,
                extraction_quality_issues=_quality_issues(st))
            rules = evaluate(ctx_rules)
            # a low model band cannot override rules, but a bad band downgrades APPROVE -> REVIEW
            if sc.get("available") and rules["recommendation"] == "APPROVE" and sc["band"] in ("D", "E"):
                rules["recommendation"], rules["reason"] = "REVIEW", f"model band {sc['band']}"
            if missing:
                rules["recommendation"] = "REFER" if rules["recommendation"] in ("APPROVE", "REVIEW") else rules["recommendation"]
            _step(case, "RulesEngine", t3, recommendation=rules["recommendation"], refer=rules["counts"]["refer"], fail=rules["counts"]["fail"])
            ctx = dict(metrics=metrics, afford=aff, recon=rec_for_feat, request=dict(amount=case.amount, term=case.term),
                       score=sc, rules=rules, business_age_months=age or 0.0)
            facts = build_facts(ctx)
            t4 = time.time()
            m = memo_mod.generate(ctx, facts, case.lang if case.lang in ("en", "uz", "ru") else "uz", use_llm=False)
            _step(case, "FormalBrief", t4, writer=m["writer"], verifier_ok=m["verifier"]["ok"])
            keep_verified = bool(case.result.get("verified"))
            case.result = dict(
                missing_documents=missing, metrics=metrics, afford=aff, recon=recon, rules_ctx=ctx_rules,
                rules=rules, score=sc, facts=[f.to_dict() for f in facts], memo={m["lang"]: m},
                identity=dict(ok=identity_ok, tins=sorted(tins), names=names_), business_age_months=age,
                verified=keep_verified, low_confidence=dict(fields=len(low), transactions=len(low_tx)),
                period=dict(start=str(p_start), end=str(p_end)))
            case.status = "ANALYZED"
            chain.append("system", "analysis_done", case_id, dict(recommendation=rules["recommendation"], pd=sc.get("pd"),
                                                                  policy=rules["policy_version"]))
            s.commit()
    except Exception as e:  # noqa: BLE001
        with session() as s:
            case = s.get(Case, case_id)
            case.status = "FAILED"
            case.result = dict(error=str(e), trace=traceback.format_exc()[-1500:])
        chain.append("system", "failed", case_id, dict(error=str(e)[:200]))
