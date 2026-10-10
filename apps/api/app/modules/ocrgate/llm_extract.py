"""LLM fallback for layouts the deterministic parsers do not know. Always PII-masked, always re-validated."""
from __future__ import annotations

from ...config import settings
from ..piimodule.mask import Masker
from ..router import gateway
from ..statement.categorize import categorize
from .common import FieldOut, TxOut, norm_text, parse_amount
from .extract import validate_declaration, validate_statement
from .text import Page

SYSTEM = ("You extract structured data from Uzbek/Russian financial documents (OCR text, may contain errors). "
          "Identifier tokens like [TIN_1] are placeholders: copy them verbatim. Amounts are in UZS. "
          "Answer with JSON only, no commentary. Use null when a value is absent; never guess.")

SCHEMAS = {
    "statement_header": '{"holder": str, "tin": str, "account": str, "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "opening": number, "closing": number}',
    "statement_rows": '[{"date": "YYYY-MM-DD", "doc_no": str, "counterparty": str|null, "counterparty_tin": str|null, "purpose": str, "debit": number, "credit": number, "balance": number}]',
    "declaration": '{"taxpayer": str, "tin": str, "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "rev_q1": number, "rev_q2": number, "rev_total": number, "tax_rate": number, "tax_amount": number, "employees": integer}',
    "registration": '{"org_name": str, "tin": str, "reg_date": "YYYY-MM-DD", "activity": str, "director": str, "pinfl": str, "address": str, "phone": str}',
    "classify": '{"doc_type": "statement"|"declaration"|"registration"|"unknown"}',
}


def _locate(pages: list[Page], value: str) -> tuple[int, list[float] | None]:
    v = norm_text(str(value))
    if not v:
        return 0, None
    for p in pages:
        for l in p.lines:
            if v in norm_text(l.text):
                return p.index, l.bbox
    return 0, None


def _ask(purpose: str, schema: str, text: str, masker: Masker):
    user = f"Extract this schema:\n{schema}\n\nDocument text:\n{masker.mask(text)}"
    res = gateway.complete(purpose, SYSTEM, user, masked=True, model=None, max_tokens=4000, want_json=True)
    return res.json


def _unmask(masker: Masker, v):
    return masker.unmask(v) if isinstance(v, str) else v


def llm_fallback(doc_type: str, pages: list[Page], fields: dict[str, FieldOut], txs: list[TxOut], validations: list[dict]):
    if not gateway.available():
        return None
    mk = Masker()
    all_lines = [l.text for p in pages for l in p.lines]
    text = "\n".join(all_lines)
    extra = {"llm_calls": 0}
    try:
        if doc_type == "unknown":
            r = _ask("classify", SCHEMAS["classify"], text[:3000], mk)
            extra["llm_calls"] += 1
            doc_type = (r or {}).get("doc_type", "unknown")
            if doc_type == "unknown":
                return doc_type, fields, txs, validations, extra
        if doc_type == "statement":
            head = "\n".join(all_lines[:25] + all_lines[-6:])
            r = _ask("statement_header", SCHEMAS["statement_header"], head, mk)
            extra["llm_calls"] += 1
            for k, v in (r or {}).items():
                v = _unmask(mk, v)
                if v is None or k in fields:
                    continue
                pg, bb = _locate(pages, v)
                fields[k] = FieldOut(k, parse_amount(str(v)) if k in ("opening", "closing") and isinstance(v, str) else v,
                                     0.75, "", pg, bb, "llm")
            structured_ok = len(txs) >= 5 and not any(x["rule"] == "rows_chain_consistent" and not x["ok"] for x in validations)
            if not structured_ok and settings.llm_statement_rows:
                new: list[TxOut] = []
                for i in range(0, len(all_lines), 110):
                    chunk = "\n".join(all_lines[i:i + 110])
                    rows = _ask("statement_rows", SCHEMAS["statement_rows"], chunk, mk) or []
                    extra["llm_calls"] += 1
                    for r in rows:
                        try:
                            debit, credit = float(r.get("debit") or 0), float(r.get("credit") or 0)
                            purpose = _unmask(mk, r.get("purpose") or "")
                            new.append(TxOut(idx=len(new), date=r["date"], doc_no=str(r.get("doc_no") or ""),
                                             desc=purpose, cp_name=_unmask(mk, r.get("counterparty") or ""),
                                             cp_tin=_unmask(mk, r.get("counterparty_tin") or "") or "", debit=debit,
                                             credit=credit, balance=float(r.get("balance") or 0),
                                             category=categorize(purpose, credit > 0), conf=0.7, flags=["llm"]))
                        except (KeyError, ValueError, TypeError):
                            continue
                if len(new) > len(txs):
                    txs = new
            stats = dict(rows=len(txs), repaired=0, unparsed=0, chain_breaks=0)
            # chain check on whatever we have
            prev = float(fields["opening"].value) if "opening" in fields else None
            for t in txs:
                if prev is not None and abs(prev + t.credit - t.debit - t.balance) > 2:
                    stats["chain_breaks"] += 1
                prev = t.balance
            validations = validate_statement(fields, txs, stats)
        elif doc_type in ("declaration", "registration"):
            r = _ask(doc_type, SCHEMAS[doc_type], text, mk)
            extra["llm_calls"] += 1
            for k, v in (r or {}).items():
                v = _unmask(mk, v)
                if v is None:
                    continue
                if k in fields and fields[k].conf >= 0.8:
                    continue
                pg, bb = _locate(pages, v)
                fields[k] = FieldOut(k, v, 0.75, "", pg, bb, "llm")
            if doc_type == "declaration":
                validations = validate_declaration(fields)
        return doc_type, fields, txs, validations, extra
    except (gateway.RouterError, Exception) as e:  # noqa: BLE001 - fall back to rule output, record why
        extra["llm_error"] = str(e)[:200]
        return doc_type, fields, txs, validations, extra
