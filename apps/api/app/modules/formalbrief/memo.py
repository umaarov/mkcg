"""FormalBrief: credit memo generation with a hard numeric verifier.

Two writers: a deterministic template (always available, used offline / on perimeter mode without a local
model) and an LLM writer that may only use numbers from the fact sheet. The verifier rejects any number that is
not a fact, and any sentence with a number but no [Fxx] citation. One retry, then fall back to the template.
"""
from __future__ import annotations

import re

from ..router import gateway
from .facts import Fact, by_key

REC = {
    "APPROVE": {"en": "Recommend APPROVAL", "uz": "TASDIQLASH tavsiya etiladi", "ru": "Рекомендуется ОДОБРИТЬ"},
    "REVIEW": {"en": "Recommend officer REVIEW of flagged items before approval", "uz": "Tasdiqlashdan oldin belgilangan bandlarni KO'RIB CHIQISH tavsiya etiladi", "ru": "Перед одобрением рекомендуется ПРОВЕРИТЬ отмеченные пункты"},
    "REFER": {"en": "REFER to the credit committee", "uz": "Kredit qo'mitasiga YO'NALTIRISH tavsiya etiladi", "ru": "Рекомендуется ПЕРЕДАТЬ на кредитный комитет"},
    "DECLINE": {"en": "Recommend DECLINE", "uz": "RAD ETISH tavsiya etiladi", "ru": "Рекомендуется ОТКАЗАТЬ"},
}
RULE_FACT = {"request_amount": "request_amount", "request_term": "request_term", "business_age_months": "business_age_months",
             "active_months": "active_months", "dscr": "dscr", "loan_to_annual_inflow": "loan_to_annual_inflow",
             "top1_share": "top1_share", "gap_adj": "gap_adj", "roundtrip_share": "roundtrip_share", "inflow_cv": "inflow_cv",
             "trend_ratio": "trend_ratio", "low_balance_days_share": "low_balance_days_share", "cashout_ratio": "cashout_ratio",
             "non_operating_in_share": "non_operating_in_share"}

T = {
    "en": dict(
        h=["Summary", "Cash flow", "Revenue consistency", "Points for the officer", "Disclaimer"],
        summary="{rec}. The applicant requests {amt} UZS over {term} months [@request_amount][@request_term], an instalment of about {inst} UZS under assumed pricing [@installment]. Average monthly operating cash flow is {net} UZS [@net_cf_avg], giving a DSCR of {dscr} [@dscr]; the most the account supports is an instalment of {maxi} UZS [@max_installment].",
        cash="Operating inflows average {inf} UZS a month [@op_inflow_avg] with volatility of {cv} [@inflow_cv] and a second-half to first-half trend of {tr} [@trend_ratio]. The largest customer provides {t1} of sales [@top1_share]. Cash withdrawals are {co} of outflows [@cashout_ratio] and existing debt service is {eds} UZS a month [@existing_debt_service].",
        rev_ok="Declared revenue of {dec} UZS [@declared_total] is consistent with {bank} UZS of operating inflows on the account [@bank_inflow]; the ratio excluding circular flows is {gap} [@gap_adj].",
        rev_over="Declared revenue of {dec} UZS [@declared_total] is HIGHER than operating inflows of {bank} UZS on the account [@bank_inflow]; ratio {gap} [@gap_adj]. Circular inflows are {rt} of sales receipts [@roundtrip_share].",
        rev_under="Declared revenue of {dec} UZS [@declared_total] is LOWER than operating inflows of {bank} UZS on the account [@bank_inflow]; ratio {gap} [@gap_adj]. The declaration understates the business; underwriting should rely on the account, and the tax position should be clarified.",
        flags_intro="Rules needing attention ({nr} for review, {nf} failed) [@rules_refer][@rules_fail]:",
        flag="{label}: {val} [{fid}]",
        flags_none="All {np} policy rules passed [@rules_pass].",
        model="Model view: default probability {pd} (risk band {band}) [@pd][@band]. The model is trained on synthetic data and is shown as decision support only.",
        disc="This memo is generated from verified document fields and deterministic calculations. It is a recommendation; the credit decision belongs to the authorised officer or committee."),
    "uz": dict(
        h=["Xulosa", "Pul oqimi", "Tushum mosligi", "Xodim e'tibori uchun", "Ogohlantirish"],
        summary="{rec}. Ariza beruvchi {amt} so'm summani {term} oyga so'ramoqda [@request_amount][@request_term]; taxminiy narxda oylik to'lov {inst} so'm [@installment]. O'rtacha oylik operatsion pul oqimi {net} so'm [@net_cf_avg], DSCR {dscr} [@dscr]; hisob ko'tara oladigan maksimal oylik to'lov {maxi} so'm [@max_installment].",
        cash="Operatsion tushumlar o'rtacha oyiga {inf} so'm [@op_inflow_avg], o'zgaruvchanlik {cv} [@inflow_cv], ikkinchi yarim / birinchi yarim dinamikasi {tr} [@trend_ratio]. Eng yirik mijoz savdoning {t1} ulushini beradi [@top1_share]. Naqd yechish chiqimlarning {co} qismi [@cashout_ratio], mavjud qarz to'lovi oyiga {eds} so'm [@existing_debt_service].",
        rev_ok="Deklaratsiyadagi {dec} so'm tushum [@declared_total] hisobdagi {bank} so'm operatsion tushumga mos [@bank_inflow]; aylanma oqimlarsiz nisbat {gap} [@gap_adj].",
        rev_over="Deklaratsiyadagi {dec} so'm tushum [@declared_total] hisobdagi {bank} so'm operatsion tushumdan YUQORI [@bank_inflow]; nisbat {gap} [@gap_adj]. Aylanma tushumlar savdo tushumining {rt} qismi [@roundtrip_share].",
        rev_under="Deklaratsiyadagi {dec} so'm tushum [@declared_total] hisobdagi {bank} so'm operatsion tushumdan PAST [@bank_inflow]; nisbat {gap} [@gap_adj]. Deklaratsiya biznesni kam ko'rsatgan; baholashda hisob ma'lumotiga tayanish va soliq holatini aniqlash kerak.",
        flags_intro="E'tibor talab qiluvchi qoidalar ({nr} ta ko'rib chiqish, {nf} ta o'tmagan) [@rules_refer][@rules_fail]:",
        flag="{label}: {val} [{fid}]",
        flags_none="Barcha {np} ta siyosat qoidasi o'tdi [@rules_pass].",
        model="Model xulosasi: defolt ehtimoli {pd} (risk toifasi {band}) [@pd][@band]. Model sintetik ma'lumotlarda o'qitilgan va faqat qaror qo'llab-quvvatlash uchun ko'rsatiladi.",
        disc="Ushbu xulosa tasdiqlangan hujjat maydonlari va deterministik hisob-kitoblar asosida tuzilgan. Bu tavsiya; kredit qarori vakolatli xodim yoki qo'mitaga tegishli."),
    "ru": dict(
        h=["Резюме", "Денежный поток", "Согласованность выручки", "Вопросы для сотрудника", "Оговорка"],
        summary="{rec}. Заявитель запрашивает {amt} сум на {term} мес. [@request_amount][@request_term], платёж около {inst} сум при расчётной ставке [@installment]. Среднемесячный операционный денежный поток {net} сум [@net_cf_avg], DSCR {dscr} [@dscr]; максимальный платёж, который выдерживает счёт, {maxi} сум [@max_installment].",
        cash="Операционные поступления в среднем {inf} сум в месяц [@op_inflow_avg], волатильность {cv} [@inflow_cv], динамика второй половины к первой {tr} [@trend_ratio]. Крупнейший клиент даёт {t1} продаж [@top1_share]. Снятие наличных — {co} расходов [@cashout_ratio], текущие платежи по долгам {eds} сум в месяц [@existing_debt_service].",
        rev_ok="Заявленная выручка {dec} сум [@declared_total] согласуется с операционными поступлениями на счёт {bank} сум [@bank_inflow]; отношение без круговых потоков {gap} [@gap_adj].",
        rev_over="Заявленная выручка {dec} сум [@declared_total] ВЫШЕ операционных поступлений на счёт {bank} сум [@bank_inflow]; отношение {gap} [@gap_adj]. Круговые поступления составляют {rt} продаж [@roundtrip_share].",
        rev_under="Заявленная выручка {dec} сум [@declared_total] НИЖЕ операционных поступлений на счёт {bank} сум [@bank_inflow]; отношение {gap} [@gap_adj]. Декларация занижает бизнес; оценку следует строить по счёту и уточнить налоговую позицию.",
        flags_intro="Правила, требующие внимания ({nr} на рассмотрение, {nf} не пройдено) [@rules_refer][@rules_fail]:",
        flag="{label}: {val} [{fid}]",
        flags_none="Все {np} правил политики пройдены [@rules_pass].",
        model="Мнение модели: вероятность дефолта {pd} (группа риска {band}) [@pd][@band]. Модель обучена на синтетических данных и служит только поддержкой решения.",
        disc="Заключение составлено по проверенным полям документов и детерминированным расчётам. Это рекомендация; кредитное решение принимает уполномоченный сотрудник или комитет."),
}


def _fid(facts: dict[str, Fact], key: str) -> Fact | None:
    return facts.get(key)


def template_memo(ctx: dict, facts: list[Fact], lang: str) -> dict:
    f = by_key(facts)
    t = T[lang]
    d = lambda k: f[k].display  # noqa: E731
    rules = ctx["rules"]
    rec_txt = REC[rules["recommendation"]][lang]
    ver = ctx["recon"]["verdict"]
    rev_key = {"consistent": "rev_ok", "over_declared": "rev_over", "under_declared": "rev_under"}[ver]
    def R(txt: str) -> str:
        return re.sub(r"\[@(\w+)\]", lambda mo: f"[{f[mo.group(1)].id}]" if mo.group(1) in f else "", txt)

    sections = []
    sections.append(dict(title=t["h"][0], text=t["summary"].format(rec=rec_txt, amt=d("request_amount"), term=d("request_term"), inst=d("installment"),
                                                                    net=d("net_cf_avg"), dscr=d("dscr"), maxi=d("max_installment"))))
    sections.append(dict(title=t["h"][1], text=t["cash"].format(inf=d("op_inflow_avg"), cv=d("inflow_cv"), tr=d("trend_ratio"), t1=d("top1_share"),
                                                                co=d("cashout_ratio"), eds=d("existing_debt_service"))))
    sections.append(dict(title=t["h"][2], text=t[rev_key].format(dec=d("declared_total"), bank=d("bank_inflow"), gap=d("gap_adj"), rt=d("roundtrip_share"))))
    flagged = [r for r in rules["results"] if r["outcome"] != "PASS"]
    lines = []
    if flagged:
        lines.append(t["flags_intro"].format(nr=d("rules_refer"), nf=d("rules_fail")))
        for r in flagged[:8]:
            fk = RULE_FACT.get(r["metric"])
            if fk and fk in f:
                lines.append("• " + t["flag"].format(label=r["label"][lang], val=f[fk].display, fid=f[fk].id) + f" ({r['id']}, {r['outcome']})")
            else:
                lines.append(f"• {r['label'][lang]} ({r['id']}, {r['outcome']})")
    else:
        lines.append(t["flags_none"].format(np=d("rules_pass")))
    sections.append(dict(title=t["h"][3], text="\n".join(lines)))
    if "pd" in f:
        sections.append(dict(title="", text=t["model"].format(pd=d("pd"), band=d("band"))))
    sections.append(dict(title=t["h"][4], text=t["disc"]))
    for sec in sections:
        sec["text"] = R(sec["text"])
    return dict(lang=lang, sections=sections, writer="template")


# ---------------------------------------------------------------------------------------
_NUM = re.compile(r"\d+(?:[  ]\d{3})*(?:[.,]\d+)?")
_STRIP = re.compile(r"\[(?:F\d+)\]|\bR\d{2}\b|\bF\d{2}\b")


def _norm(num: str) -> str:
    s = num.replace(" ", "").replace(" ", "")
    return s.replace(",", ".").rstrip("0").rstrip(".") if "." in s else s


def verify(text: str, facts: list[Fact]) -> dict:
    allowed = {_norm(n) for f in facts for n in _NUM.findall(f.display)}
    allowed |= {"2026", "1", "2", "3", "12", "24", "36", "48"}
    allowed_ids = {f.id for f in facts}
    violations = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        cites = re.findall(r"\[(F\d+)\]", sent)
        for c in cites:
            if c not in allowed_ids:
                violations.append(dict(kind="unknown_fact", sentence=sent.strip(), detail=c))
        core = _STRIP.sub("", sent)
        nums = [n for n in _NUM.findall(core) if _norm(n) not in allowed]
        for n in nums:
            violations.append(dict(kind="number_not_in_facts", sentence=sent.strip(), detail=n))
        if _NUM.findall(core) and not cites:
            violations.append(dict(kind="uncited_numeric_sentence", sentence=sent.strip(), detail=""))
    return dict(ok=not violations, violations=violations)


SYSTEM_MEMO = ("You write a short, plain credit memo for a bank loan officer. HARD RULES: use ONLY the facts provided. "
               "Write every number exactly as in the 'display' column. Every sentence that contains a number must end with the fact id(s) "
               "in square brackets, e.g. [F06]. Do not write any other number. Do not name the applicant. Do not invent facts. "
               "Do not decide: you may only restate the system recommendation. Output the memo as plain text with five sections: "
               "{sections}. Keep it under 330 words.")


def llm_memo(ctx: dict, facts: list[Fact], lang: str, tmpl: dict) -> dict | None:
    if not gateway.available():
        return None
    lang_name = {"en": "English", "uz": "Uzbek (Latin script)", "ru": "Russian"}[lang]
    sections = ", ".join(s["title"] for s in tmpl["sections"] if s["title"])
    rows = "\n".join(f"{f.id} | {f.label['en']} | {f.display}{(' ' + f.unit) if f.unit in ('UZS', 'months') else ''}" for f in facts)
    flagged = "; ".join(f"{r['id']} {r['label']['en']} => {r['outcome']}" for r in ctx["rules"]["results"] if r["outcome"] != "PASS") or "none"
    user = (f"Language: {lang_name}\nSystem recommendation: {ctx['rules']['recommendation']}\n"
            f"Revenue consistency verdict: {ctx['recon']['verdict']}\nRules not passed: {flagged}\n\nFACTS (id | label | display):\n{rows}")
    feedback = ""
    for attempt in range(2):
        try:
            res = gateway.complete("memo", SYSTEM_MEMO.format(sections=sections), user + feedback, masked=True,
                                   model=gateway.settings.memo_model, max_tokens=1500)
        except gateway.RouterError:
            return None
        v = verify(res.text, facts)
        if v["ok"]:
            return dict(lang=lang, sections=[dict(title="", text=res.text.strip())], writer="llm", model=res.model,
                        verifier=dict(ok=True, attempts=attempt + 1), cost_usd=res.cost_usd, seconds=res.seconds)
        bad = "; ".join(f"{x['kind']}: '{x['detail'] or x['sentence'][:50]}'" for x in v["violations"][:6])
        feedback = f"\n\nYour previous draft was rejected by the verifier: {bad}. Rewrite using only fact display values, each sentence with a citation."
    return None


def generate(ctx: dict, facts: list[Fact], lang: str, use_llm: bool = True) -> dict:
    tmpl = template_memo(ctx, facts, lang)
    out = tmpl
    out["verifier"] = verify("\n".join(s["text"] for s in tmpl["sections"]), facts)
    if use_llm:
        l = llm_memo(ctx, facts, lang, tmpl)
        if l:
            out = l
            out["template"] = tmpl
        else:
            out["note"] = "LLM writer unavailable or rejected by verifier; deterministic template used"
    return out
