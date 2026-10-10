"""The deterministic fallback memo must always pass its own verifier, for every archetype and language."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.formalbrief import memo as memo_mod
from app.samples import ARCHETYPES


def test_abbreviation_does_not_split_a_cited_sentence():
    parts = memo_mod._sentences("Заявитель запрашивает 35 000 000 сум на 12 мес. [F01][F02], платёж 3 [F03]. Далее [F04].")
    assert len(parts) == 2 and parts[0].endswith("[F03].")


@pytest.mark.parametrize("archetype", list(ARCHETYPES))
def test_template_memos_verify_in_all_languages(archetype):
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/guest").json()["token"]}
        cid = c.post("/api/cases/sample", headers=h, json={"archetype": archetype, "lang": "en"}).json()["id"]
        for _ in range(120):
            if c.get(f"/api/cases/{cid}", headers=h).json()["status"] == "ANALYZED":
                break
            time.sleep(0.5)
        for lang in ("en", "uz", "ru"):
            m = c.post(f"/api/cases/{cid}/memo", headers=h, json={"lang": lang}).json()
            assert m["verifier"]["ok"], (archetype, lang, m["verifier"]["violations"])
