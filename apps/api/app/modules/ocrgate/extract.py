"""OCRGate orchestrator: file -> typed fields + transactions + validations.

Strategy: deterministic parsers first (fast, free, exact on known layouts). The LLM fallback
(`llm_extract`) is only invoked when validation fails, so cost scales with difficulty, not volume.
"""
from __future__ import annotations

import time
from pathlib import Path

from .common import DocResult, FieldOut, TxOut
from .form_parser import classify, parse_declaration, parse_registration
from .statement_parser import parse_header, parse_transactions
from .text import detect_language, full_text, read_document


def validate_statement(fields: dict[str, FieldOut], txs: list[TxOut], stats: dict) -> list[dict]:
    v = []
    op, cl = fields.get("opening"), fields.get("closing")
    if txs:
        total_in = sum(t.credit for t in txs)
        total_out = sum(t.debit for t in txs)
        if op and cl:
            diff = float(op.value) + total_in - total_out - float(cl.value)
            v.append(dict(rule="balance_identity", ok=abs(diff) < 2.0,
                          detail=f"opening + credits - debits - closing = {diff:,.0f}"))
        v.append(dict(rule="rows_chain_consistent", ok=stats["chain_breaks"] == 0,
                      detail=f"{stats['chain_breaks']} chain breaks, {stats['repaired']} repaired, {stats['unparsed']} unparsed"))
        dates = sorted(t.date for t in txs)
        ps, pe = fields.get("period_start"), fields.get("period_end")
        if ps and pe:
            v.append(dict(rule="rows_within_period", ok=dates[0] >= ps.value and dates[-1] <= pe.value,
                          detail=f"{dates[0]} .. {dates[-1]}"))
    else:
        v.append(dict(rule="rows_found", ok=False, detail="no transaction rows parsed"))
    for key in ("holder", "tin", "account", "opening", "closing", "period_start"):
        v.append(dict(rule=f"has_{key}", ok=key in fields, detail=""))
    return v


def validate_declaration(f: dict[str, FieldOut]) -> list[dict]:
    v = []
    if all(k in f for k in ("rev_q1", "rev_q2", "rev_total")):
        d = float(f["rev_q1"].value) + float(f["rev_q2"].value) - float(f["rev_total"].value)
        v.append(dict(rule="quarters_sum_to_total", ok=abs(d) < 2.0, detail=f"diff {d:,.0f}"))
    if all(k in f for k in ("rev_total", "tax_rate", "tax_amount")):
        exp = float(f["rev_total"].value) * float(f["tax_rate"].value) / 100
        got = float(f["tax_amount"].value)
        ok = abs(exp - got) <= max(2000.0, 0.01 * exp)
        v.append(dict(rule="tax_equals_rate_times_base", ok=ok, detail=f"expected {exp:,.0f}, found {got:,.0f}"))
    for key in ("tin", "rev_total", "tax_amount"):
        v.append(dict(rule=f"has_{key}", ok=key in f, detail=""))
    return v


def extract_document(path: Path, name: str | None = None, llm=None) -> tuple[DocResult, list]:
    """Returns (result, pages). `llm` is an optional callable used for the validation-failure fallback."""
    t0 = time.time()
    name = name or path.name
    pages = read_document(path)
    text = full_text(pages)
    lang = detect_language(text)
    source = "ocr" if any(p.source == "ocr" for p in pages) else "text_layer"
    ocr_conf = sum(p.mean_conf for p in pages) / max(len(pages), 1)
    doc_type, scores = classify(pages)
    fields: dict[str, FieldOut] = {}
    txs: list[TxOut] = []
    methods = {"classifier": scores, "path": "rules"}
    validations: list[dict] = []
    if doc_type == "statement":
        fields = parse_header(pages, name)
        opening = float(fields["opening"].value) if "opening" in fields else None
        txs, stats = parse_transactions(pages, opening, name,
                                        fields["period_start"].value if "period_start" in fields else None)
        validations = validate_statement(fields, txs, stats)
        methods["stats"] = stats
    elif doc_type == "declaration":
        fields = parse_declaration(pages, name)
        validations = validate_declaration(fields)
    elif doc_type == "registration":
        fields = parse_registration(pages, name)
        validations = [dict(rule=f"has_{k}", ok=k in fields, detail="") for k in ("org_name", "tin", "reg_date")]
    failed = [x for x in validations if not x["ok"]]
    llm_used = False
    if llm is not None and (doc_type == "unknown" or failed):
        res = llm(doc_type, pages, fields, txs, validations)
        if res is not None:
            doc_type, fields, txs, validations, extra = res
            methods["path"] = "rules+llm"
            methods.update(extra)
            llm_used = True
    for f in fields.values():
        f.doc = name
    res = DocResult(doc_type=doc_type, lang=lang, source=source, pages=len(pages), ocr_conf=round(ocr_conf, 1),
                    fields=list(fields.values()), transactions=txs, validations=validations, methods=methods,
                    seconds=round(time.time() - t0, 2), llm_used=llm_used)
    return res, pages
