"""OCRGate step 1: get words, lines and bounding boxes out of a PDF or image.

Digital PDFs use the text layer (exact). Scans and photos go through Tesseract (uzb + uzb_cyrl + rus).
"""
from __future__ import annotations

import io
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps

from ...config import settings

os.environ.setdefault("TESSDATA_PREFIX", str(settings.tessdata_dir))
# Pages are OCR'd in parallel processes; Tesseract's own OpenMP threads on top of that oversubscribe the CPU
# (measured: a 6-page scan took >10 min instead of ~20 s in a CPU-limited container).
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
PAGE_TIMEOUT_S = 120
OCR_LANGS = "uzb+uzb_cyrl+rus"


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 100.0


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float
    words: list[Word] = field(default_factory=list)

    @property
    def bbox(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class Page:
    index: int
    width: float
    height: float
    lines: list[Line]
    source: str  # text_layer | ocr
    mean_conf: float
    ocr_seconds: float = 0.0


def _cluster_lines(words: list[Word], tol: float | None) -> list[Line]:
    if tol is None:  # OCR: tolerance relative to glyph height (photos jitter more than clean scans)
        hs = sorted(w.y1 - w.y0 for w in words) or [8.0]
        tol = max(2.5, 0.6 * hs[len(hs) // 2])
    words = sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    lines: list[list[Word]] = []
    centers: list[float] = []
    for w in words:
        cy = (w.y0 + w.y1) / 2
        if lines and abs(cy - centers[-1]) <= tol:
            lines[-1].append(w)
            centers[-1] = (centers[-1] * (len(lines[-1]) - 1) + cy) / len(lines[-1])
        else:
            lines.append([w])
            centers.append(cy)
    out = []
    for ws in lines:
        ws.sort(key=lambda w: w.x0)
        # join words; keep wide gaps as double space so column structure survives in text
        parts = [ws[0].text]
        for a, b in zip(ws, ws[1:]):
            gap = b.x0 - a.x1
            parts.append(("  " if gap > 2.2 * max(3.0, (a.y1 - a.y0) * 0.6) else " ") + b.text)
        conf = sum(w.conf for w in ws) / len(ws)
        out.append(Line("".join(parts), min(w.x0 for w in ws), min(w.y0 for w in ws), max(w.x1 for w in ws),
                        max(w.y1 for w in ws), conf, ws))
    return out


def _text_layer_page(page: pymupdf.Page, idx: int) -> Page | None:
    words = [Word(w[4], w[0], w[1], w[2], w[3]) for w in page.get_text("words") if w[4].strip()]
    if len(words) < 12:
        return None
    return Page(idx, page.rect.width, page.rect.height, _cluster_lines(words, tol=2.4), "text_layer", 100.0)


def estimate_skew(gray: Image.Image) -> float:
    """Projection-profile skew estimate in degrees (positive = text rotated counter-clockwise)."""
    import numpy as np
    small = gray.copy()
    small.thumbnail((900, 900))
    a = np.asarray(small, dtype=np.float32)
    bw = Image.fromarray(((a < a.mean() * 0.85) * 255).astype("uint8"))

    def score(angle: float) -> float:
        r = np.asarray(bw.rotate(angle, resample=Image.BILINEAR), dtype=np.float32).sum(axis=1)
        return float(np.var(r))

    best = max((score(a_), a_) for a_ in np.arange(-4.0, 4.01, 0.5))[1]
    best = max((score(a_), a_) for a_ in np.arange(best - 0.5, best + 0.51, 0.1))[1]
    return float(best)


UPSCALE = 1.5


def preprocess(img: Image.Image) -> Image.Image:
    """Uneven-lighting removal + upscale + sharpen + binarise. Turns phone photos from unreadable to readable."""
    import numpy as np
    from PIL import ImageFilter
    img = img.resize((int(img.width * UPSCALE), int(img.height * UPSCALE)), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float32)
    back = np.asarray(img.filter(ImageFilter.GaussianBlur(30)), dtype=np.float32) + 1
    n = np.clip(arr / back, 0, 1.2) / 1.2
    n = (n - n.min()) / (n.max() - n.min() + 1e-6)
    out = Image.fromarray((n * 255).astype("uint8")).filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))
    return out.point(lambda p: 255 if p > 150 else 0)


def _ocr_image(img: Image.Image, idx: int, scale_to_pt: float) -> Page:
    import math
    t0 = time.time()
    img = ImageOps.autocontrast(img.convert("L"))
    angle = estimate_skew(img) if min(img.size) > 300 else 0.0
    W, H = img.size
    if abs(angle) >= 0.3:
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    try:
        data = pytesseract.image_to_data(preprocess(img), lang=OCR_LANGS, config="--psm 6", output_type=pytesseract.Output.DICT, timeout=PAGE_TIMEOUT_S)
    except RuntimeError:  # page timed out: return it empty so the case is flagged for the officer instead of hanging
        data = {k: [] for k in ("text", "conf", "left", "top", "width", "height")}
    words = []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = 0.0
        if conf < 0:
            continue
        x, y, w, h = (data["left"][i] / UPSCALE, data["top"][i] / UPSCALE, data["width"][i] / UPSCALE, data["height"][i] / UPSCALE)
        if abs(angle) >= 0.3:  # map the box centre back to the un-rotated page so overlays line up
            cx, cy = x + w / 2 - W / 2, y + h / 2 - H / 2
            th = math.radians(-angle)
            ox = cx * math.cos(th) - cy * math.sin(th) + W / 2
            oy = cx * math.sin(th) + cy * math.cos(th) + H / 2
            x, y = ox - w / 2, oy - h / 2
        words.append(Word(txt, x * scale_to_pt, y * scale_to_pt, (x + w) * scale_to_pt, (y + h) * scale_to_pt, conf))
    lines = _cluster_lines(words, tol=None)
    mean = sum(w.conf for w in words) / len(words) if words else 0.0
    return Page(idx, W * scale_to_pt, H * scale_to_pt, lines, "ocr", mean, time.time() - t0)


def read_document(path: Path, dpi: int = 200, max_pages: int = 40) -> list[Page]:
    suffix = path.suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        scale = 72.0 / dpi
        return [_ocr_image(img, 0, scale)]
    doc = pymupdf.open(path)
    pages: dict[int, Page] = {}
    todo: list[tuple[int, bytes, float, float]] = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        p = _text_layer_page(page, i)
        if p is None:
            todo.append((i, page.get_pixmap(dpi=dpi).tobytes("png"), page.rect.width, page.rect.height))
        else:
            pages[i] = p

    def run(item):
        i, png, w, h = item
        p = _ocr_image(Image.open(io.BytesIO(png)), i, 72.0 / dpi)
        p.width, p.height = w, h
        return i, p

    if todo:
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as ex:  # tesseract is a subprocess: threads scale
            for i, p in ex.map(run, todo):
                pages[i] = p
    return [pages[i] for i in sorted(pages)]


def page_image_png(path: Path, index: int, dpi: int = 110) -> bytes:
    suffix = path.suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((1400, 1900))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    doc = pymupdf.open(path)
    return doc[index].get_pixmap(dpi=dpi).tobytes("png")


# --- language & script ---------------------------------------------------------------
_UZ_CYR_SPECIFIC = re.compile(r"[ўқғҳЎҚҒҲ]|бўйича|тўлов|ҳисоб|шартнома|солиқ|нақд")
_UZ_LAT_APOS = re.compile(r"[oOgG][ʻʼ'‘’`]|\b(to|bo)['ʻʼ‘’]?[lg]|shartnoma|hisob|toʻlov|soliq|naqd|kredit|qoldiq", re.I)
_RU = re.compile(r"оплата|договор|выписка|остаток|назначение|счёт|счет|налог|выручка|регистрац", re.I)


def detect_language(text: str) -> str:
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr + lat < 20:
        return "unknown"
    if cyr > lat * 1.2:
        uz_hits = len(_UZ_CYR_SPECIFIC.findall(text))
        ru_hits = len(_RU.findall(text))
        return "uzc" if uz_hits > ru_hits else "ru"
    if lat > cyr * 1.2:
        return "uz"
    return "mixed"


def full_text(pages: list[Page]) -> str:
    return "\n".join(l.text for p in pages for l in p.lines)
