from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

AMT_RE = re.compile(r"(?<![\w.,])([+\-\u2212\u2013])?\s?(\d{1,4}(?:[ ,\u00a0\u202f]\d{3})*[.,]\d{2}|\d{5,}[.,]\d{2})(?![\d])")
DATE_RE = re.compile(r"(?<!\d)(\d{2})[./-](\d{2})[./-](\d{4}|\d{2})(?!\d)|(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
TIN_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")

APOS = re.compile(r"[ʻʼ`´‘’']")


def norm_text(s: str) -> str:
    s = APOS.sub("'", s).lower().replace("ё", "е").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_amount(s: str) -> float:
    s = s.replace(" ", "").replace(" ", "").replace(" ", "")
    m = re.match(r"^(.*)[.,](\d{2})$", s)
    if not m:
        return float(re.sub(r"[^\d]", "", s) or 0)
    return float(re.sub(r"[^\d]", "", m.group(1)) or 0) + int(m.group(2)) / 100.0


def parse_date(s: str) -> str | None:
    m = DATE_RE.search(s)
    if not m:
        return None
    if m.group(1):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
    else:
        y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 1990 <= y <= 2100):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def best_label(left: str, variants: dict[str, list[str]], thresh: float = 0.78) -> tuple[str | None, float]:
    """Fuzzy-match the text left of a colon to a key. Tolerates OCR typos."""
    left_n = norm_text(left)
    if not left_n:
        return None, 0.0
    best_key, best = None, 0.0
    for key, vs in variants.items():
        for v in vs:
            vn = norm_text(v)
            score = SequenceMatcher(None, left_n, vn).ratio()
            if vn in left_n:
                score = max(score, 0.9 + 0.1 * min(1, len(vn) / max(len(left_n), 1)))
            if score > best:
                best_key, best = key, score
    return (best_key, best) if best >= thresh else (None, best)


@dataclass
class FieldOut:
    key: str
    value: str | float | int | None
    conf: float
    doc: str = ""
    page: int = 0
    bbox: list[float] | None = None
    source: str = "rule"  # rule | balance_chain | llm
    note: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class TxOut:
    idx: int
    date: str
    doc_no: str
    desc: str
    cp_name: str
    cp_tin: str
    debit: float
    credit: float
    balance: float
    category: str = ""
    conf: float = 1.0
    page: int = 0
    bbox: list[float] | None = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class DocResult:
    doc_type: str  # statement | declaration | registration | unknown
    lang: str
    source: str  # text_layer | ocr
    pages: int
    ocr_conf: float
    fields: list[FieldOut]
    transactions: list[TxOut]
    validations: list[dict]
    methods: dict
    seconds: float = 0.0
    llm_used: bool = False
