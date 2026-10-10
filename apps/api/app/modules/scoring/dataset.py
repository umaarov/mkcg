"""Synthetic training set: simulate -> run the *production* analytics -> label from the latent process."""
from __future__ import annotations

import time
from datetime import date
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from ...datagen import sme as S
from ..revenuegate.reconcile import reconcile
from ..statement.analytics import affordability, compute_metrics
from ..rulesengine.engine import load_policy
from . import features as F

AS_OF = date(2026, 10, 1)


def make_row(seed: int) -> dict:
    sme = S.random_sme(seed)
    stmt = S.simulate_statement(sme, seed)
    decl = S.declared_revenue(sme, stmt)
    rows = [dict(date=r["date"], debit=r["debit"], credit=r["credit"], balance=r["balance"], category=r["category"],
                 cp_tin=r["cp_tin"]) for r in stmt["rows"]]
    start = S.month_start(0).isoformat()
    end = "2026-09-30"
    m = compute_metrics(rows, stmt["opening"], stmt["closing"], start, end)
    aff = affordability(m, sme.req_amount, sme.term, load_policy()["pricing"]["annual_rate"])
    rec = reconcile(decl, m)
    age = (AS_OF - sme.reg_date).days / 30.4
    feats = F.build(m, aff, rec, age)
    o = S.simulate_outcome(sme, seed, stmt, new_inst=aff["installment"])
    return dict(seed=seed, n_tx=len(rows), y=int(o["defaulted"]), default_month=-1 if o["default_month"] is None else o["default_month"],
                archetype=sme.archetype, sector=sme.sector, **feats)


def build_dataset(n: int, out: Path, start_seed: int = 10_000, workers: int = 6) -> pd.DataFrame:
    t0 = time.time()
    with Pool(workers) as p:
        rows = p.map(make_row, range(start_seed, start_seed + n), chunksize=50)
    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(out)
    print(f"built {len(df)} SMEs, {int(df.n_tx.sum()):,} transactions, default rate {df.y.mean():.3f}, {time.time() - t0:.0f}s")
    return df
