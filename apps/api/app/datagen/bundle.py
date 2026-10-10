"""Build a complete synthetic applicant bundle: documents + ground truth."""
from __future__ import annotations

import json
import random
from pathlib import Path

from . import names, noise, render
from .sme import (SME, MONTHS, archetype_sme, declared_revenue, random_sme, simulate_outcome, simulate_statement,
                  annuity)


def build_bundle(sme: SME, seed: int, out_dir: Path, layout: str | None = None, degrade: str | None = None,
                 lang: str | None = None, with_outcome: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed ^ 0xBEEF)
    lang = lang or sme.lang
    layout = layout or rng.choice(["A", "B", "C"])
    stmt = simulate_statement(sme, seed)
    if sme.ask_ratio > 0:  # curated sample: ask relative to what the statement actually shows
        from ..modules.statement.analytics import compute_metrics
        from .sme import request_for
        rows = [dict(date=r["date"], debit=r["debit"], credit=r["credit"], balance=r["balance"], category=r["category"], cp_tin=r["cp_tin"]) for r in stmt["rows"]]
        net = compute_metrics(rows, stmt["opening"], stmt["closing"], "2026-04-01", "2026-09-30")["net_cf_avg"]
        sme.req_amount = request_for(net, sme.base_rev, sme.term, sme.ask_ratio)
    decl = declared_revenue(sme, stmt)
    files = {}
    f_stmt, f_decl, f_reg = out_dir / "statement.pdf", out_dir / "declaration.pdf", out_dir / "registration.pdf"
    meta = render.render_statement(sme, stmt, lang, layout, f_stmt)
    render.render_declaration(sme, decl, lang, rng.randint(0, 1), f_decl)
    render.render_registration(sme, lang, f_reg)
    if degrade:
        for f in (f_stmt, f_decl, f_reg):
            tmp = f.with_suffix(".clean.pdf")
            f.rename(tmp)
            noise.degrade_pdf(tmp, f, degrade, seed)
            tmp.unlink()
    files = {"statement": f_stmt.name, "declaration": f_decl.name, "registration": f_reg.name}
    bank_sales = sum(r["credit"] for r in stmt["rows"] if r["category"] in ("sales_receipt", "cash_deposit"))
    truth = dict(
        case_id=sme.id, lang=lang, layout=layout, degrade=degrade or "clean", archetype=sme.archetype,
        applicant=dict(name=names.fmt_company(sme.core_name, sme.form, lang), core=sme.core_name, form=sme.form,
                       owner=sme.owner, tin=sme.tin, pinfl=sme.pinfl, account=sme.account, phone=sme.phone,
                       bank=sme.bank, sector=sme.sector, reg_date=sme.reg_date.isoformat(), employees=sme.employees),
        request=dict(amount=sme.req_amount, term=sme.term),
        statement=dict(opening=stmt["opening"], closing=stmt["closing"], period_start=meta["period_start"],
                       period_end=meta["period_end"], rows=stmt["rows"], pages=meta["pages"]),
        declaration=decl,
        latent=dict(true_revenue=stmt["true_revenue"], declared_factor=sme.declared_factor, roundtrip=sme.roundtrip,
                    conc_alpha=sme.conc_alpha, cash_share=sme.cash_share, bank_inflow_operating=bank_sales,
                    gap=decl["rev_total"] / max(bank_sales, 1)),
        pii=[sme.tin, sme.pinfl, sme.account, sme.phone, sme.owner, names.display(sme.owner, lang)],
        files=files,
    )
    if with_outcome:
        o = simulate_outcome(sme, seed, stmt)
        truth["outcome"] = dict(defaulted=o["defaulted"], default_month=o["default_month"], installment=o["installment"])
    (out_dir / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1))
    return truth


def build_demo_set(root: Path) -> list[dict]:
    """Six curated archetypes in different languages/layouts for the UI 'sample applicants'."""
    plan = [("strong", 101, "uz", "A", None), ("thin_file", 202, "ru", "B", "scan"), ("inflated", 303, "uzc", "C", None),
            ("concentrated", 404, "ru", "A", None), ("declining", 505, "uz", "B", "scan"), ("cash_heavy", 606, "uz", "C", "photo")]
    out = []
    for arch, seed, lang, layout, deg in plan:
        sme = archetype_sme(seed, arch, lang)
        t = build_bundle(sme, seed, root / f"{arch}", layout=layout, degrade=deg, lang=lang)
        out.append(t)
    return out
