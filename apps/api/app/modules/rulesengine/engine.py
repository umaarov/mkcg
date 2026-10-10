"""RulesEngine: policy-as-data. Every outcome cites the rule id and the evidence value."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

POLICY_PATH = Path(__file__).with_name("policy.yaml")


@lru_cache(maxsize=1)
def load_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text())


def _eval_rule(rule: dict, ctx: dict) -> dict:
    metric = rule["metric"]
    val = ctx.get(metric)
    out = dict(id=rule["id"], metric=metric, label=rule["label"], hard=rule.get("hard", False), kind=rule["kind"],
               value=val, refer=rule.get("refer"), fail=rule.get("fail"), lo=rule.get("lo"), hi=rule.get("hi"))
    if val is None:
        return {**out, "outcome": "REFER", "note": "metric unavailable"}
    kind = rule["kind"]
    if kind == "bool":
        outcome = "PASS" if val else "FAIL"
    elif kind == "range":
        outcome = "PASS" if rule["lo"] <= val <= rule["hi"] else "FAIL"
    elif kind == "min":
        outcome = "PASS" if val >= rule["refer"] else ("REFER" if val >= rule["fail"] else "FAIL")
    elif kind == "max":
        outcome = "PASS" if val <= rule["refer"] else ("REFER" if val <= rule["fail"] else "FAIL")
    else:
        raise ValueError(kind)
    return {**out, "outcome": outcome, "note": ""}


def evaluate(ctx: dict) -> dict:
    pol = load_policy()
    results = [_eval_rule(r, ctx) for r in pol["rules"]]
    hard_fail = [r for r in results if r["outcome"] == "FAIL" and r["hard"]]
    soft_fail = [r for r in results if r["outcome"] == "FAIL" and not r["hard"]]
    refers = [r for r in results if r["outcome"] == "REFER"]
    if hard_fail:
        rec, why = "DECLINE", "hard rule failed"
    elif soft_fail or len(refers) >= 3:
        rec, why = "REFER", "soft rule failed or multiple referrals"
    elif refers:
        rec, why = "REVIEW", "minor referrals"
    else:
        rec, why = "APPROVE", "all rules passed"
    return dict(results=results, recommendation=rec, reason=why, policy_version=pol["version"],
                counts=dict(pass_=sum(r["outcome"] == "PASS" for r in results), refer=len(refers),
                            fail=len(hard_fail) + len(soft_fail)))
