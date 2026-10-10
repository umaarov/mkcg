"""FormalBrief step 1: a numbered fact sheet. Every number in a memo must come from here."""
from __future__ import annotations

from dataclasses import asdict, dataclass


def uzs(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def x2(v: float) -> str:
    return f"{v:.2f}"


def n0(v: float) -> str:
    return f"{v:.0f}"


@dataclass
class Fact:
    id: str
    key: str
    value: float | str
    display: str
    unit: str
    label: dict

    def to_dict(self):
        return asdict(self)


def _L(en, uz, ru):
    return dict(en=en, uz=uz, ru=ru)


def build_facts(ctx: dict) -> list[Fact]:
    m, aff, rec, req = ctx["metrics"], ctx["afford"], ctx["recon"], ctx["request"]
    sc, rules = ctx.get("score") or {}, ctx["rules"]
    F: list[Fact] = []

    def add(key, value, fmt, unit, label):
        F.append(Fact(f"F{len(F) + 1:02d}", key, value, fmt(value) if not isinstance(value, str) else value, unit, label))

    add("request_amount", req["amount"], uzs, "UZS", _L("Requested amount", "So'ralgan summa", "Запрашиваемая сумма"))
    add("request_term", req["term"], n0, "months", _L("Requested term (months)", "So'ralgan muddat (oy)", "Запрашиваемый срок (мес.)"))
    add("installment", aff["installment"], uzs, "UZS", _L("Monthly instalment (assumed pricing)", "Oylik to'lov (taxminiy narx)", "Ежемесячный платёж (расчётная ставка)"))
    add("op_inflow_avg", m["op_inflow_avg"], uzs, "UZS", _L("Average monthly operating inflow", "O'rtacha oylik operatsion tushum", "Среднемесячные операционные поступления"))
    add("net_cf_avg", m["net_cf_avg"], uzs, "UZS", _L("Average monthly operating cash flow", "O'rtacha oylik operatsion pul oqimi", "Среднемесячный операционный денежный поток"))
    add("dscr", min(aff["dscr"], 99.0), x2, "x", _L("Debt service coverage ratio", "Qarzni qoplash koeffitsiyenti (DSCR)", "Коэффициент покрытия долга (DSCR)"))
    add("max_installment", aff["max_installment"], uzs, "UZS", _L("Maximum affordable instalment", "Maksimal to'lanadigan oylik to'lov", "Максимально допустимый платёж"))
    add("max_principal", aff["max_principal"], uzs, "UZS", _L("Maximum affordable principal for the term", "Muddat uchun maksimal kredit summasi", "Максимальная сумма кредита на срок"))
    add("inflow_cv", m["inflow_cv"], pct, "%", _L("Monthly inflow volatility (CV)", "Oylik tushum o'zgaruvchanligi", "Волатильность месячных поступлений"))
    add("trend_ratio", m["trend_ratio"], x2, "x", _L("Inflow trend (2nd half / 1st half)", "Tushum dinamikasi (2-yarim / 1-yarim)", "Динамика поступлений (2-я / 1-я половина)"))
    add("top1_share", m["top1_share"], pct, "%", _L("Largest customer share of sales", "Eng yirik mijoz ulushi", "Доля крупнейшего клиента"))
    add("top3_share", m["top3_share"], pct, "%", _L("Top-3 customers share of sales", "Top-3 mijoz ulushi", "Доля трёх крупнейших клиентов"))
    add("declared_total", rec["declared_total"], uzs, "UZS", _L("Revenue declared for the period", "Davr uchun deklaratsiya tushumi", "Заявленная выручка за период"))
    add("bank_inflow", rec["bank_inflow"], uzs, "UZS", _L("Operating inflows on the account", "Hisobdagi operatsion tushumlar", "Операционные поступления на счёт"))
    add("gap_adj", rec["gap_adj"], x2, "x", _L("Declared / bank inflow (excl. circular)", "Deklaratsiya / bank tushumi (aylanmasiz)", "Заявлено / поступило (без круговых)"))
    add("roundtrip_share", m["roundtrip_share"], pct, "%", _L("Circular inflows share", "Aylanma tushumlar ulushi", "Доля круговых поступлений"))
    add("cashout_ratio", m["cashout_ratio"], pct, "%", _L("Cash withdrawals share of outflows", "Naqd yechish ulushi", "Доля снятия наличных"))
    add("existing_debt_service", m["existing_debt_service"], uzs, "UZS", _L("Existing monthly debt service", "Mavjud oylik qarz to'lovi", "Текущие ежемесячные платежи по долгам"))
    add("low_balance_days_share", m["low_balance_days_share"], pct, "%", _L("Share of days with very low balance", "Qoldiq juda past kunlar ulushi", "Доля дней с очень низким остатком"))
    add("active_months", m["active_months"], n0, "months", _L("Months with activity", "Faol oylar soni", "Месяцев с активностью"))
    add("business_age_months", ctx["business_age_months"], n0, "months", _L("Business age (months)", "Biznes yoshi (oy)", "Возраст бизнеса (мес.)"))
    add("non_operating_in_share", m["non_operating_in_share"], pct, "%", _L("Non-operating inflows share", "Nooperatsion tushumlar ulushi", "Доля неоперационных поступлений"))
    add("owner_transfer_ratio", m["owner_transfer_ratio"], pct, "%", _L("Owner transfers / inflows", "Ta'sischiga o'tkazmalar / tushum", "Переводы учредителю / поступления"))
    add("loan_to_annual_inflow", aff["loan_to_annual_inflow"], x2, "x", _L("Loan / annual inflow", "Kredit / yillik tushum", "Кредит / годовые поступления"))
    if sc.get("available"):
        add("pd", sc["pd"], pct, "%", _L("Model default probability (synthetic-trained)", "Model bo'yicha defolt ehtimoli (sintetik)", "Вероятность дефолта по модели (синтетика)"))
        add("band", sc["band"], lambda v: v, "", _L("Risk band", "Risk toifasi", "Группа риска"))
    c = rules["counts"]
    add("rules_pass", c["pass_"], n0, "", _L("Rules passed", "O'tgan qoidalar", "Пройдено правил"))
    add("rules_refer", c["refer"], n0, "", _L("Rules needing review", "Ko'rib chiqish talab qiluvchi qoidalar", "Правил на рассмотрение"))
    add("rules_fail", c["fail"], n0, "", _L("Rules failed", "O'tmagan qoidalar", "Не пройдено правил"))
    add("recommendation", rules["recommendation"], lambda v: v, "", _L("System recommendation (not a decision)", "Tizim tavsiyasi (qaror emas)", "Рекомендация системы (не решение)"))
    return F


def by_key(facts: list[Fact]) -> dict[str, Fact]:
    return {f.key: f for f in facts}
