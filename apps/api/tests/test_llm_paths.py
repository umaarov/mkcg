"""LLM-path plumbing tests against a local stub of an OpenAI-compatible server.

These prove the wiring (PII masking before the call, JSON parsing, unmasking, verifier + retry, refusal of
unmasked text, perimeter mode). They say nothing about the quality of any real model.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.config import settings
from app.datagen import bundle
from app.datagen.sme import archetype_sme
from app.modules.formalbrief import memo as memo_mod
from app.modules.formalbrief.facts import Fact
from app.modules.ocrgate.llm_extract import llm_fallback
from app.modules.ocrgate.text import read_document
from app.modules.router import gateway


class Stub:
    def __init__(self):
        self.requests, self.replies = [], []
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append(body)
                text = stub.replies.pop(0) if stub.replies else "{}"
                out = json.dumps({"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"


@pytest.fixture()
def stub(monkeypatch):
    s = Stub()
    monkeypatch.setattr(settings, "local_base_url", s.url)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "perimeter_mode", False)
    yield s
    s.srv.shutdown()


def test_router_refuses_unmasked_text(stub):
    with pytest.raises(gateway.RouterError):
        gateway.complete("x", "sys", "user", masked=False)


def test_perimeter_mode_without_local_model_refuses(monkeypatch):
    monkeypatch.setattr(settings, "local_base_url", "")
    monkeypatch.setattr(settings, "perimeter_mode", True)
    with pytest.raises(gateway.RouterError):
        gateway.complete("x", "sys", "user", masked=True)


def test_extraction_fallback_masks_pii_and_restores_it(tmp_path, stub):
    sme = archetype_sme(11, "strong", "ru")
    truth = bundle.build_bundle(sme, 11, tmp_path, layout="B", lang="ru", with_outcome=False)
    pages = read_document(tmp_path / "registration.pdf")
    stub.replies = [json.dumps({"doc_type": "registration"}),
                    json.dumps({"org_name": "x", "tin": "[TIN_1]", "reg_date": truth["applicant"]["reg_date"], "pinfl": "[PINFL_1]"})]
    doc_type, fields, *_ = llm_fallback("unknown", pages, {}, [], [])
    assert doc_type == "registration"
    sent = json.dumps(stub.requests)
    assert truth["applicant"]["tin"] not in sent and truth["applicant"]["pinfl"] not in sent   # never left the host
    assert fields["tin"].value == truth["applicant"]["tin"]                                       # restored locally
    assert fields["tin"].source == "llm"


def test_llm_memo_retries_after_verifier_rejection(stub):
    facts = [Fact("F01", "request_amount", 35e6, "35 000 000", "UZS", {"en": "Requested"}), Fact("F02", "dscr", 1.42, "1.42", "x", {"en": "DSCR"})]
    ctx = dict(rules=dict(recommendation="APPROVE", results=[]), recon=dict(verdict="consistent"))
    tmpl = dict(sections=[dict(title="Summary", text="")])
    stub.replies = ["The DSCR is 9.99 [F02].", "The applicant asks 35 000 000 UZS [F01] and the DSCR is 1.42 [F02]."]
    out = memo_mod.llm_memo(ctx, facts, "en", tmpl)
    assert out and out["writer"] == "llm" and out["verifier"]["attempts"] == 2
    assert "rejected by the verifier" in stub.requests[1]["messages"][1]["content"]


def test_llm_memo_falls_back_when_model_keeps_inventing(stub):
    facts = [Fact("F01", "dscr", 1.42, "1.42", "x", {"en": "DSCR"})]
    ctx = dict(rules=dict(recommendation="APPROVE", results=[]), recon=dict(verdict="consistent"))
    stub.replies = ["DSCR 7.77 [F01].", "DSCR 8.88 [F01]."]
    assert memo_mod.llm_memo(ctx, facts, "en", dict(sections=[])) is None
