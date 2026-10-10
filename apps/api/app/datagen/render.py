"""Render synthetic statements / declarations / registration extracts to PDF with ground truth.

Layouts are *approximations* of what bank and tax documents in Uzbekistan look like. They are
not copies of any real institution's template.
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import names
from .sme import SME, MONTHS, month_start

FONT_DIR = Path(__file__).parent / "fonts"
_registered = False


def _fonts():
    global _registered
    if not _registered:
        for name, f in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf"), ("DVS", "DejaVuSerif.ttf"),
                        ("DVM", "DejaVuSansMono.ttf")):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f)))
        _registered = True


def fmt_amount(n: int | float, style: str) -> str:
    n = int(round(n))
    if style == "space_comma":          # 12 345 678,00
        return f"{n:,}".replace(",", " ") + ",00"
    if style == "comma_dot":            # 12,345,678.00
        return f"{n:,}.00"
    if style == "nbsp_comma":           # 12 345 678,00 with NBSP
        return f"{n:,}".replace(",", " ") + ",00"
    raise ValueError(style)


def fmt_date(iso: str, style: str) -> str:
    y, m, d = iso.split("-")
    return {"dmy_dot": f"{d}.{m}.{y}", "dmy_slash": f"{d}/{m}/{y}", "iso": iso}[style]


LAYOUTS = {
    "A": dict(date="dmy_dot", amount="space_comma", blank_zero=True, signed=False, mono=False),
    "B": dict(date="dmy_slash", amount="comma_dot", blank_zero=False, signed=False, mono=False),
    "C": dict(date="iso", amount="nbsp_comma", blank_zero=False, signed=True, mono=True),
}


def _desc(row: dict, lang: str) -> str:
    texts = names.PURPOSE[row["category"]][lang]
    purpose = texts[int(row["purpose_n"]) % len(texts)].format(n=row["purpose_n"])
    if row["cp_tin"]:
        cp = names.fmt_company(row["cp_core"], row["cp_form"], lang)
        return f"{cp} ({names.L('tin', lang)} {row['cp_tin']}) {purpose}"
    return purpose


def _grp(acc: str) -> str:
    return " ".join(acc[i:i + 4] for i in range(0, 20, 4))


def render_statement(sme: SME, stmt: dict, lang: str, layout: str, path: Path) -> dict:
    """Write a bank statement PDF. Returns metadata incl. the printed text of each row."""
    _fonts()
    cfg = LAYOUTS[layout]
    landscape_mode = layout in ("A", "B")
    pw, ph = landscape(A4) if landscape_mode else A4
    c = canvas.Canvas(str(path), pagesize=(pw, ph))
    font = "DVM" if cfg["mono"] else "DV"
    fs = 6.4 if landscape_mode else 6.8
    rh = 11.0
    holder = names.fmt_company(sme.core_name, sme.form, lang)
    start = month_start(0).isoformat()
    end = date(month_start(MONTHS - 1).year, month_start(MONTHS - 1).month, 28).isoformat()
    end = _month_end(month_start(MONTHS - 1)).isoformat()
    period = f"{fmt_date(start, cfg['date'])} - {fmt_date(end, cfg['date'])}"
    left = 28
    rows = stmt["rows"]
    printed = []

    def header(page_no: int, total: int):
        y = ph - 34
        c.setFont("DVB", 9.5)
        c.drawString(left, y, f"{sme.bank}  |  {names.L('stmt_title', lang)}")
        c.setFont("DV", 7.2)
        y -= 16
        for lab, val in ((names.L("holder", lang), holder), (names.L("tin", lang), sme.tin),
                         (names.L("account", lang), _grp(sme.account)), (names.L("period", lang), period)):
            c.drawString(left, y, f"{lab}: {val}")
            y -= 10.5
        if page_no == 1:
            c.drawString(left, y, f"{names.L('opening', lang)}: {fmt_amount(stmt['opening'], cfg['amount'])} {names.L('currency', lang)}")
            y -= 12
        c.setFont("DVB", 6.8)
        cols = _cols(layout, pw)
        c.drawString(cols["date"], y, names.L("col_date", lang))
        c.drawString(cols["doc"], y, names.L("col_doc", lang))
        c.drawString(cols.get("hdesc", cols["desc"]), y, names.L("col_cp", lang))
        if cfg["signed"]:
            c.drawRightString(cols["amt"], y, "+/-")
        else:
            c.drawRightString(cols["debit"], y, names.L("col_debit", lang))
            c.drawRightString(cols["credit"], y, names.L("col_credit", lang))
        c.drawRightString(cols["bal"], y, names.L("col_balance", lang))
        c.line(left, y - 3, pw - left, y - 3)
        c.setFont(font, fs)
        c.drawRightString(pw - left, 18, f"{page_no}/{total}")
        return y - 14

    per_page = int((ph - 150) / (rh * (2 if layout == "C" else 1)))
    total_pages = max(1, -(-len(rows) // per_page))
    idx = 0
    for page in range(1, total_pages + 1):
        y = header(page, total_pages)
        c.setFont(font, fs)
        cols = _cols(layout, pw)
        for _ in range(per_page):
            if idx >= len(rows):
                break
            r = rows[idx]
            idx += 1
            d = fmt_date(r["date"], cfg["date"])
            desc = _desc(r, lang)
            c.drawString(cols["date"], y, d)
            c.drawString(cols["doc"], y, r["doc_no"])
            if cfg["signed"]:
                sign = "+" if r["credit"] else "-"
                amt = r["credit"] or r["debit"]
                c.drawRightString(cols["amt"], y, f"{sign}{fmt_amount(amt, cfg['amount'])}")
                c.drawRightString(cols["bal"], y, fmt_amount(r["balance"], cfg["amount"]))
                y -= rh
                c.drawString(cols["desc"], y, desc)
                y -= rh
            else:
                c.drawString(cols["desc"], y, desc[:112])
                dv = fmt_amount(r["debit"], cfg["amount"]) if r["debit"] or not cfg["blank_zero"] else ""
                cv = fmt_amount(r["credit"], cfg["amount"]) if r["credit"] or not cfg["blank_zero"] else ""
                c.drawRightString(cols["debit"], y, dv)
                c.drawRightString(cols["credit"], y, cv)
                c.drawRightString(cols["bal"], y, fmt_amount(r["balance"], cfg["amount"]))
                y -= rh
            printed.append(desc)
        if page == total_pages:
            y -= 6
            c.setFont("DVB", 7.2)
            c.drawString(left, y, f"{names.L('closing', lang)}: {fmt_amount(stmt['closing'], cfg['amount'])} {names.L('currency', lang)}")
        c.showPage()
    c.save()
    return dict(period_start=start, period_end=end, printed_desc=printed, pages=total_pages)


def _month_end(d0: date) -> date:
    nxt = date(d0.year + (d0.month // 12), d0.month % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def _cols(layout: str, pw: float) -> dict:
    if layout in ("A", "B"):
        return dict(date=28, doc=84, desc=122, debit=pw - 28 - 190, credit=pw - 28 - 95, bal=pw - 28)
    return dict(date=28, doc=96, desc=36, hdesc=150, amt=pw - 140, bal=pw - 28)


# ---------------------------------------------------------------------------------------
def render_declaration(sme: SME, decl: dict, lang: str, variant: int, path: Path) -> dict:
    _fonts()
    pw, ph = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    style = "space_comma" if variant == 0 else "comma_dot"
    holder = names.fmt_company(sme.core_name, sme.form, lang)
    y = ph - 56
    c.setFont("DVB", 10.5)
    for i, line in enumerate(_wrap(names.L("decl_title", lang), 62)):
        c.drawString(46, y - i * 14, line)
    y -= 14 * (i + 1) + 8
    c.setFont("DV", 9)
    rows = [
        (names.L("taxpayer", lang), holder),
        (names.L("tin", lang), sme.tin),
        (names.L("decl_period", lang), f"{fmt_date(month_start(0).isoformat(), 'dmy_dot')} - {fmt_date(_month_end(month_start(MONTHS - 1)).isoformat(), 'dmy_dot')}"),
        (names.L("employees", lang), str(decl["employees"])),
    ]
    for lab, val in rows:
        c.drawString(46, y, f"{lab}:")
        c.drawString(250, y, val)
        y -= 17
    y -= 8
    c.line(46, y + 6, pw - 46, y + 6)
    money = [("rev_q1", decl["rev_q1"]), ("rev_q2", decl["rev_q2"]), ("rev_total", decl["rev_total"]),
             ("tax_rate", None), ("tax_amount", decl["tax_amount"])]
    for key, val in money:
        c.setFont("DVB" if key == "rev_total" else "DV", 9)
        c.drawString(46, y, names.L(key, lang))
        if key == "tax_rate":
            c.drawRightString(pw - 46, y, f"{decl['tax_rate']:.1f}".replace(".", "," if variant == 0 else "."))
        else:
            c.drawRightString(pw - 46, y, f"{fmt_amount(val, style)} {names.L('currency', lang)}")
        y -= 18
    y -= 14
    c.setFont("DV", 8.5)
    c.drawString(46, y, f"{names.L('submitted', lang)}: {fmt_date(decl['submitted'], 'dmy_dot')}")
    c.showPage()
    c.save()
    return dict(pages=1)


def render_registration(sme: SME, lang: str, path: Path) -> dict:
    _fonts()
    pw, ph = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    holder = names.fmt_company(sme.core_name, sme.form, lang)
    y = ph - 56
    c.setFont("DVS", 10.5)
    for i, line in enumerate(_wrap(names.L("reg_title", lang), 58)):
        c.drawString(46, y - i * 14, line)
    y -= 14 * (i + 1) + 10
    c.setFont("DVS", 9.2)
    region = sme.region if lang == "uz" else names.REGION_CYR.get(sme.region, names.to_cyr(sme.region, "ru" if lang == "ru" else "uzc"))
    rows = [
        (names.L("org_name", lang), holder),
        (names.L("tin", lang), sme.tin),
        (names.L("reg_date", lang), fmt_date(sme.reg_date.isoformat(), "dmy_dot")),
        (names.L("activity", lang), names.SECTOR_LABEL[sme.sector][lang]),
        (names.L("director", lang), names.display(sme.owner, lang)),
        ("PINFL" if lang == "uz" else ("ПИНФЛ"), sme.pinfl),
        (names.L("address", lang), f"{region}, {names.display('Mustaqillik koʻchasi', lang) if lang != 'uz' else 'Mustaqillik koʻchasi'} {sme.employees + 3}"),
        (names.L("phone", lang), sme.phone),
    ]
    for lab, val in rows:
        c.drawString(46, y, f"{lab}:")
        c.drawString(230, y, val)
        y -= 18
    c.showPage()
    c.save()
    return dict(pages=1)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
