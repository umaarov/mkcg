"""Layout-agnosticism: statements in layouts the generator never produced must still be read from the balance chain."""
from __future__ import annotations

import pytest

from app.datagen.sme import archetype_sme, simulate_statement
from app.modules.ocrgate.align import align
from app.modules.ocrgate.extract import extract_document

import foreign_layouts as fl


@pytest.fixture(scope="module")
def stmt():
    sme = archetype_sme(21, "strong", "ru")
    return sme, simulate_statement(sme, 21)


def _score(res, truth_rows):
    pairs, *_ = align(res.transactions, truth_rows)
    return len(pairs) / len(truth_rows), len(res.transactions)


@pytest.mark.parametrize("newest_first", [True, False])
def test_portal_pdf_rows_recovered(tmp_path, stmt, newest_first):
    sme, st = stmt
    p = tmp_path / "portal.pdf"
    fl.render_portal_pdf(sme, st, "ru", p, newest_first=newest_first)
    res, _ = extract_document(p)
    recall, n = _score(res, st["rows"])
    assert res.doc_type == "statement"
    assert recall >= 0.98, f"recall {recall:.3f}, parsed {n} of {len(st['rows'])}"
    assert n <= len(st["rows"]) + 1, "a totals line must not become a transaction"
    dates = [t.date for t in res.transactions]
    assert dates == sorted(dates), "rows must come out in chronological order"
    byname = {f.key: f.value for f in res.fields}
    assert byname.get("tin") == sme.tin
    assert round(float(byname["opening"])) == round(st["opening"]) and round(float(byname["closing"])) == round(st["closing"])
    assert all(v["ok"] for v in res.validations if v["rule"] in ("balance_identity", "rows_chain_consistent")), res.validations


def test_excel_export_is_read_like_a_pdf(tmp_path, stmt):
    from app.modules.ocrgate.sheets import sheet_to_pdf
    sme, st = stmt
    x = tmp_path / "export.xlsx"
    fl.write_excel(sme, st, "ru", x)
    pdf = sheet_to_pdf(x)
    res, pages = extract_document(pdf, "export.xlsx")
    recall, n = _score(res, st["rows"])
    assert res.doc_type == "statement" and res.source == "text_layer"
    assert recall >= 0.98, f"recall {recall:.3f}, parsed {n} of {len(st['rows'])}"
    assert n <= len(st["rows"]) + 1
    byname = {f.key: f.value for f in res.fields}
    assert round(float(byname["opening"])) == round(st["opening"]) and round(float(byname["closing"])) == round(st["closing"])
    assert all(v["ok"] for v in res.validations if v["rule"] in ("balance_identity", "rows_chain_consistent")), res.validations


def test_csv_export_with_semicolons_and_cp1251(tmp_path, stmt):
    from app.modules.ocrgate.sheets import sheet_to_pdf
    sme, st = stmt
    lines = ["Клиент:;ООО Тест", f"ИНН:;{sme.tin}", f"Расчётный счёт:;{sme.account}", f"Период:;с {fl._dmy(st['rows'][0]['date'])} по {fl._dmy(st['rows'][-1]['date'])}",
             f"Входящий остаток:;{fl._eu(st['opening'])}", f"Исходящий остаток:;{fl._eu(st['closing'])}", "", "Дата;Назначение платежа;Дебет;Кредит;Остаток"]
    for r in st["rows"]:
        lines.append(f"{fl._dmy(r['date'])};{fl._desc(r, 'ru')};{fl._eu(r['debit']) if r['debit'] else ''};{fl._eu(r['credit']) if r['credit'] else ''};{fl._eu(r['balance'])}")
    p = tmp_path / "export.csv"
    p.write_bytes("\n".join(lines).encode("cp1251", errors="replace"))
    res, _ = extract_document(sheet_to_pdf(p), "export.csv")
    recall, n = _score(res, st["rows"])
    assert res.doc_type == "statement"
    assert recall >= 0.98, f"recall {recall:.3f}, parsed {n} of {len(st['rows'])}"
