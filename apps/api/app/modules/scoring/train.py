"""Train the monotone-constrained LightGBM scorer on the synthetic set and write a model card.

Run:  uv run python -m app.modules.scoring.train --n 30000
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from ...config import settings
from . import features as F
from .dataset import build_dataset


def ks_stat(y, p) -> float:
    d = pd.DataFrame({"y": y, "p": p}).sort_values("p", ascending=False)
    cum_bad = (d.y.cumsum() / max(d.y.sum(), 1)).values
    cum_good = ((1 - d.y).cumsum() / max((1 - d.y).sum(), 1)).values
    return float(np.max(np.abs(cum_bad - cum_good)))


def main(n: int = 30000):
    path = settings.data_dir / f"train_{n}.pkl"
    df = pd.read_pickle(path) if path.exists() else build_dataset(n, path)
    X, y = df[F.NAMES], df.y.values
    idx = np.arange(len(df))
    rng = np.random.default_rng(0)
    rng.shuffle(idx)
    n_tr, n_va = int(0.7 * len(df)), int(0.15 * len(df))
    tr, va, te = idx[:n_tr], idx[n_tr:n_tr + n_va], idx[n_tr + n_va:]
    params = dict(objective="binary", learning_rate=0.04, num_leaves=15, min_data_in_leaf=80, feature_fraction=0.85,
                  bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, monotone_constraints=F.MONOTONE,
                  monotone_constraints_method="advanced", verbose=-1, seed=7)
    dtr, dva = lgb.Dataset(X.iloc[tr], y[tr]), lgb.Dataset(X.iloc[va], y[va])
    booster = lgb.train(params, dtr, num_boost_round=1500, valid_sets=[dva],
                        callbacks=[lgb.early_stopping(60, verbose=False)])
    p_te = booster.predict(X.iloc[te], num_iteration=booster.best_iteration)
    # baselines
    sc = StandardScaler().fit(X.iloc[tr])
    lr = LogisticRegression(max_iter=2000, C=0.5).fit(sc.transform(X.iloc[tr]), y[tr])
    p_lr = lr.predict_proba(sc.transform(X.iloc[te]))[:, 1]
    dscr_only = -X.iloc[te]["dscr"].values
    # calibration table (deciles of predicted PD)
    cal = pd.DataFrame({"p": p_te, "y": y[te]})
    cal["bin"] = pd.qcut(cal.p, 10, duplicates="drop")
    calib = [dict(pred=float(g.p.mean()), obs=float(g.y.mean()), n=int(len(g))) for _, g in cal.groupby("bin", observed=True)]
    qs = np.quantile(p_te, [0.35, 0.65, 0.85, 0.95])
    imp = booster.feature_importance(importance_type="gain")
    card = dict(
        data=dict(kind="SYNTHETIC (declared in README)", n_sme=int(len(df)), n_transactions=int(df.n_tx.sum()),
                  default_rate=float(y.mean()), split=dict(train=len(tr), valid=len(va), test=len(te))),
        metrics=dict(auc_lightgbm=float(roc_auc_score(y[te], p_te)), ks_lightgbm=ks_stat(y[te], p_te),
                     brier_lightgbm=float(brier_score_loss(y[te], p_te)),
                     auc_logistic_baseline=float(roc_auc_score(y[te], p_lr)),
                     auc_dscr_only_baseline=float(roc_auc_score(y[te], dscr_only))),
        calibration=calib, band_cutoffs=[float(q) for q in qs], bands=["A", "B", "C", "D", "E"],
        feature_importance={n: float(v) for n, v in sorted(zip(F.NAMES, imp), key=lambda t: -t[1])},
        monotone={n: s for n, s in zip(F.NAMES, F.MONOTONE)}, best_iteration=int(booster.best_iteration),
        caveat="Labels come from a simulated default process whose drivers are partly unobservable. "
               "AUC measures how well the pipeline recovers that process; it is NOT a claim about real "
               "Uzbek SME default prediction.",
    )
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(settings.models_dir / "scorer.txt"), num_iteration=booster.best_iteration)
    (settings.models_dir / "model_card.json").write_text(json.dumps(card, indent=1))
    print(json.dumps(card["metrics"], indent=1), "bands", card["band_cutoffs"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30000)
    main(ap.parse_args().n)
