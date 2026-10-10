"""Signals: portfolio early warning. Runs on a *synthetic* book of approved loans (declared in README).

Each month after origination the account's inflow and balance are compared with the borrower's own pre-loan
baseline. An alert fires before a missed-payment signal would, so the officer can call the borrower early.
Thresholds are fitted on one half of the book and evaluated on the other.
"""
from __future__ import annotations

import json
from multiprocessing import Pool

import numpy as np

from ...config import settings
from ...datagen import sme as S
from ..statement.analytics import annuity


def _loan(seed: int) -> dict:
    sme = S.random_sme(seed)
    st = S.simulate_statement(sme, seed)
    inst = annuity(sme.req_amount, sme.term, S.ANNUAL_RATE)
    o = S.simulate_outcome(sme, seed, st, new_inst=inst)
    base_in = float(np.mean(st["monthly_true_revenue"][-3:]) * (1 - sme.undeposited))
    return dict(id=f"L{seed}", name=f"{sme.core_name}", form=sme.form, sector=sme.sector, amount=sme.req_amount, term=sme.term,
                inflow=[float(x) for x in o["inflow"]], balance=[float(x) for x in o["balance"]], base_inflow=base_in,
                opening_balance=float(st["closing"]), default_month=o["default_month"], installment=inst)


def ews(loan: dict, t: int) -> float:
    """Early-warning score 0..100 at month index t (uses data up to and including t)."""
    inflow = np.array(loan["inflow"][: t + 1])
    bal = np.array(loan["balance"][: t + 1])
    base = max(loan["base_inflow"], 1.0)
    recent = inflow[-3:].mean()
    r1 = np.clip(1 - recent / base, 0, 1)                                   # inflow erosion vs own baseline
    drain = (loan["opening_balance"] - bal[-1]) / max(loan["opening_balance"], 0.6 * base)
    r2 = np.clip(drain, 0, 1)                                               # cash buffer drain
    r3 = np.clip((inflow.std() / max(inflow.mean(), 1) - 0.12) / 0.4, 0, 1)  # unusual volatility
    r4 = 1.0 if bal[-1] < 0 else 0.0                                        # account in the red
    return float(100 * (0.40 * r1 + 0.30 * r2 + 0.10 * r3 + 0.20 * r4))


def _first_alert(loan: dict, thr: float, start: int = 2) -> int | None:
    for t in range(start, 12):
        if ews(loan, t) >= thr:
            return t
    return None


def run(n: int = 4000, seed0: int = 900_000) -> dict:
    with Pool(6) as p:
        loans = p.map(_loan, range(seed0, seed0 + n), chunksize=50)
    rng = np.random.default_rng(1)
    idx = rng.permutation(n)
    fit, test = [loans[i] for i in idx[: n // 2]], [loans[i] for i in idx[n // 2:]]

    def evaluate(book, thr):
        d = [l for l in book if l["default_month"] is not None]
        s = [l for l in book if l["default_month"] is None]
        lead = []
        caught = 0
        for l in d:
            a = _first_alert(l, thr)
            if a is not None and a < l["default_month"]:
                caught += 1
                lead.append(l["default_month"] - a)
        fp = sum(1 for l in s if _first_alert(l, thr) is not None)
        alerts = caught + fp
        return dict(threshold=thr, defaults=len(d), caught_before_default=caught, recall=caught / max(len(d), 1),
                    false_alert_rate_on_survivors=fp / max(len(s), 1), precision=caught / max(alerts, 1),
                    median_lead_months=float(np.median(lead)) if lead else 0.0, mean_lead_months=float(np.mean(lead)) if lead else 0.0)

    best = None
    for thr in range(10, 70, 3):
        e = evaluate(fit, thr)
        f = e["recall"] - 1.5 * e["false_alert_rate_on_survivors"]
        if best is None or f > best[0]:
            best = (f, thr)
    thr = best[1]
    fit_m, test_m = evaluate(fit, thr), evaluate(test, thr)
    # watchlist for the UI: live loans at their latest month with highest score
    now_t = 7
    live = [l for l in test if l["default_month"] is None or l["default_month"] > now_t]
    scored = sorted(((ews(l, now_t), l) for l in live), key=lambda x: -x[0])[:14]
    watch = [dict(id=l["id"], name=l["name"], form=l["form"], sector=l["sector"], amount=l["amount"], score=round(sc, 1),
                  inflow=[round(x) for x in l["inflow"][: now_t + 1]], balance=[round(x) for x in l["balance"][: now_t + 1]],
                  base_inflow=round(l["base_inflow"]), eventually_defaulted=l["default_month"] is not None) for sc, l in scored]
    out = dict(n_loans=n, threshold=thr, fit=fit_m, test=test_m, watchlist=watch, as_of_month=now_t,
               baseline="missed-payment trigger = alert only at the default month (lead time 0)",
               caveat="Synthetic book. Lead time and recall measure how well the signals recover the simulated process, not real portfolio behaviour.")
    (settings.models_dir / "signals.json").write_text(json.dumps(out, indent=1))
    return out


def load() -> dict | None:
    p = settings.models_dir / "signals.json"
    return json.loads(p.read_text()) if p.exists() else None


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in ("threshold", "fit", "test")}, indent=1))
