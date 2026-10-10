"""RevenueGate: declared revenue vs what actually reached the account."""
from __future__ import annotations


def reconcile(declared: dict, metrics: dict) -> dict:
    """declared: {rev_q1, rev_q2, rev_total}. metrics from Statement.compute_metrics."""
    mi = metrics["monthly_inflow"]
    half = len(mi) // 2
    bank = {"q1": float(sum(mi[:half])), "q2": float(sum(mi[half:]))}
    bank_total = float(sum(mi))
    # inflows that were refunded within days are not evidence of sales
    adj_total = max(bank_total - metrics.get("roundtrip_amount", 0.0), 1.0)
    dtot = float(declared.get("rev_total") or 0.0)
    gap = dtot / bank_total if bank_total > 0 else float("inf")
    gap_adj = dtot / adj_total
    q = {}
    for k, key in (("q1", "rev_q1"), ("q2", "rev_q2")):
        dv = declared.get(key)
        q[k] = dict(declared=dv, bank=bank[k], ratio=(float(dv) / bank[k]) if dv and bank[k] else None)
    if gap_adj > 1.25:
        verdict, sev = "over_declared", "high" if gap_adj > 1.6 else "medium"
    elif gap_adj < 0.75:
        verdict, sev = "under_declared", "high" if gap_adj < 0.5 else "medium"
    else:
        verdict, sev = "consistent", "low"
    # underwriting basis: conservative of the two sources
    basis = min(dtot, adj_total) if dtot > 0 else adj_total
    return dict(declared_total=dtot, bank_inflow=bank_total, bank_inflow_adj=adj_total, gap=gap, gap_adj=gap_adj,
                quarters=q, verdict=verdict, severity=sev, underwriting_revenue_basis=basis,
                roundtrip_amount=metrics.get("roundtrip_amount", 0.0))
