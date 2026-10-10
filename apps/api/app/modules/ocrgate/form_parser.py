"""Key-value parsers for tax declarations and registration extracts, plus document classification."""
from __future__ import annotations

import re

from .common import AMT_RE, DATE_RE, FieldOut, TIN_RE, best_label, norm_text, parse_amount, parse_date
from .text import Page

DECL_LABELS = {
    "taxpayer": ["Soliq to'lovchi", "Солиқ тўловчи", "Налогоплательщик", "Soliq to'lovchining nomi"],
    "tin": ["STIR", "СТИР", "ИНН", "INN"],
    "period": ["Hisobot davri", "Ҳисобот даври", "Отчётный период", "Отчетный период"],
    "employees": ["Xodimlar soni", "Ходимлар сони", "Среднесписочная численность", "Численность работников"],
    "rev_q1": ["1-chorak bo'yicha tushum", "1-чорак бўйича тушум", "Выручка за 1-й квартал", "Выручка за 1 квартал"],
    "rev_q2": ["2-chorak bo'yicha tushum", "2-чорак бўйича тушум", "Выручка за 2-й квартал", "Выручка за 2 квартал"],
    "rev_total": ["Jami tushum", "Жами тушум", "Итого выручка", "Jami aylanma", "Общий оборот", "Итого", "Jami", "Жами"],
    "tax_rate": ["Soliq stavkasi (%)", "Солиқ ставкаси (%)", "Налоговая ставка (%)", "Stavka"],
    "tax_amount": ["Hisoblangan soliq summasi", "Ҳисобланган солиқ суммаси", "Исчисленная сумма налога"],
    "submitted": ["Topshirilgan sana", "Топширилган сана", "Дата подачи"],
}
REG_LABELS = {
    "org_name": ["Tashkilot nomi", "Ташкилот номи", "Наименование", "Nomi"],
    "tin": ["STIR", "СТИР", "ИНН"],
    "reg_date": ["Ro'yxatdan o'tgan sana", "Рўйхатдан ўтган сана", "Дата регистрации"],
    "activity": ["Asosiy faoliyat turi", "Асосий фаолият тури", "Основной вид деятельности"],
    "director": ["Rahbar", "Раҳбар", "Руководитель", "Direktor"],
    "pinfl": ["PINFL", "ПИНФЛ", "JShShIR"],
    "address": ["Manzil", "Манзил", "Адрес"],
    "phone": ["Telefon", "Телефон"],
}

DOC_KEYS = {
    "statement": [r"ko'chirma", r"кўчирма", r"выписка", r"debet|дебет", r"qoldiq|қолдиқ|остаток", r"hisob raqami|ҳисоб рақами|расч[её]тн"],
    "declaration": [r"hisoboti|ҳисоботи|отч[её]т плательщика", r"aylanmadan|айланмадан|налога с оборота", r"tushum|тушум|выручка",
                    r"soliq stavkasi|солиқ ставкаси|налоговая ставка"],
    "registration": [r"davlat ro'yxatidan|давлат рўйхатидан|государственной регистрации", r"ma'lumotnoma|маълумотнома|справка",
                     r"asosiy faoliyat|асосий фаолият|основной вид деятельности", r"pinfl|пинфл"],
}


def classify(pages: list[Page]) -> tuple[str, dict]:
    head = norm_text(" ".join(l.text for l in pages[0].lines[:30]))
    scores = {}
    for kind, pats in DOC_KEYS.items():
        scores[kind] = sum(1 for p in pats if re.search(p, head))
    kind = max(scores, key=scores.get)
    if scores[kind] == 0:
        return "unknown", scores
    # statement is also the only multi-row, date-led doc
    rows = sum(1 for p in pages for l in p.lines if re.match(r"^\s*(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})", l.text))
    if rows >= 8 and kind != "statement":
        return "statement", scores
    return kind, scores


def _kv(pages: list[Page], labels: dict[str, list[str]], doc: str) -> dict[str, FieldOut]:
    out: dict[str, FieldOut] = {}
    for p in pages[:2]:
        for li, line in enumerate(p.lines):
            t = line.text
            amt = list(AMT_RE.finditer(t))
            neighbours = [p.lines[j].text for j in (li + 1, li - 1) if 0 <= j < len(p.lines)]
            if ":" in t:
                left, right = t.split(":", 1)
                if not right.strip() and neighbours:      # OCR put the value on the next line
                    right = neighbours[0]
            elif amt:
                left, right = t[:amt[0].start()], t[amt[0].start():]
            else:
                # decimal-less value (e.g. a rate "4,0" or employee count) following wide gap
                parts = re.split(r"\s{2,}", t.strip())
                if len(parts) >= 2:
                    left, right = parts[0], parts[-1]
                elif neighbours:                          # label alone on its line: value is a neighbour line
                    cand = [n for n in neighbours if not best_label(n.split(":")[0], labels)[0] and re.search(r"\d", n)]
                    if not cand:
                        continue
                    left, right = t, cand[0]
                else:
                    continue
            key, score = best_label(left, labels)
            if not key or key in out:
                continue
            conf = min(1.0, score) * min(1.0, 0.55 + line.conf / 200)
            val: str | float | int | None = right.strip()
            if key in ("rev_q1", "rev_q2", "rev_total", "tax_amount"):
                m = AMT_RE.search(right)
                if not m:
                    continue
                val = parse_amount(m.group(2))
            elif key == "tax_rate":
                m = re.search(r"\d+(?:[.,]\d+)?", right)
                if not m:
                    continue
                val = float(m.group(0).replace(",", "."))
            elif key == "employees":
                m = re.search(r"\d+", right)
                if not m:
                    continue
                val = int(m.group(0))
            elif key == "tin":
                m = TIN_RE.search(right)
                if not m:
                    continue
                val = m.group(0)
            elif key == "pinfl":
                d = re.sub(r"\D", "", right)
                val = d
                if len(d) != 14:
                    conf *= 0.5
            elif key in ("reg_date", "submitted"):
                val = parse_date(right)
                if not val:
                    continue
            elif key == "period":
                ds = [parse_date(m.group(0)) for m in DATE_RE.finditer(right)]
                if len(ds) >= 2 and all(ds[:2]):
                    out["period_start"] = FieldOut("period_start", ds[0], conf, doc, p.index, line.bbox)
                    out["period_end"] = FieldOut("period_end", ds[1], conf, doc, p.index, line.bbox)
                continue
            out[key] = FieldOut(key, val, round(conf, 3), doc, p.index, line.bbox)
    return out


def parse_declaration(pages: list[Page], doc: str):
    f = _kv(pages, DECL_LABELS, doc)
    # arithmetic repair: quarters + total + tax must agree, so one missing/garbled value can be derived
    def v(k):
        return float(f[k].value) if k in f else None

    def put(k, val, conf, note):
        if val <= 0:
            return
        f[k] = FieldOut(k, round(val), conf, doc, 0, None, "derived", note)

    q1, q2, tot, tax, rate = v("rev_q1"), v("rev_q2"), v("rev_total"), v("tax_amount"), v("tax_rate")
    if tot is None and q1 is not None and q2 is not None:
        put("rev_total", q1 + q2, 0.7, "sum of quarters")
    elif q1 is None and tot is not None and q2 is not None:
        put("rev_q1", tot - q2, 0.7, "total minus Q2")
    elif q2 is None and tot is not None and q1 is not None:
        put("rev_q2", tot - q1, 0.7, "total minus Q1")
    elif tot is None and tax is not None and rate:
        put("rev_total", tax / rate * 100, 0.55, "tax amount / rate")
    return f


def parse_registration(pages: list[Page], doc: str):
    return _kv(pages, REG_LABELS, doc)
