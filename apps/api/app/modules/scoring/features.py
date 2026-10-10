"""Scoring features. One function builds the vector for both training and live cases."""
from __future__ import annotations

import math

# name -> (monotone sign w.r.t. default risk, {lang: reason text when this feature pushes risk UP}, {lang: text when it pushes DOWN})
FEATURES: dict[str, tuple[int, dict, dict]] = {
    "dscr": (-1, {"en": "Cash flow covers instalments thinly", "uz": "Pul oqimi to'lovlarni zo'rg'a qoplaydi", "ru": "Денежный поток едва покрывает платежи"},
             {"en": "Cash flow comfortably covers instalments", "uz": "Pul oqimi to'lovlarni bemalol qoplaydi", "ru": "Денежный поток уверенно покрывает платежи"}),
    "loan_to_annual_inflow": (1, {"en": "Loan is large relative to annual inflow", "uz": "Kredit yillik tushumga nisbatan katta", "ru": "Кредит велик относительно годовых поступлений"},
                              {"en": "Loan is modest relative to annual inflow", "uz": "Kredit yillik tushumga nisbatan o'rtacha", "ru": "Кредит умерен относительно годовых поступлений"}),
    "inflow_cv": (1, {"en": "Monthly inflows are volatile", "uz": "Oylik tushumlar beqaror", "ru": "Месячные поступления нестабильны"},
                  {"en": "Monthly inflows are stable", "uz": "Oylik tushumlar barqaror", "ru": "Месячные поступления стабильны"}),
    "trend_ratio": (-1, {"en": "Inflows are declining", "uz": "Tushumlar kamayib bormoqda", "ru": "Поступления снижаются"},
                    {"en": "Inflows are growing", "uz": "Tushumlar o'smoqda", "ru": "Поступления растут"}),
    "top1_share": (1, {"en": "One customer dominates sales", "uz": "Savdoda bitta mijoz ustun", "ru": "Один клиент доминирует в продажах"},
                   {"en": "Customer base is diversified", "uz": "Mijozlar bazasi turli xil", "ru": "База клиентов диверсифицирована"}),
    "hhi": (1, {"en": "Customer base is concentrated", "uz": "Mijozlar bazasi konsentratsiyalashgan", "ru": "База клиентов концентрирована"},
            {"en": "Customer base is broad", "uz": "Mijozlar bazasi keng", "ru": "База клиентов широкая"}),
    "gap_dev": (1, {"en": "Declared revenue disagrees with bank inflows", "uz": "Deklaratsiya tushumi bank tushumiga mos kelmaydi", "ru": "Заявленная выручка расходится с поступлениями"},
                {"en": "Declared revenue matches bank inflows", "uz": "Deklaratsiya tushumi bank tushumiga mos", "ru": "Заявленная выручка согласуется с поступлениями"}),
    "roundtrip_share": (1, {"en": "Part of inflows are refunded within days", "uz": "Tushumning bir qismi bir necha kunda qaytarilgan", "ru": "Часть поступлений возвращена в течение нескольких дней"},
                        {"en": "No circular inflows detected", "uz": "Aylanma tushumlar topilmadi", "ru": "Круговых поступлений не выявлено"}),
    "cashout_ratio": (1, {"en": "High share of cash withdrawals", "uz": "Naqd yechish ulushi yuqori", "ru": "Высокая доля снятия наличных"},
                      {"en": "Low cash withdrawals", "uz": "Naqd yechish kam", "ru": "Снятие наличных невелико"}),
    "owner_transfer_ratio": (1, {"en": "Large transfers to the owner", "uz": "Ta'sischiga katta o'tkazmalar", "ru": "Крупные переводы учредителю"},
                             {"en": "Modest owner withdrawals", "uz": "Ta'sischi yechishlari o'rtacha", "ru": "Умеренные выводы владельца"}),
    "non_operating_in_share": (1, {"en": "Inflows rely on owner loans / other lenders", "uz": "Tushumlar ta'sischi qarzi / boshqa kreditorlarga tayanadi", "ru": "Поступления опираются на займы учредителя / других кредиторов"},
                               {"en": "Inflows are operating", "uz": "Tushumlar operatsion", "ru": "Поступления операционные"}),
    "low_balance_days_share": (1, {"en": "Account often near empty", "uz": "Hisob tez-tez bo'sh", "ru": "Счёт часто почти пуст"},
                               {"en": "Healthy balances", "uz": "Qoldiqlar yetarli", "ru": "Достаточные остатки"}),
    "op_margin": (-1, {"en": "Thin operating margin", "uz": "Operatsion marja past", "ru": "Низкая операционная маржа"},
                  {"en": "Healthy operating margin", "uz": "Operatsion marja yaxshi", "ru": "Хорошая операционная маржа"}),
    "existing_ds_ratio": (1, {"en": "Existing debt service is heavy", "uz": "Mavjud qarz xizmati og'ir", "ru": "Существующие платежи по долгам велики"},
                          {"en": "Little existing debt", "uz": "Mavjud qarz kam", "ru": "Существующий долг невелик"}),
    "cash_deposit_share": (0, {"en": "Cash-heavy business", "uz": "Naqd pulga tayangan biznes", "ru": "Бизнес с большой долей наличных"},
                           {"en": "Mostly bank-settled sales", "uz": "Asosan bank orqali savdo", "ru": "Преимущественно безналичные продажи"}),
    "active_months": (-1, {"en": "Gaps in account activity", "uz": "Hisob faoliyatida uzilishlar", "ru": "Перерывы в активности счёта"},
                      {"en": "Continuous activity", "uz": "Uzluksiz faoliyat", "ru": "Непрерывная активность"}),
    "business_age_months": (-1, {"en": "Young business", "uz": "Yosh biznes", "ru": "Молодой бизнес"},
                            {"en": "Established business", "uz": "Barqaror biznes", "ru": "Устоявшийся бизнес"}),
    "log_avg_inflow": (-1, {"en": "Small scale of operations", "uz": "Faoliyat ko'lami kichik", "ru": "Небольшой масштаб операций"},
                       {"en": "Meaningful scale of operations", "uz": "Faoliyat ko'lami sezilarli", "ru": "Заметный масштаб операций"}),
}
NAMES = list(FEATURES)
MONOTONE = [FEATURES[n][0] for n in NAMES]


def build(metrics: dict, afford: dict, recon: dict, business_age_months: float) -> dict[str, float]:
    avg_in = max(metrics["op_inflow_avg"], 1.0)
    dscr = afford["dscr"]
    return dict(
        dscr=float(min(max(dscr, -5.0), 10.0)),
        loan_to_annual_inflow=float(min(afford["loan_to_annual_inflow"], 10.0)),
        inflow_cv=float(min(metrics["inflow_cv"], 3.0)),
        trend_ratio=float(min(max(metrics["trend_ratio"], 0.0), 3.0)),
        top1_share=float(metrics["top1_share"]),
        hhi=float(metrics["hhi"]),
        gap_dev=float(abs(math.log(max(min(recon["gap_adj"], 20.0), 0.05)))),
        roundtrip_share=float(metrics["roundtrip_share"]),
        cashout_ratio=float(metrics["cashout_ratio"]),
        owner_transfer_ratio=float(min(metrics["owner_transfer_ratio"], 2.0)),
        non_operating_in_share=float(metrics["non_operating_in_share"]),
        low_balance_days_share=float(metrics["low_balance_days_share"]),
        op_margin=float(max(min(metrics["op_margin"], 1.0), -1.0)),
        existing_ds_ratio=float(min(metrics["existing_debt_service"] / avg_in, 2.0)),
        cash_deposit_share=float(metrics["cash_deposit_share"]),
        active_months=float(metrics["active_months"]),
        business_age_months=float(min(business_age_months, 240)),
        log_avg_inflow=float(math.log(avg_in)),
    )
