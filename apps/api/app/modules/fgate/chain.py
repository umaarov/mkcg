"""FGate: tamper-evident audit chain + Ed25519-signed decision dossier.

* every state change appends an event whose hash covers the previous hash (a hash chain)
* `verify_chain` recomputes the whole chain: editing or deleting any past row breaks it
* the dossier (everything an auditor needs to re-trace a decision) is canonical-JSON signed with Ed25519
  Production note: the key would live in the bank's HSM; the Uzbek e-signature (E-IMZO) is the integration target.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ...config import settings
from ...db import AuditEvent, now, session

_lock = threading.Lock()
GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash(prev: str, actor: str, action: str, case_id: str, ts: str, payload: str) -> str:
    return hashlib.sha256("|".join([prev, actor, action, case_id or "", ts, payload]).encode()).hexdigest()


def append(actor: str, action: str, case_id: str | None, payload: dict | None = None) -> dict:
    payload_s = canonical(payload or {})
    with _lock, session() as s:
        last = s.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
        prev = last.hash if last else GENESIS
        ts = now()
        h = _hash(prev, actor, action, case_id or "", ts.isoformat(), payload_s)
        ev = AuditEvent(ts=ts, actor=actor, action=action, case_id=case_id, payload=payload_s, prev_hash=prev, hash=h)
        s.add(ev)
        s.flush()
        return dict(id=ev.id, hash=h, prev_hash=prev)


def verify_chain() -> dict:
    with session() as s:
        rows = s.query(AuditEvent).order_by(AuditEvent.id).all()
        prev, bad = GENESIS, None
        for r in rows:
            exp = _hash(r.prev_hash, r.actor, r.action, r.case_id or "", r.ts.isoformat(), r.payload)
            if r.prev_hash != prev or r.hash != exp:
                bad = r.id
                break
            prev = r.hash
        return dict(ok=bad is None, events=len(rows), head=prev, first_bad_event=bad)


def events(case_id: str | None = None, limit: int = 200) -> list[dict]:
    with session() as s:
        q = s.query(AuditEvent)
        if case_id:
            q = q.filter(AuditEvent.case_id == case_id)
        rows = q.order_by(AuditEvent.id.desc()).limit(limit).all()
        return [dict(id=r.id, ts=r.ts.isoformat(), actor=r.actor, action=r.action, case_id=r.case_id,
                     payload=json.loads(r.payload), prev_hash=r.prev_hash, hash=r.hash) for r in rows]


# --- signing ----------------------------------------------------------------------------
def _key() -> Ed25519PrivateKey:
    p = settings.keys_dir / "ed25519.pem"
    if p.exists():
        return serialization.load_pem_private_key(p.read_bytes(), None)  # type: ignore[return-value]
    k = Ed25519PrivateKey.generate()
    p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    p.chmod(0o600)
    return k


def public_key_pem() -> str:
    return _key().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def fingerprint() -> str:
    raw = _key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:32]


def sign_dossier(dossier: dict) -> dict:
    body = canonical(dossier)
    sig = _key().sign(body.encode())
    return dict(dossier=dossier, signature=base64.b64encode(sig).decode(), algorithm="Ed25519",
                sha256=hashlib.sha256(body.encode()).hexdigest(), key_fingerprint=fingerprint())


def verify_signed(signed: dict) -> dict:
    try:
        body = canonical(signed["dossier"])
        sig = base64.b64decode(signed["signature"])
        _key().public_key().verify(sig, body.encode())
        ok = hashlib.sha256(body.encode()).hexdigest() == signed.get("sha256")
        return dict(valid=ok, key_fingerprint=fingerprint())
    except Exception as e:  # noqa: BLE001
        return dict(valid=False, error=type(e).__name__)
