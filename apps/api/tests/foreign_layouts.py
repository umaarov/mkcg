"""Statement layouts that the product's own generator (app/datagen/render.py) does NOT produce.

Purpose: check that OCRGate is layout-agnostic rather than tuned to layouts A/B/C. Differences on purpose:
  * a running row number and a document number precede the date
  * amounts as 1.234.567,00 (dot thousands, comma decimals)
  * purposes wrap onto a second line
  * newest transaction first, closing balance printed above the table
  * a totals line, repeated table headers, different wording of the header labels
  * the same data as an Excel export
"""
from __future__ import annotations

import textwrap
from datetime import date, datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.datagen import names
from app.datagen.render import _desc, _fonts


def _eu(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", ".") + ",00"


def _dmy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def render_portal_pdf(sme, stmt: dict, lang: str, path: Path, newest_first: bool = True, per_page: int = 30) -> None:
    """Online-banking style export: № | doc | date | purpose (2 lines) | debit | credit | balance."""
    _fonts()
    rows = list(stmt["rows"])
    order = list(range(len(rows)))
    if newest_first:
        order.reverse()
    p0, p1 = rows[0]["date"], rows[-1]["date"]
    W, H = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(W, H))
    pages = [order[i:i + per_page] for i in range(0, len(order), per_page)]
    for pi, chunk in enumerate(pages):
        y = H - 40
        c.setFont("DVB", 12)
        c.drawString(30, y, "Выписка по лицевому счёту"); y -= 20
        c.setFont("DV", 8)
        if pi == 0:
            for line in (f"Клиент: {names.fmt_company(sme.core_name, sme.form, 'ru')}", f"ИНН: {sme.tin}",
                         f"Расчётный счёт: {sme.account}", f"Период: с {_dmy(p0)} по {_dmy(p1)}",
                         f"Исходящий остаток: {_eu(stmt['closing'])} сум", f"Входящий остаток: {_eu(stmt['opening'])} сум"):
                c.drawString(30, y, line); y -= 12
            y -= 6
        c.setFont("DVB", 7)
        for x, label in ((30, "№"), (52, "Док."), (100, "Дата"), (170, "Назначение платежа"), (560, "Дебет"), (650, "Кредит"), (745, "Остаток")):
            c.drawString(x, y, label)
        y -= 11
        c.setFont("DV", 7)
        for k in chunk:
            r = rows[k]
            desc = textwrap.wrap(_desc(r, "ru"), 78) or [""]
            c.drawString(30, y, str(k + 1))
            c.drawString(52, y, str(r["n"]) if "n" in r else str(1000 + k))
            c.drawString(100, y, _dmy(r["date"]))
            c.drawString(170, y, desc[0])
            if r["debit"]:
                c.drawRightString(610, y, _eu(r["debit"]))
            if r["credit"]:
                c.drawRightString(700, y, _eu(r["credit"]))
            c.drawRightString(795, y, _eu(r["balance"]))
            y -= 9
            for extra in desc[1:2]:
                c.drawString(170, y, extra); y -= 9
            y -= 2
        if pi == len(pages) - 1:
            y -= 4
            c.setFont("DVB", 7)
            c.drawString(170, y, "Итого обороты за период:")
            c.drawRightString(610, y, _eu(sum(r["debit"] for r in rows)))
            c.drawRightString(700, y, _eu(sum(r["credit"] for r in rows)))
        c.setFont("DV", 7)
        c.drawString(W / 2 - 20, 20, f"{pi + 1} / {len(pages)}")
        c.showPage()
    c.save()


def render_portal_png(pdf: Path, png: Path, dpi: int = 130, jpeg_quality: int | None = None) -> None:
    """Rasterise page 1..n of a PDF into one PNG/JPG per page-stacked image is not needed: we keep page 1 only."""
    import pymupdf
    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap(dpi=dpi)
    if jpeg_quality:
        pix.save(str(png), jpg_quality=jpeg_quality)
    else:
        pix.save(str(png))


def write_excel(sme, stmt: dict, lang: str, path: Path) -> None:
    """Typical accounting-system export: header block, then a table with real dates and numeric cells."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Выписка"
    p0, p1 = stmt["rows"][0]["date"], stmt["rows"][-1]["date"]
    ws.append(["Выписка по счёту"])
    ws.append(["Клиент:", names.fmt_company(sme.core_name, sme.form, "ru")])
    ws.append(["ИНН:", sme.tin])
    ws.append(["Расчётный счёт:", sme.account])
    ws.append(["Период:", f"с {_dmy(p0)} по {_dmy(p1)}"])
    ws.append(["Входящий остаток:", float(stmt["opening"])])
    ws.append(["Исходящий остаток:", float(stmt["closing"])])
    ws.append([])
    ws.append(["Дата", "№ док.", "Назначение платежа", "Дебет", "Кредит", "Остаток"])
    for i, r in enumerate(stmt["rows"]):
        d = datetime.fromisoformat(r["date"])
        ws.append([d, 2000 + i, _desc(r, "ru"), float(r["debit"]) or None, float(r["credit"]) or None, float(r["balance"])])
    ws.append([None, None, "Итого обороты:", float(sum(r["debit"] for r in stmt["rows"])), float(sum(r["credit"] for r in stmt["rows"])), None])
    for row in ws.iter_rows(min_row=10):
        row[0].number_format = "DD.MM.YYYY"
        for cell in row[3:6]:
            cell.number_format = "#,##0.00"
    wb.save(path)
