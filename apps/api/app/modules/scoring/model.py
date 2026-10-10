"""Scoring: load the booster, score a case, explain it with SHAP reason codes."""
from __future__ import annotations

import json
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import shap

from ...config import settings
from . import features as F


@lru_cache(maxsize=1)
def _load():
    path = settings.models_dir / "scorer.txt"
    if not path.exists():
        return None
    booster = lgb.Booster(model_file=str(path))
    card = json.loads((settings.models_dir / "model_card.json").read_text())
    return booster, shap.TreeExplainer(booster), card


def model_card() -> dict | None:
    m = _load()
    return m[2] if m else None


def band_for(pd_: float, cutoffs: list[float]) -> str:
    for b, c in zip("ABCD", cutoffs):
        if pd_ <= c:
            return b
    return "E"


def score(feats: dict[str, float], top_k: int = 4) -> dict:
    m = _load()
    if m is None:
        return dict(available=False, reason="model not trained")
    booster, explainer, card = m
    x = np.array([[feats[n] for n in F.NAMES]], dtype=float)
    pd_ = float(booster.predict(x)[0])
    sv = explainer.shap_values(x)
    sv = sv[1] if isinstance(sv, list) else sv
    contrib = sv[0]
    order = np.argsort(-np.abs(contrib))
    reasons = []
    for i in order:
        if len(reasons) >= top_k:
            break
        name = F.NAMES[i]
        if abs(contrib[i]) < 0.02:
            continue
        up = contrib[i] > 0
        sign, txt_up, txt_down = F.FEATURES[name]
        reasons.append(dict(feature=name, value=float(x[0, i]), contribution=float(contrib[i]),
                            direction="raises_risk" if up else "lowers_risk", text=txt_up if up else txt_down))
    base = float(np.ravel(explainer.expected_value)[-1])
    return dict(available=True, pd=pd_, band=band_for(pd_, card["band_cutoffs"]), reasons=reasons,
                base_logit=base, features=feats, model=dict(auc_test=card["metrics"]["auc_lightgbm"],
                                                         n_train_sme=card["data"]["n_sme"], synthetic=True))
