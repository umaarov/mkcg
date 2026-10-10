"""Statement: deterministic cash-flow analytics. No LLM touches a number in this module."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

OPERATING_IN = {"sales_receipt", "cash_deposit"}
OPERATING_OUT = {"supplier_payment", "payroll", "rent", "utilities", "tax", "bank_fee"}
NON_OPERATING_IN = {"owner_inflow", "loan_disbursement"}


def annuity(principal: float, months: int, annual_rate: float) -> float:
    r = annual_rate / 12
    return principal * r / (1 - (1 + r) ** -months)


def _month_range(start: str, end: str) -> list[str]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _roundtrip(df: pd.DataFrame) -> tuple[float, list[int]]:
    """Credits that are refunded to the same counterparty within 7 days at >=90% of the amount."""
    flagged: list[int] = []
    cred = df[(df.category == "sales_receipt") & (df.credit > 0) & (df.cp_tin != "")]
    deb = df[(df.debit > 0) & (df.cp_tin != "")]
    if cred.empty or deb.empty:
        return 0.0, flagged
    by_cp = {k: g for k, g in deb.groupby("cp_tin")}
    used: set[int] = set()
    for i, r in cred.iterrows():
        g = by_cp.get(r.cp_tin)
        if g is None:
            continue
        w = g[(g.ts >= r.ts) & (g.ts <= r.ts + pd.Timedelta(days=7)) & (g.debit >= 0.9 * r.credit) & (g.debit <= 1.02 * r.credit)]
        w = w[~w.index.isin(used)]
        if len(w):
            used.add(int(w.index[0]))
            flagged.append(int(i))
    total = cred.credit.sum()
    return (float(df.loc[flagged, "credit"].sum() / total) if total else 0.0), flagged


def compute_metrics(rows: list[dict], opening: float, closing: float, period_start: str, period_end: str) -> dict:
    df = pd.DataFrame(rows)
    if df.empty:
        return {"n_tx": 0}
    df = df.copy()
    df["ts"] = pd.to_datetime(df["date"])
    df["month"] = df["ts"].dt.strftime("%Y-%m")
    for c in ("debit", "credit", "balance"):
        df[c] = df[c].astype(float)
    if "cp_tin" not in df:
        df["cp_tin"] = ""
    df["cp_tin"] = df["cp_tin"].fillna("").astype(str)
    months = _month_range(period_start, period_end)
    n_m = len(months)
    op_in = df[df.category.isin(OPERATING_IN)]
    sales = df[df.category == "sales_receipt"]
    op_out = df[df.category.isin(OPERATING_OUT)]
    m_in = op_in.groupby("month").credit.sum().reindex(months, fill_value=0.0)
    m_out = op_out.groupby("month").debit.sum().reindex(months, fill_value=0.0)
    m_net = m_in - m_out
    total_in = float(op_in.credit.sum())
    avg_in = total_in / n_m
    cv = float(m_in.std(ddof=0) / avg_in) if avg_in > 0 else 0.0
    x = np.arange(n_m)
    slope = float(np.polyfit(x, m_in.values, 1)[0] / avg_in) if avg_in > 0 and n_m > 1 else 0.0
    half = max(1, n_m // 2)
    trend_ratio = float(m_in.iloc[-half:].mean() / m_in.iloc[:half].mean()) if m_in.iloc[:half].mean() > 0 else 1.0
    # customer concentration over sales receipts with a known counterparty
    cp = sales[sales.cp_tin != ""].groupby("cp_tin").credit.sum().sort_values(ascending=False)
    cp_total = float(cp.sum())
    shares = (cp / cp_total).values if cp_total > 0 else np.array([])
    top1 = float(shares[0]) if len(shares) else 0.0
    top3 = float(shares[:3].sum()) if len(shares) else 0.0
    hhi = float((shares ** 2).sum()) if len(shares) else 0.0
    total_debit = float(df.debit.sum())
    total_credit = float(df.credit.sum())
    rt_share, rt_idx = _roundtrip(df)
    rt_amount = float(df.loc[rt_idx, "credit"].sum()) if rt_idx else 0.0
    # balances: daily forward-filled series
    daily = df.groupby("ts").balance.last()
    idx = pd.date_range(period_start, period_end, freq="D")
    daily = daily.reindex(idx).ffill().fillna(opening)
    low_thr = 0.10 * avg_in
    sales_amt = sales.credit
    round_share = float(((sales_amt % 1_000_000 == 0) & (sales_amt >= 5_000_000)).mean()) if len(sales_amt) else 0.0
    loan_ds = float(df[df.category == "loan_payment"].debit.sum()) / n_m
    net_avg = float(m_net.mean())
    return dict(
        n_tx=int(len(df)), n_months=n_m, months=months, opening=float(opening), closing=float(closing),
        total_credit=total_credit, total_debit=total_debit,
        op_inflow_total=total_in, op_inflow_avg=avg_in,
        monthly_inflow=[float(v) for v in m_in.values], monthly_op_outflow=[float(v) for v in m_out.values],
        monthly_net_cf=[float(v) for v in m_net.values],
        active_months=int((m_in > 0).sum()), inflow_cv=cv, inflow_trend=slope, trend_ratio=trend_ratio,
        net_cf_avg=net_avg, op_margin=float(net_avg / avg_in) if avg_in > 0 else 0.0,
        n_customers=int(len(cp)), top1_share=top1, top3_share=top3, hhi=hhi,
        cash_deposit_share=float(df[df.category == "cash_deposit"].credit.sum() / total_in) if total_in > 0 else 0.0,
        cashout_ratio=float(df[df.category == "cash_withdrawal"].debit.sum() / total_debit) if total_debit > 0 else 0.0,
        owner_transfer_ratio=float(df[df.category == "owner_transfer"].debit.sum() / total_in) if total_in > 0 else 0.0,
        non_operating_in_share=float(df[df.category.isin(NON_OPERATING_IN)].credit.sum() / total_credit) if total_credit > 0 else 0.0,
        existing_debt_service=loan_ds, avg_balance=float(daily.mean()), min_balance=float(daily.min()),
        low_balance_days_share=float((daily < low_thr).mean()),
        roundtrip_share=rt_share, roundtrip_amount=rt_amount, roundtrip_tx=rt_idx, round_number_share=round_share,
        tax_paid=float(df[df.category == "tax"].debit.sum()),
    )


def affordability(metrics: dict, amount: float, term: int, annual_rate: float, max_payment_share: float = 0.5) -> dict:
    inst = annuity(amount, term, annual_rate)
    ds_total = metrics["existing_debt_service"] + inst
    net = metrics["net_cf_avg"]
    dscr = net / ds_total if ds_total > 0 else float("inf")
    max_inst = max(0.0, net * max_payment_share - metrics["existing_debt_service"])
    r = annual_rate / 12
    max_principal = max_inst * (1 - (1 + r) ** -term) / r if max_inst > 0 else 0.0
    return dict(installment=inst, dscr=dscr, max_installment=max_inst, max_principal=max_principal,
                loan_to_annual_inflow=amount / (metrics["op_inflow_avg"] * 12) if metrics["op_inflow_avg"] else float("inf"))
