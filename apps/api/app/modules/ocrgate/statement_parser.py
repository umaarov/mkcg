"""Deterministic bank-statement parser with balance-chain repair.

Column positions are never used: each record is a date-led block of lines, the last amount is the
running balance, and the direction/size of the movement is resolved from the balance delta. That makes
the parser layout-agnostic and lets it repair OCR digit errors (see `repaired` flag).
"""
from __future__ import annotations

import re

from ..statement.categorize import categorize, infer_direction
from .common import (AMT_RE, DATE_RE, FieldOut, TIN_RE, TxOut, best_label, norm_text, parse_amount, parse_date)
from .text import Line, Page

LABELS = {
    "holder": ["Hisob egasi", "Ҳисоб эгаси", "Владелец счёта", "Владелец счета"],
    "tin": ["STIR", "СТИР", "ИНН"],
    "account": ["Hisob raqami", "Ҳисоб рақами", "Номер счёта", "Номер счета"],
    "period": ["Davr", "Давр", "Период"],
    "opening": ["Davr boshiga qoldiq", "Давр бошига қолдиқ", "Остаток на начало периода"],
    "closing": ["Davr oxiriga qoldiq", "Давр охирига қолдиқ", "Остаток на конец периода"],
}
CP_RE = re.compile(r"(?P<name>.+?)\W{0,3}(?:STIR|СТИР|ИНН)\W{0,3}(?P<tin>\d{9})\W*(?P<purpose>.*)$", re.I)
FOOTER_RE = re.compile(r"^\s*\d{1,3}\s*/\s*\d{1,3}\s*$")
ROW_START = re.compile(r"^\W{0,2}(\d{2}[./-]\d{2}[./-]\d{4}|\d{2}[./]\d{2}[./]\d{2}(?!\d)|\d{4}-\d{2}-\d{2})")
# OCR-tolerant: digits may be read as O/o/l/I/| and separators may be dropped
FUZZY_DATE = re.compile(r"^\W{0,2}([\dOoОоlI|]{2}[./\-]?[\dOoОоlI|]{2}[./\-]?[\dOoОоlI|]{4}|[\dOoОоlI|]{10}|[\dOoОоlI|]{4}-[\dOoОоlI|]{2}-[\dOoОоlI|]{2})(?=\s)")
_DIGITMAP = str.maketrans({"O": "0", "o": "0", "О": "0", "о": "0", "l": "1", "I": "1", "|": "1"})


def _fuzzy_iso(token: str) -> str | None:
    t = token.translate(_DIGITMAP)
    if re.fullmatch(r"\d{10}", t):  # separators were read as digits: dd?mm?yyyy
        t = t[:2] + t[3:5] + t[6:]
    d = re.sub(r"[./\-]", "", t)
    if not d.isdigit() or len(d) != 8:
        return None
    if token.count("-") == 2 or (len(token) >= 4 and token[:4].translate(_DIGITMAP).isdigit() and int(d[:4]) > 1990):
        y, m, dd = d[:4], d[4:6], d[6:]
    else:
        dd, m, y = d[:2], d[2:4], d[4:]
    if not (1 <= int(m) <= 12 and 1 <= int(dd) <= 31 and 2000 <= int(y) <= 2100):
        return None
    return f"{y}-{m}-{dd}"


def _mask_dates(t: str) -> str:
    return DATE_RE.sub(lambda m: " " * len(m.group(0)), t)


def is_row_start(line: Line) -> bool:
    t = line.text
    if ROW_START.match(t) or FUZZY_DATE.match(t):
        return True
    # date unreadable: a line that ends with a movement + balance is still a row
    return len(AMT_RE.findall(_mask_dates(t))) >= 2


def _split_label(text: str) -> tuple[str, str] | None:
    if ":" not in text:
        return None
    left, right = text.split(":", 1)
    return left.strip(), right.strip()


def parse_header(pages: list[Page], doc: str) -> dict[str, FieldOut]:
    out: dict[str, FieldOut] = {}
    first = pages[0]
    # bank from the title line
    if first.lines:
        title = first.lines[0]
        if "|" in title.text:
            bank = title.text.split("|")[0].strip()
            out["bank"] = FieldOut("bank", bank, 0.9 * min(1, title.conf / 100 + 0.2), doc, 0, title.bbox)
    for line in first.lines[:22]:
        sp = _split_label(line.text)
        if not sp:
            continue
        key, score = best_label(sp[0], LABELS)
        if not key:
            continue
        conf = min(1.0, score) * min(1.0, 0.55 + line.conf / 200)
        val = sp[1]
        if key == "holder" and "holder" not in out:
            out["holder"] = FieldOut("holder", val, conf, doc, 0, line.bbox)
        elif key == "tin" and "tin" not in out:
            m = TIN_RE.search(val)
            if m:
                out["tin"] = FieldOut("tin", m.group(0), conf, doc, 0, line.bbox)
        elif key == "account" and "account" not in out:
            digits = re.sub(r"\D", "", val)
            if len(digits) == 20:
                out["account"] = FieldOut("account", digits, conf, doc, 0, line.bbox)
            elif digits:
                out["account"] = FieldOut("account", digits, conf * 0.5, doc, 0, line.bbox, note="expected 20 digits")
        elif key == "period" and "period_start" not in out:
            ds = [parse_date(m.group(0)) for m in DATE_RE.finditer(val)]
            if len(ds) >= 2 and all(ds[:2]):
                out["period_start"] = FieldOut("period_start", ds[0], conf, doc, 0, line.bbox)
                out["period_end"] = FieldOut("period_end", ds[1], conf, doc, 0, line.bbox)
        elif key in ("opening", "closing"):
            m = AMT_RE.search(val)
            if m:
                out[key] = FieldOut(key, parse_amount(m.group(2)), conf, doc, 0, line.bbox)
    # closing balance sits on the last page
    for line in reversed(pages[-1].lines[-6:]):
        sp = _split_label(line.text)
        if sp:
            key, score = best_label(sp[0], {"closing": LABELS["closing"]})
            if key:
                m = AMT_RE.search(sp[1])
                if m:
                    out["closing"] = FieldOut("closing", parse_amount(m.group(2)),
                                              min(1.0, score) * min(1.0, 0.55 + line.conf / 200), doc,
                                              pages[-1].index, line.bbox)
                    break
    return out


def _records(pages: list[Page]):
    """Yield (page_index, [lines]) per date-led record."""
    cur: list[Line] | None = None
    cur_page = 0
    for p in pages:
        if cur:  # records never span pages (page headers would be glued on otherwise)
            yield cur_page, cur
            cur = None
        for line in p.lines:
            t = line.text
            if FOOTER_RE.match(t):
                continue
            if is_row_start(line):
                if cur:
                    yield cur_page, cur
                cur, cur_page = [line], p.index
            elif cur is not None:
                low = norm_text(t)
                if ":" in t and best_label(t.split(":", 1)[0], {"closing": LABELS["closing"]})[0]:
                    yield cur_page, cur
                    cur = None
                    continue
                if re.search(r"kontragent|корреспондент|ҳужжат|hujjat|документ", low) and not AMT_RE.search(t):
                    continue  # repeated table header on a new page
                cur.append(line)
    if cur:
        yield cur_page, cur


def parse_transactions(pages: list[Page], opening: float | None, doc: str,
                       default_date: str | None = None) -> tuple[list[TxOut], dict]:
    raw = []
    last_date = default_date
    for page_idx, lines in _records(pages):
        text = "  ".join(l.text for l in lines)
        m = ROW_START.match(text)
        date, flags0 = None, []
        if m:
            date, rest = parse_date(m.group(1)), text[m.end():]
        else:
            fm = FUZZY_DATE.match(text)
            if fm:
                date, rest = _fuzzy_iso(fm.group(1)), text[fm.end():]
                flags0.append("date_ocr_repaired")
            else:
                rest = text
        if not date:
            date = last_date
            flags0.append("date_inferred")
        rest = _mask_dates(rest)
        amts = [(mm.group(1) or "", parse_amount(mm.group(2)), mm.span()) for mm in AMT_RE.finditer(rest)]
        if not date or len(amts) < 2:  # a row needs a movement and a balance
            raw.append(dict(ok=False, text=text, page=page_idx, lines=lines))
            continue
        last_date = date
        # strip amounts out of the text to get doc no + description
        desc_txt = rest
        for _, _, (a, b) in reversed(amts):
            desc_txt = desc_txt[:a] + " " + desc_txt[b:]
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()
        dm = re.match(r"^(\d{1,7})\s+(.*)$", desc_txt)
        doc_no, desc = (dm.group(1), dm.group(2)) if dm else ("", desc_txt)
        balance = amts[-1][1]
        cands = [(s, v) for s, v, _ in amts[:-1]]
        bbox = [min(l.x0 for l in lines), min(l.y0 for l in lines), max(l.x1 for l in lines), max(l.y1 for l in lines)]
        conf = min(l.conf for l in lines) / 100.0
        raw.append(dict(ok=True, date=date, doc_no=doc_no, desc=desc, balance=balance, cands=cands, page=page_idx,
                        bbox=bbox, conf=conf, flags0=flags0))

    txs: list[TxOut] = []
    stats = dict(rows=0, repaired=0, unparsed=0, chain_breaks=0)  # unparsed = date-led blocks without movement+balance
    prev = opening
    oks = [r for r in raw if r["ok"]]
    for i, r in enumerate(raw):
        if not r["ok"]:
            stats["unparsed"] += 1
            continue
        flags: list[str] = list(r.get("flags0", []))
        bal = r["balance"]
        cands = r["cands"]
        nxt = next((x for x in raw[i + 1:] if x["ok"]), None)

        def fits_next(b: float) -> bool:
            if not nxt:
                return True
            return any(_amt_match(c, abs(nxt["balance"] - b)) for _, c in nxt["cands"] if c)

        debit = credit = 0.0
        resolved = False
        if prev is not None:
            delta = bal - prev
            match = [c for _, c in cands if c and _amt_match(c, abs(delta))]
            if match:
                resolved = True
                debit, credit = (0.0, abs(delta)) if delta > 0 else (abs(delta), 0.0)
            else:
                # chain mismatch: either the amount or the balance is misread
                nz = [(s, c) for s, c in cands if c]
                if nz:
                    sign, amt = nz[0]
                    cr = _direction(sign, r["desc"], delta)
                    if fits_next(bal) and abs(delta) > 0:
                        # balance is consistent with the next row => the amount was misread: trust the chain
                        debit, credit = (0.0, abs(delta)) if delta > 0 else (abs(delta), 0.0)
                        flags.append("amount_repaired_from_balance")
                        stats["repaired"] += 1
                    else:
                        amt_ = amt
                        debit, credit = (0.0, amt_) if cr else (amt_, 0.0)
                        bal = prev + (amt_ if cr else -amt_)
                        flags.append("balance_repaired_from_amount")
                        stats["repaired"] += 1
                    stats["chain_breaks"] += 1
                else:
                    debit, credit = (0.0, abs(delta)) if delta > 0 else (abs(delta), 0.0)
                    flags.append("amount_missing")
                    stats["chain_breaks"] += 1
        else:
            nz = [(s, c) for s, c in cands if c]
            if nz:
                sign, amt = nz[0]
                cr = _direction(sign, r["desc"], None)
                debit, credit = (0.0, amt) if cr else (amt, 0.0)
                flags.append("no_opening_balance_direction_guessed")
        prev = bal
        m = CP_RE.match(r["desc"])
        if m:
            cp_name, cp_tin, purpose = m.group("name").strip(" ,;("), m.group("tin"), m.group("purpose")
        else:
            cp_name, cp_tin, purpose = "", "", r["desc"]
        conf = r["conf"] if resolved else min(r["conf"], 0.6)
        txs.append(TxOut(idx=len(txs), date=r["date"], doc_no=r["doc_no"], desc=r["desc"], cp_name=cp_name,
                         cp_tin=cp_tin, debit=debit, credit=credit, balance=bal,
                         category=categorize(purpose or r["desc"], credit > 0), conf=round(conf, 3),
                         page=r["page"], bbox=r["bbox"], flags=flags))
    _fix_dates(txs, None)
    stats["rows"] = len(txs)
    return txs, stats


def _amt_match(c: float, target: float) -> bool:
    """Amounts agree, tolerating one junk glyph glued to the front (OCR often reads '+' as '4' or '1')."""
    if abs(c - target) <= 1.0:
        return True
    ci, ti = str(int(round(c))), str(int(round(target)))
    return target >= 1000 and len(ci) == len(ti) + 1 and ci.endswith(ti)


def _fix_dates(txs: list[TxOut], period_end: str | None) -> None:
    """Dates are non-decreasing in a statement: repair isolated outliers, interpolate unreadable runs."""
    from datetime import date as _d
    n = len(txs)
    for i in range(1, n - 1):
        a, b, c = txs[i - 1].date, txs[i].date, txs[i + 1].date
        if "date_inferred" not in txs[i].flags and not (a <= b <= c) and a <= c:
            txs[i].date = a
            txs[i].flags.append("date_monotone_repaired")
    i = 0
    while i < n:
        if "date_inferred" in txs[i].flags:
            j = i
            while j < n and "date_inferred" in txs[j].flags:
                j += 1
            d0 = _d.fromisoformat(txs[i - 1].date) if i > 0 else None
            end = txs[j].date if j < n else (period_end or txs[i - 1].date if i > 0 else None)
            d1 = _d.fromisoformat(end) if end else d0
            if d0 and d1 and d1 >= d0:
                span = (d1 - d0).days
                for k in range(i, j):
                    frac = (k - i + 1) / (j - i + 1)
                    txs[k].date = _d.fromordinal(d0.toordinal() + round(span * frac)).isoformat()
                    txs[k].flags.append("date_interpolated")
            i = j
        else:
            i += 1


def _direction(sign: str, desc: str, delta: float | None) -> bool:
    if sign == "+":
        return True
    if sign in ("-", "−", "–"):
        return False
    if delta is not None and delta != 0:
        return delta > 0
    d = infer_direction(desc)
    return True if d is None else d
