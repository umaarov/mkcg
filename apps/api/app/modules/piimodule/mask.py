"""PIIModule: reversible masking of identifiers before any text leaves the perimeter.

Entities: taxpayer IDs (9 digits), PINFL (14), account numbers (20, grouped or not), card numbers (16),
phones (+998...), e-mails, and person names (labelled directors/owners, sole-proprietor names).
The mapping never leaves the host. Recall is measured on synthetic documents in eval/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PHONE = re.compile(r"\+?998[\s\-()]*\d{2}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
ACCOUNT = re.compile(r"(?<!\d)(?:\d{4}[ ]){4}\d{4}(?!\d)|(?<!\d)\d{20}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{4}(?!\d)")
PINFL = re.compile(r"(?<!\d)\d{14}(?!\d)")
TIN = re.compile(r"(?<!\d)\d{9}(?!\d)")
WS = re.compile(r"\s+")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# names: sole proprietor (YaTT / ИП / ЯТТ) + 2-3 capitalised words, or after a director/owner label
CAP = r"[A-ZА-ЯЎҚҒҲ][a-zа-яёўқғҳʻʼ'’\-]{2,}"
NAME_AFTER_FORM = re.compile(rf"(?:YaTT|ЯТТ|ИП|IP)\s+({CAP}(?:\s+{CAP}){{1,2}})")
NAME_AFTER_LABEL = re.compile(
    rf"(?:Rahbar|Раҳбар|Руководитель|Direktor|Директор|Hisob egasi|Ҳисоб эгаси|Владелец счёта|Taʼsischi|Таъсисчи|Учредитель)\s*:\s*(?:(?:YaTT|ЯТТ|ИП)\s+)?({CAP}(?:\s+{CAP}){{1,2}})")


@dataclass
class Masker:
    mapping: dict[str, str] = field(default_factory=dict)  # token -> original
    _rev: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def _tok(self, kind: str, original: str) -> str:
        key = kind + ":" + WS.sub(" ", original).strip()
        if key in self._rev:
            return self._rev[key]
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        tok = f"[{kind}_{n}]"
        self.mapping[tok] = original
        self._rev[key] = tok
        return tok

    def mask(self, text: str) -> str:
        t = text
        for m in sorted({m.group(1) for rx in (NAME_AFTER_FORM, NAME_AFTER_LABEL) for m in rx.finditer(t)}, key=len, reverse=True):
            t = t.replace(m, self._tok("PERSON", m))
        t = EMAIL.sub(lambda m: self._tok("EMAIL", m.group(0)), t)
        t = PHONE.sub(lambda m: self._tok("PHONE", m.group(0)), t)
        t = CARD.sub(lambda m: self._tok("CARD", m.group(0)), t)
        t = ACCOUNT.sub(lambda m: self._tok("ACCOUNT", m.group(0)), t)
        t = PINFL.sub(lambda m: self._tok("PINFL", m.group(0)), t)
        t = TIN.sub(lambda m: self._tok("TIN", m.group(0)), t)
        return t

    def unmask(self, text: str) -> str:
        for tok, orig in self.mapping.items():
            text = text.replace(tok, orig)
        return text


def residual_pii(masked: str, secrets: list[str]) -> list[str]:
    """Which known secrets still appear in the masked text (used by the eval harness)."""
    flat = re.sub(r"\s+", "", masked)
    return [s for s in secrets if re.sub(r"\s+", "", s) and re.sub(r"\s+", "", s) in flat]
