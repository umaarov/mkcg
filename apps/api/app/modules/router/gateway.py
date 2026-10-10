"""Router: one door for every model call.

* decides local vs external per request (perimeter mode forbids external)
* enforces that only PIIModule-masked text is sent out (caller passes `masked=True`; unmasked is refused)
* meters latency, tokens and cost for every call
* degrades gracefully: no key and no local server => caller falls back to deterministic paths
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from threading import Lock

import httpx

from ...config import settings

_calls: list[dict] = []
_lock = Lock()


class RouterError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    seconds: float
    cost_usd: float
    json: dict | list | None = None


def status() -> dict:
    return dict(perimeter_mode=settings.perimeter_mode, external_available=bool(settings.anthropic_api_key) and not settings.perimeter_mode,
                local_available=bool(settings.local_base_url), extraction_model=settings.extraction_model,
                memo_model=settings.memo_model, local_model=settings.local_model)


def available() -> bool:
    s = status()
    return s["external_available"] or s["local_available"]


def _cost(model: str, tin: int, tout: int) -> float:
    pin = settings.price_in_per_m.get(model, 0.0)
    pout = settings.price_out_per_m.get(model, 0.0)
    return (tin * pin + tout * pout) / 1_000_000


def _log(entry: dict):
    with _lock:
        _calls.append(entry)
        del _calls[:-500]


def call_log() -> list[dict]:
    with _lock:
        return list(_calls)


def summary() -> dict:
    log = call_log()
    ext = [c for c in log if c["provider"] == "anthropic"]
    loc = [c for c in log if c["provider"] == "local"]
    return dict(calls=len(log), external=len(ext), local=len(loc), cost_usd=round(sum(c["cost_usd"] for c in log), 5),
                p50_s=_pct([c["seconds"] for c in log], 50), p95_s=_pct([c["seconds"] for c in log], 95),
                tokens_in=sum(c["tokens_in"] for c in log), tokens_out=sum(c["tokens_out"] for c in log))


def _pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * q / 100))], 2)


def complete(purpose: str, system: str, user: str, *, masked: bool, model: str | None = None,
             max_tokens: int = 2000, want_json: bool = False, prefer: str = "auto") -> LLMResult:
    if not masked:
        raise RouterError("refused: only PII-masked text may be sent to a model")
    use_local = bool(settings.local_base_url) and (prefer in ("auto", "local") or settings.perimeter_mode)
    use_ext = bool(settings.anthropic_api_key) and not settings.perimeter_mode and prefer in ("auto", "external")
    if prefer == "local":
        use_ext = False
    if prefer == "external":
        use_local = False
    if settings.perimeter_mode and not settings.local_base_url:
        raise RouterError("perimeter mode is on and no local model is configured")
    t0 = time.time()
    if use_ext and not (use_local and prefer == "local"):
        model = model or settings.extraction_model
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120,
                       headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"},
                       json=dict(model=model, max_tokens=max_tokens, system=system,
                                 messages=[dict(role="user", content=user)]))
        if r.status_code >= 400:
            raise RouterError(f"external model error {r.status_code}: {r.text[:200]}")
        d = r.json()
        text = "".join(b.get("text", "") for b in d["content"] if b["type"] == "text")
        tin, tout = d["usage"]["input_tokens"], d["usage"]["output_tokens"]
        provider = "anthropic"
    elif use_local:
        model = settings.local_model
        r = httpx.post(settings.local_base_url.rstrip("/") + "/chat/completions", timeout=300,
                       json=dict(model=model, max_tokens=max_tokens, temperature=0,
                                 messages=[dict(role="system", content=system), dict(role="user", content=user)]))
        if r.status_code >= 400:
            raise RouterError(f"local model error {r.status_code}: {r.text[:200]}")
        d = r.json()
        text = d["choices"][0]["message"]["content"]
        tin, tout = d.get("usage", {}).get("prompt_tokens", 0), d.get("usage", {}).get("completion_tokens", 0)
        provider = "local"
    else:
        raise RouterError("no model available")
    secs = time.time() - t0
    res = LLMResult(text, provider, model, tin, tout, round(secs, 2), _cost(model, tin, tout) if provider == "anthropic" else 0.0)
    if want_json:
        res.json = parse_json(text)
    _log(dict(ts=time.time(), purpose=purpose, provider=provider, model=model, tokens_in=tin, tokens_out=tout,
              seconds=res.seconds, cost_usd=res.cost_usd, masked=masked))
    return res


def parse_json(text: str):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise RouterError("no JSON in model output")
    end = max(body.rfind("}"), body.rfind("]"))
    return json.loads(body[start:end + 1])
