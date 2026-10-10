"""Core behaviour tests. Run: cd apps/api && uv run pytest -q"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.datagen import bundle
from app.datagen.sme import archetype_sme, random_sme, simulate_statement
from app.modules.fgate import chain
from app.modules.formalbrief import memo as memo_mod
from app.modules.formalbrief.facts import Fact
from app.modules.ocrgate.align import align
from app.modules.ocrgate.extract import extract_document
from app.modules.piimodule.mask import Masker, residual_pii
from app.modules.revenuegate.reconcile import reconcile
from app.modules.rulesengine.engine import evaluate
from app.modules.statement.analytics import affordability, compute_metrics
from app.modules.statement.categorize import categorize


@pytest.fixture(scope="module")
def clean_bundle(tmp_path_factory):
    d = tmp_path_factory.mktemp("b")
    sme = archetype_sme(11, "strong", "ru")
    truth = bundle.build_bundle(sme, 11, d, layout="B", lang="ru")
    return d, truth


def test_clean_statement_is_recovered_exactly(clean_bundle):
    d, truth = clean_bundle
    r, _ = extract_document(d / "statement.pdf")
    gt = truth["statement"]["rows"]
    pairs, *_ = align(r.transactions, gt)
    assert len(pairs) == len(gt) == len(r.transactions)
    assert all(v["ok"] for v in r.validations if v["rule"] in ("balance_identity", "rows_chain_consistent"))


@pytest.mark.parametrize("layout,lang", [("A", "uz"), ("B", "ru"), ("C", "uzc")])
def test_all_layouts_and_scripts(tmp_path, layout, lang):
    sme = random_sme(77, "random", lang)
    truth = bundle.build_bundle(sme, 77, tmp_path, layout=layout, lang=lang, with_outcome=False)
    r, _ = extract_document(tmp_path / "statement.pdf")
    pairs, *_ = align(r.transactions, truth["statement"]["rows"])
    assert len(pairs) == len(truth["statement"]["rows"])


def test_balance_chain_repairs_a_corrupted_amount(clean_bundle):
    """Break one amount in the text; the running balance must restore it."""
    from app.modules.ocrgate.statement_parser import parse_transactions
    from app.modules.ocrgate.text import read_document
    d, truth = clean_bundle
    pages = read_document(d / "statement.pdf")
    line = next(l for l in pages[0].lines if l.text[:2].isdigit() and "," in l.text or "." in l.text)
    original = line.text
    # corrupt the first amount-looking token
    import re
    line.text = re.sub(r"(\d)(\d{3}[.,]00)", r"9\2", original, count=1)
    txs, stats = parse_transactions(pages, truth["statement"]["opening"], "x")
    gt = truth["statement"]["rows"]
    assert round(txs[0].credit + txs[0].debit) == gt[0]["credit"] + gt[0]["debit"]


def test_categorizer_uses_direction():
    assert categorize("Оплата по договору №5", True) == "sales_receipt"
    assert categorize("Оплата за поставку товара, счёт-фактура №5", False) == "supplier_payment"
    assert categorize("Kredit boʻyicha toʻlov, shartnoma №4", False) == "loan_payment"
    assert categorize("Ish haqi toʻlovi", False) == "payroll"


def test_circular_inflows_are_flagged():
    sme = archetype_sme(303, "inflated", "uz")
    st = simulate_statement(sme, 303)
    rows = [dict(date=r["date"], debit=r["debit"], credit=r["credit"], balance=r["balance"], category=r["category"], cp_tin=r["cp_tin"]) for r in st["rows"]]
    m = compute_metrics(rows, st["opening"], st["closing"], "2026-04-01", "2026-09-30")
    assert m["roundtrip_share"] > 0.1


def test_reconcile_verdicts():
    m = dict(monthly_inflow=[100.0] * 6, roundtrip_amount=0.0)
    assert reconcile(dict(rev_q1=300, rev_q2=300, rev_total=600), m)["verdict"] == "consistent"
    assert reconcile(dict(rev_q1=500, rev_q2=500, rev_total=1000), m)["verdict"] == "over_declared"
    assert reconcile(dict(rev_q1=100, rev_q2=100, rev_total=200), m)["verdict"] == "under_declared"


def test_rules_hard_fail_dominates():
    ctx = dict(request_amount=50e6, request_term=24, business_age_months=40, active_months=6, dscr=0.8, loan_to_annual_inflow=0.2, top1_share=0.2,
               gap_adj=1.0, roundtrip_share=0.0, inflow_cv=0.1, trend_ratio=1.0, low_balance_days_share=0.0, cashout_ratio=0.05,
               non_operating_in_share=0.0, identity_gap_share=0.0, identity_consistent=True, statement_age_days=10, fields_verified_share=1.0, extraction_quality_issues=0.0)
    assert evaluate(ctx)["recommendation"] == "DECLINE"
    assert evaluate({**ctx, "dscr": 2.0})["recommendation"] == "APPROVE"


def test_pii_masking_round_trip_and_recall(clean_bundle):
    d, truth = clean_bundle
    r, pages = extract_document(d / "registration.pdf")
    from app.modules.ocrgate.text import full_text
    text = full_text(pages)
    m = Masker()
    masked = m.mask(text)
    secrets_ = [truth["applicant"]["tin"], truth["applicant"]["pinfl"], truth["applicant"]["phone"]]
    assert residual_pii(masked, secrets_) == []
    assert m.unmask(masked).replace("\n", " ") == text.replace("\n", " ")


def test_memo_verifier_rejects_invented_numbers():
    facts = [Fact("F01", "dscr", 1.42, "1.42", "x", {"en": "DSCR"})]
    assert memo_mod.verify("The DSCR is 1.42 [F01].", facts)["ok"]
    assert not memo_mod.verify("The DSCR is 1.89 [F01].", facts)["ok"]
    assert not memo_mod.verify("The DSCR is 1.42 and strong.", facts)["ok"]  # numeric sentence without citation


def test_audit_chain_detects_tampering(tmp_path, monkeypatch):
    from app import db
    chain.append("t", "a1", "CASE1", {"x": 1})
    chain.append("t", "a2", "CASE1", {"x": 2})
    assert chain.verify_chain()["ok"]
    with db.session() as s:
        ev = s.query(db.AuditEvent).order_by(db.AuditEvent.id.desc()).first()
        ev.payload = json.dumps({"x": 999})
    assert not chain.verify_chain()["ok"]


def test_dossier_signature_detects_edit():
    signed = chain.sign_dossier({"case_id": "C1", "request": {"amount": 100}})
    assert chain.verify_signed(signed)["valid"]
    signed["dossier"]["request"]["amount"] = 101
    assert not chain.verify_signed(signed)["valid"]
