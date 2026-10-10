"""CreditGateway evaluation harness.

Builds a stratified synthetic test set (layout x language x degradation), runs the *production* OCRGate /
PIIModule / Statement / RevenueGate code on it and compares with ground truth.

    cd apps/api && uv run python ../../eval/run_eval.py --n 81                        # rules only -> results/latest.json
    CG_OPENAI_BASE_URL=... CG_OPENAI_API_KEY=... uv run python ../../eval/run_eval.py --n 81 --llm on --only scan,photo
                                                                                      # same seeds with the PII-masked LLM fallback -> results/latest_llm.json

Everything measured here is on synthetic documents we generated; see README for the limits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import settings  # noqa: E402
from app.datagen import bundle  # noqa: E402
from app.datagen.sme import random_sme  # noqa: E402
from app.modules.ocrgate.align import align  # noqa: E402
from app.modules.ocrgate.extract import extract_document  # noqa: E402
from app.modules.ocrgate.llm_extract import llm_fallback  # noqa: E402
from app.modules.ocrgate.text import full_text, read_document  # noqa: E402
from app.modules.piimodule.mask import Masker, residual_pii  # noqa: E402
from app.modules.revenuegate.reconcile import reconcile  # noqa: E402
from app.modules.statement.analytics import compute_metrics  # noqa: E402

OUT = Path(__file__).parent / "results"
WORK = Path(__file__).parent / "work"
LANGS = ["uz", "uzc", "ru"]
LAYOUTS = ["A", "B", "C"]
DEGRADE = [None, "scan", "photo"]


def plan(n: int):
    """Full factorial (degradation x language x layout) repeated, so no factor is confounded with another."""
    return [dict(seed=700_000 + i, degrade=DEGRADE[i % 3], lang=LANGS[(i // 3) % 3], layout=LAYOUTS[(i // 9) % 3]) for i in range(n)]


def run_one(cfg: dict) -> dict:
    sme = random_sme(cfg["seed"], "random", cfg["lang"])
    d = WORK / f"{cfg['seed']}"
    truth = bundle.build_bundle(sme, cfg["seed"], d, layout=cfg["layout"], degrade=cfg["degrade"], lang=cfg["lang"], with_outcome=False)
    res = dict(cfg=cfg, docs={})
    pii_secrets = truth["pii"]
    for name in ("statement", "declaration", "registration"):
        t0 = time.time()
        r, pages = extract_document(d / f"{name}.pdf", llm=llm_fallback if os.environ.get("CG_EVAL_LLM") == "1" else None)
        sec = time.time() - t0
        fields = {f.key: f for f in r.fields}
        entry = dict(cls_ok=r.doc_type == name, seconds=round(sec, 2), route=r.source, pages=r.pages, llm=bool(r.llm_used))
        text = full_text(pages)
        m = Masker()
        masked = m.mask(text)
        entry["pii_leaks"] = len(residual_pii(masked, [s for s in pii_secrets if s]))
        entry["pii_total"] = len([s for s in pii_secrets if s and s.replace(" ", "") in text.replace(" ", "")])
        if name == "statement":
            gt = truth["statement"]["rows"]
            pairs, mp, mt = align(r.transactions, gt)
            entry.update(rows_truth=len(gt), rows_parsed=len(r.transactions), rows_matched=len(pairs),
                         cat_ok=sum(1 for i, j in pairs if r.transactions[i].category == gt[j]["category"]),
                         date_exact=sum(1 for i, j in pairs if r.transactions[i].date == gt[j]["date"]))
            st = truth["statement"]
            hdr = {"tin": truth["applicant"]["tin"], "account": truth["applicant"]["account"], "opening": st["opening"], "closing": st["closing"],
                   "period_start": st["period_start"], "period_end": st["period_end"]}
            entry["hdr"] = {k: (k in fields and str(fields[k].value if not isinstance(fields[k].value, float) else round(fields[k].value)) == str(v)) for k, v in hdr.items()}
            entry["chain_ok"] = all(v["ok"] for v in r.validations if v["rule"] in ("balance_identity",))
            # would the product have warned the officer? (same logic as pipeline._quality_issues + case-page banner)
            stats = r.methods.get("stats", {})
            n = max(stats.get("rows", 0), 1)
            nflag = sum(1 for t in r.transactions if any(f in t.flags for f in ("amount_repaired_from_balance", "balance_repaired_from_amount", "amount_missing", "date_inferred", "date_interpolated")))
            issues = nflag / n
            if r.source == "ocr" and r.ocr_conf < 75:
                issues = max(issues, 0.12)
            entry["flagged"] = bool(issues > 0.02 or any(not v["ok"] for v in r.validations))
            entry["rows_recall_case"] = len(pairs) / max(len(gt), 1)
            # downstream metric fidelity: compute analytics on parsed vs true rows
            def rows(txs, truth_mode):
                return [dict(date=(t["date"] if truth_mode else t.date), debit=(t["debit"] if truth_mode else t.debit), credit=(t["credit"] if truth_mode else t.credit),
                             balance=(t["balance"] if truth_mode else t.balance), category=(t["category"] if truth_mode else t.category),
                             cp_tin=(t["cp_tin"] if truth_mode else t.cp_tin)) for t in txs]
            try:
                mt_ = compute_metrics(rows(gt, True), st["opening"], st["closing"], "2026-04-01", "2026-09-30")
                mp_ = compute_metrics(rows(r.transactions, False), st["opening"], st["closing"], "2026-04-01", "2026-09-30")
                entry["metric_err"] = {k: abs(mp_[k] - mt_[k]) / max(abs(mt_[k]), 1e-9) for k in ("op_inflow_avg", "net_cf_avg", "top1_share")}
                dec = truth["declaration"]
                v_t = reconcile(dec, mt_)["verdict"]
                v_p = reconcile(dec, mp_)["verdict"]
                entry["recon_verdict_ok"] = v_t == v_p
            except Exception as e:  # noqa: BLE001
                entry["metric_err_exc"] = str(e)[:80]
        elif name == "declaration":
            gt = truth["declaration"]
            entry["f"] = {k: (k in fields and float(fields[k].value) == float(gt[k])) for k in ("rev_q1", "rev_q2", "rev_total", "tax_amount", "tax_rate", "employees")}
            entry["tin"] = "tin" in fields and fields["tin"].value == truth["applicant"]["tin"]
        else:
            a = truth["applicant"]
            entry["f"] = {"tin": "tin" in fields and fields["tin"].value == a["tin"], "pinfl": "pinfl" in fields and fields["pinfl"].value == a["pinfl"],
                          "reg_date": "reg_date" in fields and fields["reg_date"].value == a["reg_date"]}
        res["docs"][name] = entry
    return res


def agg(results: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in results:
        groups["all"].append(r)
        groups[f"deg={r['cfg']['degrade'] or 'clean'}"].append(r)
        groups[f"lang={r['cfg']['lang']}"].append(r)
        groups[f"layout={r['cfg']['layout']}"].append(r)
    out = {}
    for g, rs in groups.items():
        st = [r["docs"]["statement"] for r in rs]
        de = [r["docs"]["declaration"] for r in rs]
        rg = [r["docs"]["registration"] for r in rs]
        rows_t = sum(s["rows_truth"] for s in st)
        fl = lambda ds, key: sum(sum(d["f"].values()) for d in ds) / max(sum(len(d["f"]) for d in ds), 1)  # noqa: E731
        hdr_ok = sum(sum(s["hdr"].values()) for s in st) / max(sum(len(s["hdr"]) for s in st), 1)
        me = [s["metric_err"] for s in st if "metric_err" in s]
        pii_leaks = sum(d["pii_leaks"] for r in rs for d in r["docs"].values())
        pii_total = sum(d["pii_total"] for r in rs for d in r["docs"].values())
        out[g] = dict(
            n_cases=len(rs),
            classification_acc=sum(d["cls_ok"] for r in rs for d in r["docs"].values()) / (3 * len(rs)),
            stmt_row_recall=sum(s["rows_matched"] for s in st) / max(rows_t, 1),
            stmt_row_precision=sum(s["rows_matched"] for s in st) / max(sum(s["rows_parsed"] for s in st), 1),
            stmt_category_acc=sum(s["cat_ok"] for s in st) / max(sum(s["rows_matched"] for s in st), 1),
            stmt_header_field_acc=hdr_ok,
            stmt_balance_identity_pass=sum(s["chain_ok"] for s in st) / len(st),
            decl_field_acc=fl(de, "f"), reg_field_acc=fl(rg, "f"),
            recon_verdict_agreement=sum(s.get("recon_verdict_ok", False) for s in st) / len(st),
            flagged_share=sum(s.get("flagged", False) for s in st) / len(st),
            silent_failure_share=sum(1 for s in st if s["rows_recall_case"] < 0.9 and not s["flagged"]) / len(st),
            bad_extraction_share=sum(1 for s in st if s["rows_recall_case"] < 0.9) / len(st),
            median_rel_err_op_inflow=sorted(m["op_inflow_avg"] for m in me)[len(me) // 2] if me else None,
            median_rel_err_net_cf=sorted(m["net_cf_avg"] for m in me)[len(me) // 2] if me else None,
            pii_recall=1 - pii_leaks / max(pii_total, 1), pii_items=pii_total,
            sec_per_case_p50=sorted(sum(d["seconds"] for d in r["docs"].values()) for r in rs)[len(rs) // 2],
            sec_per_case_p95=sorted(sum(d["seconds"] for d in r["docs"].values()) for r in rs)[min(len(rs) - 1, int(len(rs) * 0.95))],
        )
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--llm", choices=["on", "off"], default="off")
    ap.add_argument("--only", default="", help="comma list of degradations to keep, e.g. scan,photo")
    a = ap.parse_args()
    cfgs = plan(a.n)
    if a.only:
        keep = set(a.only.split(","))
        cfgs = [c for c in cfgs if (c["degrade"] or "clean") in keep]
    if a.llm == "on":
        os.environ["CG_EVAL_LLM"] = "1"
    suffix = "_llm" if a.llm == "on" else ""
    t0 = time.time()
    with ProcessPoolExecutor(a.workers) as ex:
        results = list(ex.map(run_one, cfgs))
    summary = agg(results)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), n_cases=len(results), wall_seconds=round(time.time() - t0),
                   mode=("rules + PII-masked LLM fallback (" + settings.openai_extraction_model + ")") if a.llm == "on" else "rules-only (deterministic parsers; LLM fallback disabled)", summary=summary,
                   note="All documents synthetic, generated by app/datagen with known ground truth. Header/field accuracy is exact match.")
    (OUT / f"latest{suffix}.json").write_text(json.dumps(payload, indent=1))
    (OUT / f"per_case{suffix}.json").write_text(json.dumps(results, indent=1))
    for g in ("all", "deg=clean", "deg=scan", "deg=photo"):
        s = summary.get(g)
        if s:
            print(g, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
