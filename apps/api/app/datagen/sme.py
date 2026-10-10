"""Latent small-business model and 6-month bank statement simulation (fully synthetic)."""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import numpy as np

from . import names

PERIOD_START = date(2026, 4, 1)
MONTHS = 6
TAX_RATE_PCT = 4.0  # illustrative rate printed on the synthetic declarations
ANNUAL_RATE = 0.24  # assumed loan pricing, see rulesengine/policy.yaml


@dataclass
class SME:
    id: str
    core_name: str
    form: str
    owner: str
    sector: str
    tin: str
    pinfl: str
    account: str
    bank: str
    region: str
    reg_date: date
    employees: int
    phone: str
    base_rev: float          # true monthly revenue at period start (UZS)
    growth: float            # monthly drift
    season_amp: float
    season_phase: float
    vol: float
    n_customers: int
    conc_alpha: float        # small => concentrated customer base
    cost_ratio: float        # COGS / revenue
    salary: float
    rent: float
    existing_inst: float
    cash_share: float        # share of revenue received in cash and deposited
    undeposited: float       # share of revenue never touching the account
    declared_factor: float   # declared revenue / true revenue
    roundtrip: float         # fake circular inflow as share of revenue
    discipline: float        # 0..1 latent owner payment discipline
    shock_prob: float
    req_amount: float
    term: int
    lang: str
    archetype: str = "random"
    ask_ratio: float = 0.0   # >0: size the request from the statement's own cash flow (curated samples)

    def to_json(self) -> dict:
        d = asdict(self)
        d["reg_date"] = self.reg_date.isoformat()
        return d


def _digits(rng: random.Random, n: int, first_nonzero: bool = True) -> str:
    s = "".join(rng.choice("0123456789") for _ in range(n))
    return (rng.choice("123456789") + s[1:]) if first_nonzero else s


def annuity(principal: float, months: int, annual_rate: float = ANNUAL_RATE) -> float:
    r = annual_rate / 12
    return principal * r / (1 - (1 + r) ** -months)


def request_for(net_cf: float, base_rev: float, term: int, ask_ratio: float) -> float:
    """Requested principal whose installment is `ask_ratio` of monthly operating cash flow."""
    inst = max(net_cf, base_rev * 0.03) * ask_ratio
    r = ANNUAL_RATE / 12
    pv = inst * (1 - (1 + r) ** -term) / r
    return float(np.clip(round(pv / 5e6) * 5e6, 20e6, 300e6))


def random_sme(seed: int, archetype: str = "random", lang: str | None = None) -> SME:
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    sector = rng.choice(list(names.SECTORS))
    form = rng.choices(["MChJ", "XK", "YaTT"], weights=[0.55, 0.15, 0.30])[0]
    owner = names.person(rng)
    core, form = names.company_name(rng, sector, form, owner)
    base_rev = float(np.exp(nrng.normal(math.log(85e6), 0.75)))  # median ~85M UZS / month
    base_rev = float(np.clip(base_rev, 12e6, 900e6))
    employees = int(np.clip(round(base_rev / 45e6 + nrng.normal(0, 1.2)), 1, 60))
    salary = float(nrng.uniform(2.6e6, 5.2e6))
    margin_lo, margin_hi = names.SECTORS[sector]["margin"]
    cost_ratio = float(1 - nrng.uniform(margin_lo, margin_hi) - 0.10)
    rent = float(base_rev * nrng.uniform(0.02, 0.08))
    sme = SME(
        id=f"S{seed:06d}", core_name=core, form=form, owner=owner, sector=sector,
        tin=_digits(rng, 9), pinfl=_digits(rng, 14), account=_digits(rng, 20),
        bank=rng.choice(names.BANKS), region=rng.choice(names.REGIONS),
        reg_date=date(2026, 4, 1) - timedelta(days=int(nrng.integers(120, 3200))),
        employees=employees, phone="+998 " + rng.choice(["90", "91", "93", "94", "95", "97", "99", "88"]) + " " + _digits(rng, 3) + " " + _digits(rng, 2) + " " + _digits(rng, 2),
        base_rev=base_rev, growth=float(nrng.normal(0.004, 0.018)),
        season_amp=float(names.SECTORS[sector]["season"] * nrng.uniform(0.4, 1.2)),
        season_phase=float(nrng.uniform(0, 12)), vol=float(nrng.uniform(0.05, 0.28)),
        n_customers=int(np.clip(nrng.lognormal(math.log(14), 0.6), 3, 80)),
        conc_alpha=float(nrng.choice([0.35, 0.7, 1.4, 3.0], p=[0.15, 0.3, 0.35, 0.2])),
        cost_ratio=float(np.clip(cost_ratio, 0.42, 0.88)), salary=salary,
        rent=rent, existing_inst=0.0,
        cash_share=float(np.clip(nrng.beta(1.4, 5), 0, 0.7)),
        undeposited=float(np.clip(nrng.beta(1.2, 9), 0, 0.35)),
        declared_factor=1.0, roundtrip=0.0,
        discipline=float(np.clip(nrng.beta(6, 1.8), 0.05, 1)),
        shock_prob=float(np.clip(nrng.beta(1.6, 9), 0.01, 0.5)),
        req_amount=0.0, term=int(rng.choice([12, 18, 24, 36, 48])), lang=lang or rng.choice(names.LANGS),
        archetype=archetype,
    )
    if rng.random() < 0.35:  # existing debt service
        sme.existing_inst = float(base_rev * nrng.uniform(0.03, 0.14))
    # tax-declaration behaviour: most are roughly honest, a minority under- or over-report
    u = rng.random()
    if u < 0.62:
        sme.declared_factor = float(nrng.uniform(0.9, 1.08))
    elif u < 0.84:
        sme.declared_factor = float(nrng.uniform(0.55, 0.9))   # under-reporting (tax avoidance)
    elif u < 0.93:
        sme.declared_factor = float(nrng.uniform(1.25, 1.9))   # over-declared to look bigger
    else:
        sme.declared_factor = float(nrng.uniform(0.3, 0.55))
    if sme.declared_factor > 1.25 or rng.random() < 0.05:
        sme.roundtrip = float(nrng.uniform(0.12, 0.45))        # circular inflows inflate statement turnover
    net = base_rev * (1 - cost_ratio) - employees * salary - rent
    sme.req_amount = request_for(net, base_rev, sme.term, float(nrng.uniform(0.2, 0.85)))
    return sme


ARCHETYPES = {
    "strong": dict(conc_alpha=3.0, vol=0.07, declared_factor=1.02, roundtrip=0.0, discipline=0.95, shock_prob=0.02,
                   existing_inst=0.0, cash_share=0.12, undeposited=0.03, growth=0.012),
    "thin_file": dict(conc_alpha=1.4, vol=0.16, declared_factor=0.96, roundtrip=0.0, discipline=0.8,
                      shock_prob=0.08, existing_inst=0.0, cash_share=0.35, undeposited=0.12, growth=0.006),
    "inflated": dict(conc_alpha=0.7, vol=0.12, declared_factor=1.6, roundtrip=0.34, discipline=0.5, shock_prob=0.2,
                     cash_share=0.05, undeposited=0.0),
    "concentrated": dict(conc_alpha=0.3, vol=0.2, declared_factor=1.0, roundtrip=0.0, discipline=0.75, shock_prob=0.3,
                         growth=0.0),
    "declining": dict(conc_alpha=1.4, vol=0.18, declared_factor=1.05, roundtrip=0.0, discipline=0.7, shock_prob=0.25,
                      growth=-0.05, existing_inst=0.1),
    "cash_heavy": dict(conc_alpha=2.0, vol=0.14, declared_factor=0.62, roundtrip=0.0, discipline=0.75, shock_prob=0.1,
                       cash_share=0.5, undeposited=0.3, growth=0.004),
}


def archetype_sme(seed: int, archetype: str, lang: str | None = None) -> SME:
    s = random_sme(seed, archetype, lang)
    for k, v in ARCHETYPES[archetype].items():
        if k == "existing_inst":
            v = s.base_rev * v
        setattr(s, k, v)
    # re-size the request so the archetype keeps an interesting but plausible ask
    net = s.base_rev * (1 - s.cost_ratio) - s.employees * s.salary - s.rent
    s.req_amount = request_for(net, s.base_rev, s.term, 0.6)
    s.ask_ratio = ASK[archetype]
    return s


ASK = {"strong": 0.45, "thin_file": 0.6, "inflated": 0.55, "concentrated": 0.5, "declining": 0.45, "cash_heavy": 0.5}


# --------------------------------------------------------------------------------------
@dataclass
class Counterparty:
    tin: str
    core: str
    form: str
    kind: str  # customer | supplier | landlord | misc


def _counterparties(rng: random.Random, n_cust: int, n_sup: int) -> tuple[list[Counterparty], list[Counterparty]]:
    def mk(kind: str) -> Counterparty:
        sector = rng.choice(list(names.SECTORS))
        form = rng.choices(["MChJ", "XK", "YaTT"], weights=[0.7, 0.1, 0.2])[0]
        core, form = names.company_name(rng, sector, form)
        return Counterparty(_digits(rng, 9), core, form, kind)
    return [mk("customer") for _ in range(n_cust)], [mk("supplier") for _ in range(n_sup)]


def _bizday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _round_amount(x: float) -> int:
    return int(max(1000, round(x / 100) * 100))


def month_start(i: int) -> date:
    y, m = PERIOD_START.year, PERIOD_START.month + i
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, 1)


def simulate_statement(sme: SME, seed: int) -> dict:
    """Return {'opening', 'closing', 'rows', 'true_revenue', 'declared'} for the 6-month period."""
    rng = random.Random(seed * 7919 + 13)
    nrng = np.random.default_rng(seed * 104729 + 7)
    customers, suppliers = _counterparties(rng, sme.n_customers, rng.randint(4, 12))
    cust_w = nrng.dirichlet(np.full(len(customers), sme.conc_alpha))
    landlord = Counterparty(_digits(rng, 9), rng.choice(names.BRANDS) + " Invest", "MChJ", "landlord")
    events: list[dict] = []
    true_rev_months = []

    def add(d: date, cat: str, amount: float, cp: Counterparty | None, credit: bool):
        events.append(dict(date=_bizday(d), category=cat, amount=_round_amount(amount), cp=cp, credit=credit,
                           n=rng.randint(1, 999)))

    for mi in range(MONTHS):
        ms = month_start(mi)
        season = 1 + sme.season_amp * math.sin(2 * math.pi * (mi + sme.season_phase) / 12)
        rev = sme.base_rev * (1 + sme.growth) ** mi * season * math.exp(nrng.normal(0, sme.vol))
        true_rev_months.append(rev)
        banked = rev * (1 - sme.cash_share - sme.undeposited)
        # customer receipts
        k = max(3, int(sme.n_customers * rng.uniform(0.7, 1.6)))
        picks = nrng.choice(len(customers), size=k, p=cust_w)
        w = nrng.lognormal(0, 0.5, size=k)
        w = w / w.sum()
        for j in range(k):
            add(ms + timedelta(days=int(nrng.integers(0, 27))), "sales_receipt", banked * w[j], customers[picks[j]], True)
        # cash deposits
        if sme.cash_share > 0:
            kd = rng.randint(2, 6)
            wd = nrng.dirichlet(np.ones(kd))
            for j in range(kd):
                add(ms + timedelta(days=int(nrng.integers(0, 27))), "cash_deposit", rev * sme.cash_share * wd[j], None, True)
        # round-tripping (circular) inflows: round amounts out and back within days
        if sme.roundtrip > 0:
            kr = rng.randint(2, 5)
            partner = customers[int(nrng.integers(0, len(customers)))]
            for _ in range(kr):
                amt = round(rev * sme.roundtrip / kr / 5e6) * 5e6 or 5e6
                d = ms + timedelta(days=int(nrng.integers(0, 22)))
                add(d, "sales_receipt", amt, partner, True)
                add(d + timedelta(days=int(nrng.integers(1, 5))), "supplier_payment", amt * 0.985, partner, False)
        # supplier payments
        cogs = rev * sme.cost_ratio
        ks = rng.randint(3, 9)
        ws = nrng.dirichlet(np.ones(ks))
        for j in range(ks):
            add(ms + timedelta(days=int(nrng.integers(0, 27))), "supplier_payment", cogs * ws[j], rng.choice(suppliers), False)
        # payroll (advance + final), rent, utilities, tax, bank fee
        pay = sme.employees * sme.salary
        add(ms + timedelta(days=4), "payroll", pay * 0.4, None, False)
        add(ms + timedelta(days=24), "payroll", pay * 0.6, None, False)
        add(ms + timedelta(days=2), "rent", sme.rent, landlord, False)
        add(ms + timedelta(days=int(nrng.integers(8, 20))), "utilities", sme.rent * nrng.uniform(0.1, 0.25), None, False)
        add(ms + timedelta(days=int(nrng.integers(10, 15))), "tax", rev * sme.declared_factor * TAX_RATE_PCT / 100 / 1.0 * (1 / 3), None, False)
        add(ms + timedelta(days=27), "bank_fee", rng.uniform(40e3, 190e3), None, False)
        if sme.existing_inst > 0:
            late = 0 if rng.random() < sme.discipline else rng.randint(4, 12)
            add(ms + timedelta(days=14 + late), "loan_payment", sme.existing_inst, None, False)
        # owner draws, occasional extra cash withdrawals, occasional owner loan
        draw = rev * (1 - sme.cost_ratio) * nrng.uniform(0.05, 0.35) * (1.4 - sme.discipline)
        add(ms + timedelta(days=int(nrng.integers(6, 26))), "owner_transfer", draw, None, False)
        if rng.random() < 0.55:
            add(ms + timedelta(days=int(nrng.integers(1, 27))), "cash_withdrawal", rev * nrng.uniform(0.01, 0.06), None, False)
        if rng.random() < 0.08:
            add(ms + timedelta(days=int(nrng.integers(1, 27))), "owner_inflow", rev * nrng.uniform(0.1, 0.4), None, True)

    events.sort(key=lambda e: (e["date"], not e["credit"]))
    opening = _round_amount(sme.base_rev * rng.uniform(0.3, 1.6))
    balance = opening
    rows = []
    doc_no = rng.randint(1, 400)
    for e in events:
        amt = e["amount"]
        if not e["credit"] and amt > balance:
            if e["category"] in ("supplier_payment", "owner_transfer", "cash_withdrawal", "utilities"):
                continue  # postponed (dropped) when the account is empty
            amt = max(1000, int(balance * 0.98)) if balance > 1000 else 0
            if amt == 0:
                continue
        balance += amt if e["credit"] else -amt
        doc_no += rng.randint(1, 4)
        cp = e["cp"]
        rows.append(dict(date=e["date"].isoformat(), doc_no=str(doc_no), category=e["category"],
                         cp_tin=cp.tin if cp else "", cp_core=cp.core if cp else "", cp_form=cp.form if cp else "",
                         purpose_n=str(e["n"]), debit=0 if e["credit"] else amt, credit=amt if e["credit"] else 0,
                         balance=balance))
    true_revenue = float(sum(true_rev_months))
    return dict(opening=opening, closing=balance, rows=rows, true_revenue=true_revenue,
                monthly_true_revenue=[float(x) for x in true_rev_months])


def declared_revenue(sme: SME, stmt: dict) -> dict:
    """Quarterly declared revenue = declared_factor * true revenue (the taxpayer's own figure)."""
    m = stmt["monthly_true_revenue"]
    q1 = int(round(sum(m[:3]) * sme.declared_factor / 1000) * 1000)
    q2 = int(round(sum(m[3:]) * sme.declared_factor / 1000) * 1000)
    total = q1 + q2
    return dict(rev_q1=q1, rev_q2=q2, rev_total=total, tax_rate=TAX_RATE_PCT,
                tax_amount=int(round(total * TAX_RATE_PCT / 100 / 1000) * 1000),
                employees=sme.employees, submitted=date(2026, 10, 1).isoformat())


def simulate_outcome(sme: SME, seed: int, stmt: dict, months: int = 12, new_inst: float | None = None) -> dict:
    """Forward 12-month trajectory after origination; `default_month` is None if the loan survives."""
    nrng = np.random.default_rng(seed * 31 + 5)
    rng = random.Random(seed * 17 + 3)
    inst = annuity(sme.req_amount, sme.term) if new_inst is None else new_inst
    cash = float(stmt["closing"])
    shock_m = None
    drop = 0.0
    if rng.random() < sme.shock_prob:
        shock_m = rng.randint(1, 8)
        # losing the largest customers hurts more when the base is concentrated
        drop = float(np.clip(nrng.uniform(0.15, 0.55) * (1.35 - min(sme.conc_alpha, 1.2)), 0.1, 0.75))
    arrears = 0
    default_month = None
    inflow, balance, rev_series = [], [], []
    for t in range(months):
        mi = MONTHS + t
        season = 1 + sme.season_amp * math.sin(2 * math.pi * (mi + sme.season_phase) / 12)
        rev = sme.base_rev * (1 + sme.growth) ** mi * season * math.exp(nrng.normal(0, sme.vol))
        if shock_m is not None and t >= shock_m:
            rev *= (1 - drop)
        net = rev * (1 - sme.cost_ratio) - sme.employees * sme.salary - sme.rent - sme.existing_inst
        draw = rev * (1 - sme.cost_ratio) * 0.18 * (1.4 - sme.discipline)
        cash += net - draw - inst
        rev_series.append(rev)
        inflow.append(rev * (1 - sme.undeposited))
        balance.append(cash)
        if default_month is None:
            if cash < -0.35 * sme.base_rev:
                arrears += 1
            else:
                arrears = max(0, arrears - 1)
            hazard = 0.002 + 0.016 * (1 - sme.discipline) ** 2 + (0.012 if sme.roundtrip > 0 else 0)
            if arrears >= 2 or rng.random() < hazard:
                default_month = t
    return dict(default_month=default_month, defaulted=default_month is not None, inflow=inflow, balance=balance,
                revenue=rev_series, shock_month=shock_m, shock_drop=drop, installment=inst)
