from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException, Query

from .config import settings
from .db import User, session

TTL = 60 * 60 * 24 * 3


def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(12)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 13, r=8, p=1, dklen=32)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_pw(pw: str, stored: str) -> bool:
    salt_b64, _ = stored.split("$")
    return hmac.compare_digest(hash_pw(pw, base64.b64decode(salt_b64)), stored)


def make_token(username: str, role: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(dict(u=username, r=role, e=int(time.time()) + TTL)).encode()).decode()
    sig = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_token(tok: str) -> dict | None:
    try:
        body, sig = tok.rsplit(".", 1)
        exp = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, exp):
            return None
        d = json.loads(base64.urlsafe_b64decode(body))
        return d if d["e"] > time.time() else None
    except Exception:  # noqa: BLE001
        return None


def current_user(authorization: str | None = Header(None), t: str | None = Query(None)) -> dict:
    tok = (authorization or "").removeprefix("Bearer ").strip() or (t or "")
    d = read_token(tok) if tok else None
    if not d:
        raise HTTPException(401, "not authenticated")
    return dict(username=d["u"], role=d["r"])


def require_role(*roles: str):
    def dep(user: dict = Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, f"requires role: {', '.join(roles)}")
        return user
    return dep


def new_guest() -> tuple[str, str]:
    name = "guest-" + secrets.token_hex(3)
    with session() as s:
        s.add(User(username=name, name="Demo officer", role="officer", password_hash="x$x"))
    return name, make_token(name, "officer")


DEMO = [("officer1", "Officer (demo)", "officer"), ("committee1", "Credit committee (demo)", "committee"),
        ("admin1", "Administrator (demo)", "admin")]
DEMO_PASSWORD = "creditgateway"


def seed_users():
    with session() as s:
        for u, n, r in DEMO:
            if not s.query(User).filter_by(username=u).first():
                s.add(User(username=u, name=n, role=r, password_hash=hash_pw(DEMO_PASSWORD)))
