from __future__ import annotations

import copy
import json
import secrets
import shutil
import subprocess
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm.attributes import flag_modified

from . import auth, dossier, pipeline, samples
from .config import settings
from .db import Case, Document, User, init_db, now, session
from .modules.fgate import chain
from .modules.formalbrief import memo as memo_mod
from .modules.formalbrief.facts import Fact
from .modules.ocrgate.text import page_image_png
from .modules.router import gateway
from .modules.scoring import model as scorer
from .modules.signals import portfolio

app = FastAPI(title="CreditGateway API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_BYTES = 15 * 1024 * 1024
EVAL_PATH = Path(__file__).resolve().parents[3] / "eval" / "results" / "latest.json"


def _cleanup(days: int = 7):
    """Public demo hygiene: drop undecided cases and their files after a week."""
    import datetime as _dt
    cutoff = now() - _dt.timedelta(days=days)
    with session() as s:
        old = s.query(Case).filter(Case.created < cutoff, Case.decision.is_(None)).all()
        ids = [c.id for c in old]
        for c in old:
            s.delete(c)
    for i in ids:
        shutil.rmtree(settings.uploads_dir / i, ignore_errors=True)


@app.on_event("startup")
def _startup():
    init_db()
    auth.seed_users()
    chain._key()  # create the signing key early
    _cleanup()


# ---- auth -------------------------------------------------------------------------------
@app.post("/api/auth/login")
def login(body: dict = Body(...)):
    with session() as s:
        u = s.query(User).filter_by(username=body.get("username", "")).first()
        if not u or not auth.check_pw(body.get("password", ""), u.password_hash):
            raise HTTPException(401, "invalid credentials")
        tok = auth.make_token(u.username, u.role)
        out = dict(token=tok, username=u.username, name=u.name, role=u.role)
    chain.append(out["username"], "login", None, {})
    return out


@app.post("/api/auth/guest")
def guest():
    name, tok = auth.new_guest()
    chain.append(name, "guest_session", None, {})
    return dict(token=tok, username=name, name="Demo officer", role="officer")


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.current_user)):
    return user


# ---- helpers ----------------------------------------------------------------------------
def _own(case: Case, user: dict):
    if user["role"] != "admin" and case.owner != user["username"] and user["role"] != "committee":
        raise HTTPException(404, "case not found")


def _summary(c: Case) -> dict:
    r = c.result or {}
    return dict(id=c.id, applicant=c.applicant, tin=c.tin, amount=c.amount, term=c.term, status=c.status, lang=c.lang,
                created=c.created.isoformat(), owner=c.owner, sample=c.sample,
                recommendation=(r.get("rules") or {}).get("recommendation"), band=(r.get("score") or {}).get("band"),
                pd=(r.get("score") or {}).get("pd"), decision=(c.decision or {}).get("outcome"), verified=r.get("verified", False))


def _detail(c: Case) -> dict:
    d = _summary(c)
    d.update(result=c.result, steps=c.steps, decision=c.decision,
             docs=[dict(id=x.id, filename=x.filename, doc_type=x.doc_type, lang=x.lang, source=x.source, pages=x.pages,
                        ocr_conf=x.ocr_conf, seconds=x.seconds, extraction=x.extraction) for x in c.docs])
    return d


_recent: dict[str, list[float]] = {}


def _rate_limit(username: str):
    import time as _t
    now_ = _t.time()
    q = [x for x in _recent.get(username, []) if now_ - x < 3600]
    if len(q) >= settings.max_cases_per_hour:
        raise HTTPException(429, "rate limit: too many applications created in the last hour")
    q.append(now_)
    _recent[username] = q


def _new_case(user: dict, amount: float, term: int, lang: str, sample: str = "") -> Case:
    _rate_limit(user["username"])
    cid = "C" + secrets.token_hex(4).upper()
    c = Case(id=cid, owner=user["username"], amount=amount, term=term, lang=lang, sample=sample, status="UPLOADED", result={}, steps=[])
    return c


# ---- cases ------------------------------------------------------------------------------
@app.get("/api/cases")
def list_cases(user: dict = Depends(auth.current_user)):
    with session() as s:
        q = s.query(Case).order_by(Case.created.desc())
        if user["role"] not in ("admin", "committee"):
            q = q.filter(Case.owner == user["username"])
        return [_summary(c) for c in q.limit(100).all()]


@app.post("/api/cases")
async def create_case(files: list[UploadFile] = File(...), amount: float = Form(...), term: int = Form(...), lang: str = Form("uz"),
                      user: dict = Depends(auth.require_role("officer", "admin"))):
    if not (1 <= len(files) <= 6):
        raise HTTPException(400, "upload 1 to 6 files")
    # Read every upload BEFORE touching the database: a write transaction must never stay open across an await,
    # otherwise a second request blocks the event loop on SQLite's write lock while the first cannot resume (deadlock).
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED:
            raise HTTPException(400, f"unsupported file type {ext}")
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "file too large (15 MB max)")
        blobs.append((Path(f.filename or "doc").name, data))
    cid = await run_in_threadpool(_store_case, user, amount, term, lang, blobs)
    return dict(id=cid)


def _store_case(user: dict, amount: float, term: int, lang: str, blobs: list[tuple[str, bytes]]) -> str:
    with session() as s:
        case = _new_case(user, amount, term, lang)
        s.add(case)
        s.flush()
        cdir = settings.uploads_dir / case.id
        cdir.mkdir(parents=True, exist_ok=True)
        for name, data in blobs:
            p = cdir / name
            p.write_bytes(data)
            s.add(Document(case_id=case.id, filename=name, path=str(p)))
        cid = case.id
    chain.append(user["username"], "case_created", cid, dict(files=[n for n, _ in blobs], amount=amount, term=term))
    pipeline.submit_extraction(cid)
    return cid


@app.get("/api/samples")
def list_samples(user: dict = Depends(auth.current_user)):
    return [dict(key=k, **{kk: vv for kk, vv in v.items() if kk != "seed"}) for k, v in samples.ARCHETYPES.items()]


@app.post("/api/cases/sample")
def create_sample(body: dict = Body(...), user: dict = Depends(auth.require_role("officer", "admin"))):
    key = body.get("archetype")
    lang = body.get("lang", "uz")
    if key:
        if key not in samples.ARCHETYPES:
            raise HTTPException(400, "unknown archetype")
        src = samples.ensure_archetype(key)
        truth = json.loads((src / "truth.json").read_text())
        amount, term = truth["request"]["amount"], truth["request"]["term"]
    else:
        src, truth = samples.random_bundle(body.get("seed"), body.get("doc_lang"), body.get("degrade"))
        amount, term = truth["request"]["amount"], truth["request"]["term"]
    with session() as s:
        case = _new_case(user, amount, term, lang, sample=key or "random")
        s.add(case)
        s.flush()
        files = samples.copy_into(settings.uploads_dir / case.id, src)
        for p in files:
            s.add(Document(case_id=case.id, filename=p.name, path=str(p)))
        cid = case.id
    chain.append(user["username"], "case_created", cid, dict(sample=key or "random"))
    pipeline.submit_extraction(cid)
    return dict(id=cid)


@app.get("/api/cases/{cid}")
def get_case(cid: str, user: dict = Depends(auth.current_user)):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404, "case not found")
        _own(c, user)
        return _detail(c)


@app.delete("/api/cases/{cid}")
def delete_case(cid: str, user: dict = Depends(auth.require_role("officer", "admin"))):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404, "case not found")
        _own(c, user)
        if c.decision:
            raise HTTPException(409, "decided cases are retained for audit")
        s.delete(c)
    shutil.rmtree(settings.uploads_dir / cid, ignore_errors=True)
    chain.append(user["username"], "case_deleted", cid, {})
    return dict(ok=True)


@app.get("/api/cases/{cid}/docs/{did}/page/{n}.png")
def page_png(cid: str, did: int, n: int, user: dict = Depends(auth.current_user)):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        d = s.get(Document, did)
        if not d or d.case_id != cid:
            raise HTTPException(404)
        path = Path(d.path)
    return Response(page_image_png(path, n), media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@app.post("/api/cases/{cid}/verify")
def verify_case(cid: str, body: dict = Body(...), user: dict = Depends(auth.require_role("officer", "admin"))):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        if c.decision:
            raise HTTPException(409, "case already decided")
        n_changed = 0
        docs = {d.id: d for d in c.docs}
        for corr in body.get("corrections", []):
            d = docs.get(corr["doc_id"])
            if not d:
                continue
            ex = copy.deepcopy(d.extraction)
            for f in ex["fields"]:
                if f["key"] == corr["key"]:
                    if str(f["value"]) != str(corr["value"]):
                        f["verified_value"] = corr["value"]
                        n_changed += 1
                    f["verified_by"] = user["username"]
            d.extraction = ex
            flag_modified(d, "extraction")
        for tc in body.get("tx_categories", []):
            d = docs.get(tc["doc_id"])
            if not d:
                continue
            ex = copy.deepcopy(d.extraction)
            t = ex["transactions"][tc["idx"]]
            if t["category"] != tc["category"]:
                t["verified_category"] = tc["category"]
                n_changed += 1
            t["verified_by"] = user["username"]
            d.extraction = ex
            flag_modified(d, "extraction")
        if body.get("accept_all_low"):
            for d in docs.values():
                ex = copy.deepcopy(d.extraction)
                for f in ex.get("fields", []):
                    if f["conf"] < 0.85 and not f.get("verified_by"):
                        f["verified_by"] = user["username"]
                for t in ex.get("transactions", []):
                    if t["conf"] < 0.85 and not t.get("verified_by"):
                        t["verified_by"] = user["username"]
                d.extraction = ex
                flag_modified(d, "extraction")
        res = copy.deepcopy(c.result or {})
        res["verified"] = True
        res["verified_by"] = user["username"]
        c.result = res
        flag_modified(c, "result")
        s.commit()
    chain.append(user["username"], "fields_verified", cid, dict(changed=n_changed, accept_all=bool(body.get("accept_all_low"))))
    pipeline.run_analysis(cid)
    with session() as s:
        return _detail(s.get(Case, cid))


def _ctx_from(c: Case) -> tuple[dict, list[Fact]]:
    r = c.result
    ctx = dict(metrics=r["metrics"], afford=r["afford"], recon=r["recon"] or dict(gap_adj=1.0, verdict="consistent", declared_total=0, bank_inflow=0, roundtrip_amount=0),
               request=dict(amount=c.amount, term=c.term), score=r["score"], rules=r["rules"], business_age_months=r.get("business_age_months") or 0.0)
    facts = [Fact(**f) for f in r["facts"]]
    return ctx, facts


@app.post("/api/cases/{cid}/memo")
def make_memo(cid: str, body: dict = Body(...), user: dict = Depends(auth.require_role("officer", "admin", "committee"))):
    lang = body.get("lang", "en")
    if lang not in ("en", "uz", "ru"):
        raise HTTPException(400, "lang must be en|uz|ru")
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        if c.status not in ("ANALYZED", "DECIDED"):
            raise HTTPException(409, "analysis not ready")
        ctx, facts = _ctx_from(c)
        m = memo_mod.generate(ctx, facts, lang, use_llm=bool(body.get("use_llm", True)))
        res = copy.deepcopy(c.result)
        res.setdefault("memo", {})[lang] = m
        c.result = res
        flag_modified(c, "result")
    chain.append(user["username"], "memo_generated", cid, dict(lang=lang, writer=m["writer"], verifier_ok=m["verifier"]["ok"] if "verifier" in m else None))
    return m


@app.post("/api/cases/{cid}/whatif")
def whatif(cid: str, body: dict = Body(...), user: dict = Depends(auth.current_user)):
    """Re-price the same verified evidence for another amount/term. Nothing is persisted."""
    from .modules.rulesengine.engine import evaluate, load_policy
    from .modules.scoring import features as F
    from .modules.statement.analytics import affordability
    amount, term = float(body["amount"]), int(body["term"])
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        r = c.result or {}
        if "metrics" not in r:
            raise HTTPException(409, "analysis not ready")
        pol = load_policy()["pricing"]
        aff = affordability(r["metrics"], amount, term, pol["annual_rate"], pol["max_payment_share"])
        recon = r["recon"] or dict(gap_adj=1.0)
        feats = F.build(r["metrics"], aff, recon, r.get("business_age_months") or 0.0)
        sc = scorer.score(feats)
        ctx = dict(r["rules_ctx"], request_amount=amount, request_term=term, dscr=aff["dscr"], loan_to_annual_inflow=aff["loan_to_annual_inflow"])
        rules = evaluate(ctx)
        if sc.get("available") and rules["recommendation"] == "APPROVE" and sc["band"] in ("D", "E"):
            rules["recommendation"] = "REVIEW"
        return dict(afford=aff, score=dict(pd=sc.get("pd"), band=sc.get("band")), recommendation=rules["recommendation"],
                    counts=rules["counts"], failing=[x["id"] for x in rules["results"] if x["outcome"] == "FAIL"])


@app.post("/api/cases/{cid}/decision")
def decide(cid: str, body: dict = Body(...), user: dict = Depends(auth.require_role("officer", "committee", "admin"))):
    outcome = body.get("outcome")
    if outcome not in ("approve", "decline", "escalate"):
        raise HTTPException(400, "outcome must be approve|decline|escalate")
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        if c.status != "ANALYZED":
            raise HTTPException(409, "case is not ready for a decision")
        if not (c.result or {}).get("verified"):
            raise HTTPException(409, "officer verification of extracted fields is required before a decision")
        rec = c.result["rules"]["recommendation"]
        override = (outcome == "approve" and rec in ("REFER", "DECLINE")) or (outcome == "decline" and rec == "APPROVE")
        reason = (body.get("reason") or "").strip()
        if override and len(reason) < 10:
            raise HTTPException(422, "an override needs a written reason (10+ characters)")
        if outcome == "approve" and rec in ("REFER", "DECLINE") and user["role"] not in ("committee", "admin"):
            raise HTTPException(403, "approving against a REFER/DECLINE recommendation needs the credit committee role (four-eyes rule)")
        c.decision = dict(outcome=outcome, by=user["username"], role=user["role"], at=now().isoformat(), reason=reason,
                          override=override, recommendation=rec, policy_version=c.result["rules"]["policy_version"])
        c.status = "DECIDED"
        out = copy.deepcopy(c.decision)
    chain.append(user["username"], "decision", cid, out)
    return out


@app.get("/api/cases/{cid}/dossier")
def get_dossier(cid: str, user: dict = Depends(auth.current_user)):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        signed = chain.sign_dossier(dossier.build(c))
    chain.append(user["username"], "dossier_exported", cid, dict(sha256=signed["sha256"]))
    return signed


@app.post("/api/cases/{cid}/dossier.pdf")
def get_dossier_pdf(cid: str, user: dict = Depends(auth.current_user)):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
        signed = chain.sign_dossier(dossier.build(c))
    return Response(dossier.pdf_bytes(signed), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="dossier-{cid}.pdf"'})


@app.get("/api/cases/{cid}/audit")
def case_audit(cid: str, user: dict = Depends(auth.current_user)):
    with session() as s:
        c = s.get(Case, cid)
        if not c:
            raise HTTPException(404)
        _own(c, user)
    return chain.events(cid)


# ---- FGate ------------------------------------------------------------------------------
@app.get("/api/audit")
def audit(user: dict = Depends(auth.require_role("admin", "committee"))):
    return chain.events(None, 150)


@app.get("/api/fgate/verify-chain")
def verify_chain(user: dict = Depends(auth.current_user)):
    return chain.verify_chain()


@app.post("/api/fgate/verify")
def verify_signed(body: dict = Body(...)):
    return chain.verify_signed(body)


@app.get("/api/fgate/pubkey")
def pubkey():
    return dict(algorithm="Ed25519", fingerprint=chain.fingerprint(), pem=chain.public_key_pem())


# ---- system / eval / portfolio ------------------------------------------------------------
def _tess_version() -> str:
    try:
        return subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=5).stdout.splitlines()[0]
    except Exception:  # noqa: BLE001
        return "unavailable"


@app.get("/api/system/status")
def status(user: dict = Depends(auth.current_user)):
    card = scorer.model_card()
    return dict(router=gateway.status(), router_summary=gateway.summary(), model_card=card, chain=chain.verify_chain(),
                fgate=dict(fingerprint=chain.fingerprint()), ocr=dict(engine=_tess_version(), langs="uzb+uzb_cyrl+rus"),
                signals=bool(portfolio.load()), eval=EVAL_PATH.exists(), version="0.1")


@app.post("/api/system/perimeter")
def perimeter(body: dict = Body(...), user: dict = Depends(auth.require_role("admin"))):
    settings.perimeter_mode = bool(body.get("on"))
    chain.append(user["username"], "perimeter_mode", None, dict(on=settings.perimeter_mode))
    return gateway.status()


@app.get("/api/system/router-calls")
def router_calls(user: dict = Depends(auth.current_user)):
    return gateway.call_log()[-60:]


@app.get("/api/eval")
def eval_results(user: dict = Depends(auth.current_user)):
    if not EVAL_PATH.exists():
        raise HTTPException(404, "eval not run yet")
    out = json.loads(EVAL_PATH.read_text())
    llm = EVAL_PATH.with_name("latest_llm.json")
    if llm.exists():  # same seeds as the rules-only run, scan and photo slices, with the PII-masked LLM fallback enabled
        out["llm"] = json.loads(llm.read_text())
    return out


@app.get("/api/portfolio")
def get_portfolio(user: dict = Depends(auth.current_user)):
    p = portfolio.load()
    if not p:
        raise HTTPException(404, "signals not built")
    return p


@app.get("/api/health")
def health():
    return dict(ok=True)
