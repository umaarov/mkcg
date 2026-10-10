"""Align parsed transactions to ground truth (used by eval and tests). Key = (month, debit, credit):
month-level because analytics bucket by month and OCR garbles some day digits."""
from __future__ import annotations

from difflib import SequenceMatcher


def key(date: str, debit: float, credit: float, balance: float | None = None) -> tuple:
    return (date[:7], round(debit), round(credit))


def align(pred: list, truth: list[dict]):
    """Return list of (pred_idx|None, truth_idx|None) pairs by sequence alignment on (date, debit, credit)."""
    a = [key(p.date, p.debit, p.credit) for p in pred]
    b = [key(t["date"], t["debit"], t["credit"]) for t in truth]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    pairs, matched_pred, matched_true = [], set(), set()
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pairs.append((blk.a + k, blk.b + k))
            matched_pred.add(blk.a + k)
            matched_true.add(blk.b + k)
    return pairs, matched_pred, matched_true
