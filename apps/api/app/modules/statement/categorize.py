"""Multilingual (uz-Latn / uz-Cyrl / ru) payment-purpose categorisation.

Rule cascade that uses the payment *direction* as a feature. Measured against ground truth in eval/.
"""
from __future__ import annotations

import re

from ..ocrgate.common import norm_text

_R = lambda p: re.compile(p, re.I)  # noqa: E731

LOAN = _R(r"kredit|кредит")
DISB = _R(r"mablag'i berildi|маблағи берилди|выдача|выдан")
OWNER = _R(r"ta'sischi|таъсисчи|учредител")
CASH = _R(r"naqd|нақд|наличн")
PAYROLL = _R(r"ish haqi|иш ҳақи|иш хаки|заработной|зарплат")
RENT = _R(r"ijara|ижара|аренд")
TAX = _R(r"soliq|солиқ|солик|налог")
UTIL = _R(r"kommunal|коммунал")
FEE = _R(r"komissiya|комиссия|комиссии")
GOODS = _R(r"shartnoma|шартнома|договор|hisob|ҳисоб|хисоб|счёт|счет|oldindan|олдиндан|предоплата|tovar|товар|xom ashyo|хом ашё|сырь")


def categorize(desc: str, credit: bool) -> str:
    t = norm_text(desc)
    if LOAN.search(t):
        return "loan_disbursement" if credit and DISB.search(t) else "loan_payment"
    if OWNER.search(t):
        return "owner_inflow" if credit else "owner_transfer"
    if CASH.search(t):
        return "cash_deposit" if credit else "cash_withdrawal"
    if PAYROLL.search(t):
        return "payroll"
    if RENT.search(t):
        return "rent"
    if TAX.search(t):
        return "tax"
    if UTIL.search(t):
        return "utilities"
    if FEE.search(t):
        return "bank_fee"
    if GOODS.search(t):
        return "sales_receipt" if credit else "supplier_payment"
    return "sales_receipt" if credit else "supplier_payment"


def infer_direction(desc: str) -> bool | None:
    """True = credit, False = debit, None = unknown. Used only when the chain gives no sign."""
    t = norm_text(desc)
    if CASH.search(t):
        return bool(re.search(r"kirit|кирит|взнос", t))
    if PAYROLL.search(t) or RENT.search(t) or TAX.search(t) or UTIL.search(t) or FEE.search(t):
        return False
    return None
