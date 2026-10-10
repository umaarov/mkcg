"""Name pools, transliteration and multilingual phrase tables for the synthetic generator.

All people and companies are fictional combinations of common given names, surnames and
brand words. Any match with a real person or company is coincidental.
"""
from __future__ import annotations

import random
import re

LANGS = ("uz", "uzc", "ru")  # Uzbek Latin, Uzbek Cyrillic, Russian

MALE = ["Aziz", "Bobur", "Dilshod", "Farhod", "Gʻayrat", "Hasan", "Ilhom", "Jasur", "Kamol", "Laziz",
        "Mansur", "Nodir", "Oybek", "Rustam", "Sardor", "Timur", "Ulugʻbek", "Valijon", "Shavkat",
        "Zafar", "Anvar", "Bahrom", "Doniyor", "Eldor", "Javlon", "Otabek", "Sanjar", "Sherzod"]
FEMALE = ["Dilnoza", "Feruza", "Gulnora", "Hilola", "Madina", "Nigora", "Malika", "Nozima", "Sevara",
          "Shahnoza", "Zilola", "Munisa", "Lola", "Kamola", "Barno", "Dildora"]
SURNAME_STEMS = ["Karim", "Usman", "Rahim", "Yusuf", "Abdullaev", "Tursun", "Nazarov", "Ismoil", "Saidov",
                 "Hamid", "Mirzaev", "Qodir", "Jalil", "Sobir", "Ergash", "Normat", "Rasul", "Salim",
                 "Ahmad", "Botir", "Komil", "Ortiq", "Davlat", "Halim", "Murod", "Umar"]

BRANDS = ["Baraka", "Navruz", "Samarqand", "Silk", "Orzu", "Zafar", "Mehr", "Bahor", "Sharq", "Oltin",
          "Zarafshon", "Fargʻona", "Buxoro", "Xiva", "Chorsu", "Registon", "Tolib", "Nur", "Asr",
          "Yulduz", "Madad", "Ishonch", "Kamalak", "Dilkash", "Vatan", "Guliston", "Sirdaryo",
          "Amir", "Temur", "Mirob", "Shifo", "Kelajak", "Shahar", "Tong", "Quyosh", "Olmos"]

SECTORS = {
    "retail":       {"words": ["Savdo", "Market", "Tovarlar"],       "margin": (0.14, 0.28), "season": 0.10},
    "food":         {"words": ["Oziq-ovqat", "Pishiriq", "Non"],     "margin": (0.18, 0.35), "season": 0.12},
    "agro":         {"words": ["Agro", "Meva", "Dehqon"],            "margin": (0.20, 0.40), "season": 0.35},
    "construction": {"words": ["Qurilish", "Bunyod", "Montaj"],     "margin": (0.15, 0.30), "season": 0.25},
    "textile":      {"words": ["Toʻqimachilik", "Tekstil", "Mato"],  "margin": (0.16, 0.30), "season": 0.10},
    "logistics":    {"words": ["Logistika", "Transport", "Yoʻl"],    "margin": (0.15, 0.28), "season": 0.08},
    "services":     {"words": ["Servis", "Xizmat", "Konsalt"],       "margin": (0.28, 0.50), "season": 0.07},
}
SECTOR_LABEL = {
    "retail": {"uz": "Chakana savdo", "uzc": "Чакана савдо", "ru": "Розничная торговля"},
    "food": {"uz": "Oziq-ovqat ishlab chiqarish", "uzc": "Озиқ-овқат ишлаб чиқариш", "ru": "Пищевое производство"},
    "agro": {"uz": "Qishloq xoʻjaligi", "uzc": "Қишлоқ хўжалиги", "ru": "Сельское хозяйство"},
    "construction": {"uz": "Qurilish", "uzc": "Қурилиш", "ru": "Строительство"},
    "textile": {"uz": "Toʻqimachilik", "uzc": "Тўқимачилик", "ru": "Текстильное производство"},
    "logistics": {"uz": "Transport va logistika", "uzc": "Транспорт ва логистика", "ru": "Транспорт и логистика"},
    "services": {"uz": "Xizmat koʻrsatish", "uzc": "Хизмат кўрсатиш", "ru": "Услуги"},
}

REGIONS = ["Toshkent", "Samarqand", "Buxoro", "Fargʻona", "Andijon", "Namangan", "Xorazm", "Qashqadaryo",
           "Surxondaryo", "Navoiy", "Jizzax", "Sirdaryo"]
REGION_CYR = {"Toshkent": "Тошкент", "Samarqand": "Самарқанд", "Buxoro": "Бухоро", "Fargʻona": "Фарғона",
              "Andijon": "Андижон", "Namangan": "Наманган", "Xorazm": "Хоразм", "Qashqadaryo": "Қашқадарё",
              "Surxondaryo": "Сурхондарё", "Navoiy": "Навоий", "Jizzax": "Жиззах", "Sirdaryo": "Сирдарё"}

_DIGRAPHS = [("oʻ", "ў"), ("o'", "ў"), ("o‘", "ў"), ("gʻ", "ғ"), ("g'", "ғ"), ("g‘", "ғ"),
             ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е"), ("ng", "нг")]
_SINGLE = dict(zip("abdfghijklmnopqrstuvxyz", "абдфгҳийклмнопқрстувхйз"))
_SINGLE.update({"g": "г", "h": "ҳ", "q": "қ", "e": "е", "x": "х", "y": "й", "j": "ж", "c": "ц", "w": "в"})
_RU_OVERRIDE = {"ў": "у", "ғ": "г", "қ": "к", "ҳ": "х"}


def to_cyr(text: str, lang: str = "uzc") -> str:
    """Uzbek Latin -> Cyrillic. lang='ru' maps Uzbek-specific letters to Russian equivalents."""
    out, i = [], 0
    low = text.lower()
    while i < len(text):
        ch = text[i]
        hit = None
        for lat, cyr in _DIGRAPHS:
            if low.startswith(lat, i):
                hit = (lat, cyr)
                break
        if hit:
            lat, cyr = hit
            piece = cyr
            lat = text[i:i + len(lat)]
            i += len(lat)
        else:
            if not ch.isalpha():
                out.append(ch)
                i += 1
                continue
            lc = ch.lower()
            piece = _SINGLE.get(lc, lc)
            if lc == "e" and (i == 0 or not text[i - 1].isalpha()):
                piece = "э"
            i += 1
            lat = ch
        if lang == "ru":
            piece = "".join(_RU_OVERRIDE.get(c, c) for c in piece)
        if lat[0].isupper():
            piece = piece[0].upper() + piece[1:]
        out.append(piece)
    return "".join(out)


def display(text: str, lang: str) -> str:
    """Render a Latin-script string in the document language."""
    text = text.replace("ʻ", "ʻ")
    if lang == "uz":
        return text
    return to_cyr(text, "ru" if lang == "ru" else "uzc")


def person(rng: random.Random, female: bool | None = None) -> str:
    female = rng.random() < 0.18 if female is None else female
    first = rng.choice(FEMALE if female else MALE)
    stem = rng.choice(SURNAME_STEMS)
    suffix = "ova" if female else "ov"
    if stem.endswith(("ev",)) or stem in ("Abdullaev", "Mirzaev"):
        sur = stem + ("a" if female else "")
    else:
        sur = stem + suffix
    return f"{sur} {first}"


LEGAL = {"MChJ": {"uz": '"{n}" MChJ', "uzc": '"{n}" МЧЖ', "ru": 'ООО «{n}»'},
         "XK": {"uz": '"{n}" XK', "uzc": '"{n}" ХК', "ru": 'ЧП «{n}»'},
         "YaTT": {"uz": "YaTT {n}", "uzc": "ЯТТ {n}", "ru": "ИП {n}"}}


def company_name(rng: random.Random, sector: str, form: str, owner: str | None = None) -> tuple[str, str]:
    """Return (core_name_latin, legal_form)."""
    if form == "YaTT":
        return owner or person(rng), form
    return f"{rng.choice(BRANDS)} {rng.choice(SECTORS[sector]['words'])}", form


def fmt_company(core: str, form: str, lang: str) -> str:
    return LEGAL[form][lang].format(n=display(core, lang))


# --- phrase tables: transaction purposes & document labels --------------------------------
PURPOSE = {
    "sales_receipt": {"uz": ["Shartnoma №{n} boʻyicha toʻlov", "Tovar uchun oldindan toʻlov, hisob №{n}", "{n}-sonli hisob-faktura boʻyicha toʻlov"],
                      "uzc": ["Шартнома №{n} бўйича тўлов", "Товар учун олдиндан тўлов, ҳисоб №{n}", "{n}-сонли ҳисоб-фактура бўйича тўлов"],
                      "ru": ["Оплата по договору №{n}", "Предоплата за товар, счёт №{n}", "Оплата по счёт-фактуре №{n}"]},
    "supplier_payment": {"uz": ["Tovar yetkazib berish uchun toʻlov, hisob-faktura №{n}", "Xom ashyo uchun toʻlov, shartnoma №{n}"],
                         "uzc": ["Товар етказиб бериш учун тўлов, ҳисоб-фактура №{n}", "Хом ашё учун тўлов, шартнома №{n}"],
                         "ru": ["Оплата за поставку товара, счёт-фактура №{n}", "Оплата сырья по договору №{n}"]},
    "payroll": {"uz": ["Ish haqi toʻlovi"], "uzc": ["Иш ҳақи тўлови"], "ru": ["Выплата заработной платы"]},
    "rent": {"uz": ["Ijara haqi toʻlovi"], "uzc": ["Ижара ҳақи тўлови"], "ru": ["Арендная плата за помещение"]},
    "tax": {"uz": ["Soliq toʻlovi (aylanmadan)"], "uzc": ["Солиқ тўлови (айланмадан)"], "ru": ["Уплата налога с оборота"]},
    "utilities": {"uz": ["Kommunal xizmatlar uchun toʻlov"], "uzc": ["Коммунал хизматлар учун тўлов"], "ru": ["Оплата коммунальных услуг"]},
    "loan_payment": {"uz": ["Kredit boʻyicha toʻlov, shartnoma №{n}"], "uzc": ["Кредит бўйича тўлов, шартнома №{n}"], "ru": ["Погашение кредита по договору №{n}"]},
    "cash_withdrawal": {"uz": ["Naqd pul yechish"], "uzc": ["Нақд пул ечиш"], "ru": ["Снятие наличных"]},
    "cash_deposit": {"uz": ["Kassaga naqd pul kiritish"], "uzc": ["Кассага нақд пул киритиш"], "ru": ["Взнос наличных в кассу"]},
    "owner_transfer": {"uz": ["Taʼsischiga oʻtkazma"], "uzc": ["Таъсисчига ўтказма"], "ru": ["Перевод учредителю"]},
    "owner_inflow": {"uz": ["Taʼsischidan qarz mablagʻi"], "uzc": ["Таъсисчидан қарз маблағи"], "ru": ["Заём от учредителя"]},
    "loan_disbursement": {"uz": ["Kredit mablagʻi berildi, shartnoma №{n}"], "uzc": ["Кредит маблағи берилди, шартнома №{n}"], "ru": ["Выдача кредита по договору №{n}"]},
    "bank_fee": {"uz": ["Bank xizmati komissiyasi"], "uzc": ["Банк хизмати комиссияси"], "ru": ["Комиссия банка за обслуживание"]},
}
CATEGORIES = list(PURPOSE)
INFLOW_OPERATING = {"sales_receipt", "cash_deposit"}

LABELS = {
    "stmt_title": {"uz": "HISOB RAQAMI BOʻYICHA KOʻCHIRMA", "uzc": "ҲИСОБ РАҚАМИ БЎЙИЧА КЎЧИРМА", "ru": "ВЫПИСКА ПО РАСЧЁТНОМУ СЧЁТУ"},
    "holder": {"uz": "Hisob egasi", "uzc": "Ҳисоб эгаси", "ru": "Владелец счёта"},
    "tin": {"uz": "STIR", "uzc": "СТИР", "ru": "ИНН"},
    "account": {"uz": "Hisob raqami", "uzc": "Ҳисоб рақами", "ru": "Номер счёта"},
    "bank": {"uz": "Bank", "uzc": "Банк", "ru": "Банк"},
    "period": {"uz": "Davr", "uzc": "Давр", "ru": "Период"},
    "opening": {"uz": "Davr boshiga qoldiq", "uzc": "Давр бошига қолдиқ", "ru": "Остаток на начало периода"},
    "closing": {"uz": "Davr oxiriga qoldiq", "uzc": "Давр охирига қолдиқ", "ru": "Остаток на конец периода"},
    "col_date": {"uz": "Sana", "uzc": "Сана", "ru": "Дата"},
    "col_doc": {"uz": "Hujjat", "uzc": "Ҳужжат", "ru": "Документ"},
    "col_cp": {"uz": "Kontragent / maqsad", "uzc": "Контрагент / мақсад", "ru": "Корреспондент / назначение"},
    "col_debit": {"uz": "Debet", "uzc": "Дебет", "ru": "Дебет"},
    "col_credit": {"uz": "Kredit", "uzc": "Кредит", "ru": "Кредит"},
    "col_balance": {"uz": "Qoldiq", "uzc": "Қолдиқ", "ru": "Остаток"},
    "currency": {"uz": "soʻm", "uzc": "сўм", "ru": "сум"},
    "decl_title": {"uz": "AYLANMADAN SOLIQ TOʻLOVCHISINING HISOBOTI", "uzc": "АЙЛАНМАДАН СОЛИҚ ТЎЛОВЧИСИНИНГ ҲИСОБОТИ", "ru": "ОТЧЁТ ПЛАТЕЛЬЩИКА НАЛОГА С ОБОРОТА"},
    "taxpayer": {"uz": "Soliq toʻlovchi", "uzc": "Солиқ тўловчи", "ru": "Налогоплательщик"},
    "decl_period": {"uz": "Hisobot davri", "uzc": "Ҳисобот даври", "ru": "Отчётный период"},
    "rev_q1": {"uz": "1-chorak boʻyicha tushum", "uzc": "1-чорак бўйича тушум", "ru": "Выручка за 1-й квартал"},
    "rev_q2": {"uz": "2-chorak boʻyicha tushum", "uzc": "2-чорак бўйича тушум", "ru": "Выручка за 2-й квартал"},
    "rev_total": {"uz": "Jami tushum", "uzc": "Жами тушум", "ru": "Итого выручка"},
    "tax_rate": {"uz": "Soliq stavkasi (%)", "uzc": "Солиқ ставкаси (%)", "ru": "Налоговая ставка (%)"},
    "tax_amount": {"uz": "Hisoblangan soliq summasi", "uzc": "Ҳисобланган солиқ суммаси", "ru": "Исчисленная сумма налога"},
    "employees": {"uz": "Xodimlar soni", "uzc": "Ходимлар сони", "ru": "Среднесписочная численность"},
    "submitted": {"uz": "Topshirilgan sana", "uzc": "Топширилган сана", "ru": "Дата подачи"},
    "reg_title": {"uz": "YURIDIK SHAXS / YaTT DAVLAT ROʻYXATIDAN OʻTKAZILGANLIGI TOʻGʻRISIDA MAʼLUMOTNOMA",
                  "uzc": "ЮРИДИК ШАХС / ЯТТ ДАВЛАТ РЎЙХАТИДАН ЎТКАЗИЛГАНЛИГИ ТЎҒРИСИДА МАЪЛУМОТНОМА",
                  "ru": "СПРАВКА О ГОСУДАРСТВЕННОЙ РЕГИСТРАЦИИ ЮРИДИЧЕСКОГО ЛИЦА / ИП"},
    "org_name": {"uz": "Tashkilot nomi", "uzc": "Ташкилот номи", "ru": "Наименование"},
    "reg_date": {"uz": "Roʻyxatdan oʻtgan sana", "uzc": "Рўйхатдан ўтган сана", "ru": "Дата регистрации"},
    "activity": {"uz": "Asosiy faoliyat turi", "uzc": "Асосий фаолият тури", "ru": "Основной вид деятельности"},
    "director": {"uz": "Rahbar", "uzc": "Раҳбар", "ru": "Руководитель"},
    "address": {"uz": "Manzil", "uzc": "Манзил", "ru": "Адрес"},
    "phone": {"uz": "Telefon", "uzc": "Телефон", "ru": "Телефон"},
}

BANKS = ["MKBANK", "Milliy Bank", "Hamkor Bank", "Ipak Yoʻli Banki", "Asia Alliance Bank", "Xalq Banki"]


def L(key: str, lang: str) -> str:
    return LABELS[key][lang]


_NORM = re.compile(r"[ʻʼ`´‘’']")


def norm_apos(s: str) -> str:
    return _NORM.sub("'", s)
