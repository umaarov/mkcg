"""Upload API: consent gate, Excel/CSV ingestion end to end, photo (JPG) of an unfamiliar layout."""
from __future__ import annotations

import time

import foreign_layouts as fl
from fastapi.testclient import TestClient

from app.datagen import bundle
from app.datagen.sme import archetype_sme, simulate_statement
from app.main import app
from app.modules.ocrgate.align import align
from app.modules.ocrgate.extract import extract_document


def _wait(c, cid, h, secs=300):
    for _ in range(secs * 2):
        d = c.get(f"/api/cases/{cid}", headers=h).json()
        if d["status"] not in ("UPLOADED", "EXTRACTING", "ANALYZING"):
            return d
        time.sleep(0.5)
    raise AssertionError(f"case {cid} still {d['status']} after {secs}s")


def test_upload_requires_synthetic_confirmation(tmp_path):
    sme = archetype_sme(31, "strong", "ru")
    bundle.build_bundle(sme, 31, tmp_path, layout="B", lang="ru", with_outcome=False)
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/guest").json()["token"]}
        files = [("files", ("statement.pdf", (tmp_path / "statement.pdf").read_bytes(), "application/pdf"))]
        r = c.post("/api/cases", headers=h, files=files, data={"amount": 1e8, "term": 12, "lang": "en"})
        assert r.status_code == 400 and "synthetic" in r.text
        r = c.post("/api/cases", headers=h, files=files, data={"amount": 1e8, "term": 12, "lang": "en", "synthetic_ack": "true"})
        assert r.status_code == 200


def test_excel_statement_goes_through_the_whole_pipeline(tmp_path):
    sme = archetype_sme(32, "strong", "ru")
    truth = bundle.build_bundle(sme, 32, tmp_path, layout="B", lang="ru", with_outcome=False)
    st = dict(opening=truth["statement"]["opening"], closing=truth["statement"]["closing"], rows=truth["statement"]["rows"])
    fl.write_excel(sme, st, "ru", tmp_path / "statement.xlsx")
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/guest").json()["token"]}
        files = [("files", ("statement.xlsx", (tmp_path / "statement.xlsx").read_bytes(), "application/octet-stream")),
                 ("files", ("declaration.pdf", (tmp_path / "declaration.pdf").read_bytes(), "application/pdf")),
                 ("files", ("registration.pdf", (tmp_path / "registration.pdf").read_bytes(), "application/pdf"))]
        cid = c.post("/api/cases", headers=h, files=files, data={"amount": 1e8, "term": 12, "lang": "en", "synthetic_ack": "true"}).json()["id"]
        d = _wait(c, cid, h)
        assert d["status"] == "ANALYZED", d["status"]
        stmt = next(x for x in d["docs"] if x["doc_type"] == "statement")
        assert stmt["filename"] == "statement.xlsx" and stmt["pages"] >= 1
        assert len(stmt["extraction"]["transactions"]) >= len(st["rows"]) - 1
        page = c.get(f"/api/cases/{cid}/docs/{stmt['id']}/page/0.png", headers=h)
        assert page.status_code == 200 and page.content[:4] == b"\x89PNG"
        assert len(d["result"]["rules"]["results"]) == 20


def test_jpeg_photo_of_unfamiliar_layout(tmp_path):
    sme = archetype_sme(33, "strong", "ru")
    st = simulate_statement(sme, 33)
    pdf = tmp_path / "portal.pdf"
    fl.render_portal_pdf(sme, st, "ru", pdf, newest_first=True)
    jpg = tmp_path / "portal.jpg"
    fl.render_portal_png(pdf, jpg, dpi=170, jpeg_quality=60)
    res, _ = extract_document(jpg)
    page1 = st["rows"][-30:]  # newest-first first page holds the last 30 rows
    pairs, *_ = align(res.transactions, page1)
    assert res.doc_type == "statement" and res.source == "ocr"
    assert len(pairs) / len(page1) >= 0.85, f"{len(pairs)}/{len(page1)} rows"
