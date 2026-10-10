"""Sample applicants: curated archetypes + on-demand random synthetic bundles."""
from __future__ import annotations

import random
import shutil
from pathlib import Path

from .config import settings
from .datagen import bundle
from .datagen.sme import archetype_sme, random_sme

ARCHETYPES = {
    "strong": dict(seed=101, lang="uz", layout="A", degrade=None,
                   title={"en": "Established retailer, clean documents", "uz": "Barqaror chakana savdo, toza hujjatlar", "ru": "Устойчивая розница, чистые документы"}),
    "thin_file": dict(seed=202, lang="ru", layout="B", degrade="scan",
                      title={"en": "Thin file, scanned Russian documents", "uz": "Qisqa tarix, skan qilingan rus hujjatlari", "ru": "Тонкая история, сканы на русском"}),
    "inflated": dict(seed=303, lang="uzc", layout="C", degrade=None,
                     title={"en": "Inflated revenue + circular inflows", "uz": "Shishirilgan tushum + aylanma oqimlar", "ru": "Завышенная выручка + круговые потоки"}),
    "concentrated": dict(seed=404, lang="ru", layout="A", degrade=None,
                         title={"en": "One customer dominates", "uz": "Bitta mijoz ustun", "ru": "Доминирует один клиент"}),
    "declining": dict(seed=505, lang="uz", layout="B", degrade="scan",
                      title={"en": "Declining sales with existing debt (scan)", "uz": "Savdo pasaymoqda, qarz bor (skan)", "ru": "Падающие продажи и долг (скан)"}),
    "cash_heavy": dict(seed=606, lang="uz", layout="C", degrade="photo",
                       title={"en": "Cash-heavy, under-declared (phone photos)", "uz": "Naqd pul ko'p, kam deklaratsiya (telefon surati)", "ru": "Много наличных, занижено (фото)"}),
}


def samples_dir() -> Path:
    d = settings.data_dir / "samples"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_archetype(name: str) -> Path:
    cfg = ARCHETYPES[name]
    out = samples_dir() / name
    if not (out / "truth.json").exists():
        sme = archetype_sme(cfg["seed"], name, cfg["lang"])
        bundle.build_bundle(sme, cfg["seed"], out, layout=cfg["layout"], degrade=cfg["degrade"], lang=cfg["lang"])
    return out


def random_bundle(seed: int | None, lang: str | None, degrade: str | None) -> tuple[Path, dict]:
    seed = seed if seed is not None else random.randint(1_000_000, 9_999_999)
    sme = random_sme(seed, "random", lang)
    out = samples_dir() / f"rnd_{seed}"
    truth = bundle.build_bundle(sme, seed, out, degrade=degrade or None, lang=lang)
    return out, truth


def copy_into(case_dir: Path, src: Path) -> list[Path]:
    case_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for n in ("statement.pdf", "declaration.pdf", "registration.pdf"):
        dst = case_dir / n
        shutil.copy(src / n, dst)
        files.append(dst)
    return files
