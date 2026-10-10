"""Scan / phone-photo degradation of rendered pages."""
from __future__ import annotations

import io
import random
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageFilter

PROFILES = {
    # name: (dpi, rotation_deg, blur_px, noise_sigma, jpeg_q, contrast, brightness_gradient)
    "scan": (170, 0.7, 0.55, 5, 72, 0.95, 0.04),
    "photo": (160, 2.2, 1.05, 9, 55, 0.82, 0.16),
}


def degrade_pdf(src: Path, dst_pdf: Path, profile: str, seed: int) -> int:
    dpi, rot, blur, sigma, q, contrast, grad = PROFILES[profile]
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    doc = fitz.open(src)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        angle = rng.uniform(-rot, rot)
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(250, 250, 248))
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur * rng.uniform(0.7, 1.2)))
        a = np.asarray(img).astype(np.float32)
        a = (a - 128) * contrast + 128
        h, w = a.shape[:2]
        ramp = np.linspace(1 - grad, 1 + grad * 0.3, w, dtype=np.float32)[None, :, None]
        a = a * ramp
        a += nrng.normal(0, sigma, a.shape)
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q)
        buf.seek(0)
        pages.append(Image.open(buf).convert("RGB"))
    pages[0].save(dst_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return len(pages)
