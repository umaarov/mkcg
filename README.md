# CreditGateway

**An evidence-linked underwriting workbench for small-business lending in Uzbekistan.**
Loan officers upload an applicant's messy documents (bank statement, tax declaration, registration extract — Uzbek Latin, Uzbek Cyrillic or Russian, digital or scanned). CreditGateway reads them, checks them against each other, computes the affordability and risk numbers deterministically, drafts a credit memo whose every figure is machine-verified, and records the officer's decision in a tamper-evident audit chain with a signed dossier.

* **Mode:** Partner product. Owning unit: MKBANK small-business lending. Process changed: underwriting of microloans of the *Imkoniyat* type (up to 300 million UZS).
* **Track:** FinTech / AI in Finance. **Users:** loan officers, credit committee, risk/audit.
* **Not affiliated with or endorsed by MKBANK.** All data is synthetic. There is no pilot yet; the 3-month pilot plan is in `docs/BUSINESS_CASE.md`.

> The LLM never decides and never calculates. It reads (only as a fallback), and it writes (under a numeric verifier). Every number on screen is produced by deterministic code and links back to a highlighted region of the source document.

## Live demo
`https://<PUBLIC_HOST>` — click **Continue as demo officer**, then open a sample applicant. Demo accounts: `officer1`, `committee1`, `admin1` / `creditgateway`.

## Modules (all live in this repo)
| Module | What it does | Where |
|---|---|---|
| **OCRGate** | classify document, text layer or OCR (Tesseract uzb+uzb_cyrl+rus, deskew, lighting normalisation), deterministic parsers with *balance-chain repair*, optional LLM fallback | `app/modules/ocrgate` |
| **Statement** | multilingual payment-purpose categorisation, cash-flow analytics, circular-inflow detection, affordability | `app/modules/statement` |
| **RevenueGate** | declared revenue vs money that actually reached the account | `app/modules/revenuegate` |
| **RulesEngine** | 20 policy rules as YAML, PASS/REFER/FAIL with evidence | `app/modules/rulesengine` |
| **Scoring** | monotone-constrained LightGBM + SHAP reason codes | `app/modules/scoring` |
| **FormalBrief** | credit memo (uz/ru/en) with fact sheet, `[F##]` citations and a numeric verifier | `app/modules/formalbrief` |
| **PIIModule** | reversible masking of IDs, accounts, phones, PINFL, owner names before any model call | `app/modules/piimodule` |
| **Router** | single gateway for model calls: local vs external, perimeter mode, cost/latency metering | `app/modules/router` |
| **FGate** | SHA-256 hash-chained audit log, Ed25519-signed decision dossier, public verifier | `app/modules/fgate` |
| **Signals** | portfolio early-warning on a synthetic book of approved loans | `app/modules/signals` |

## Measured quality (our synthetic test set — `eval/`)
81 synthetic applicants × 3 documents, full factorial over degradation (clean / scan / phone photo) × language (uz-Latn, uz-Cyrl, ru) × layout (3). Deterministic parsers only, **no LLM**. Reproduce: `cd apps/api && uv run python ../../eval/run_eval.py --n 81`.

| Slice | Statement rows recovered | Row precision | Category acc. | Header fields | Declaration fields | Verdict unchanged | s/case (p50) |
|---|---|---|---|---|---|---|---|
| Digital PDF | 100.0% | 100.0% | 100.0% | 100% | 100% | 100% | 0.1 |
| Scan | 93.3% | 93.9% | 90.6% | 99% | 98% | 89% | 21.0 |
| **Phone photo (harsh synthetic)** | **32.5%** | 42.7% | 66.6% | 77% | 42% | 30% | 22.8 |

PII masking recall 98.7% over 623 identifier occurrences. Scoring model (synthetic labels): AUC 0.830 held-out vs 0.811 logistic and 0.694 DSCR-only, trained on 30,000 synthetic SMEs / 6,648,597 transactions. Signals: 57% of defaults flagged before they happen (median 3 months early) at a 6.9% false-alert rate on held-out loans.

### Known failure cases (we show them on purpose)
* **Phone photos at our harsh setting recover only about a third of statement rows** with rules alone. The system raises a data-quality flag (rule R20, banner on the case page) and tells the officer to re-capture or upload the PDF; on our test set **no extraction below 90 % row recall went unflagged (0 silent failures)** — but the flag is conservative: every scan and photo is flagged, so it is a safety net for the officer, not a precision tool (see the “Flagged / Silent failures” columns on the System page). The designed remedy is the LLM/VLM fallback (`ocrgate/llm_extract.py`, PII-masked). Its plumbing is covered by tests against a stub server (identifiers never reach the model and are restored locally; the memo verifier retries and falls back) — **the accuracy of a real model on these documents is not measured and not part of the numbers above.**
* Layouts are *approximations* we wrote; real bank/tax templates will differ. Unknown layouts are what the LLM fallback is for.
* The scoring model and Signals measure how well the pipeline recovers a **simulated** default process. They say nothing about real Uzbek SME default rates.
* PyMuPDF is AGPL-3.0; a production deployment needs its commercial licence or a swap to pypdfium2.

## Quick start
```bash
# one command (API + web), needs Docker
cp .env.example .env && echo "CG_SECRET_KEY=$(openssl rand -hex 24)" >> .env
docker compose up -d --build          # http://127.0.0.1:3101
docker compose --profile https up -d --build   # + automatic HTTPS for $PUBLIC_HOST

# development
sh scripts/get_tessdata.sh            # Tesseract uz/ru models (Apache-2.0)
brew install tesseract                # or: apt-get install tesseract-ocr
cd apps/api && uv sync && uv run uvicorn app.main:app --port 8101
cd apps/web && npm install && npm run dev      # http://localhost:3101  (proxies /api to :8101)
cd apps/api && uv run pytest -q                # 18 tests
```
Regenerate artifacts: `uv run python -m app.modules.scoring.train --n 30000`, `uv run python -m app.modules.signals.portfolio`, `uv run python ../../eval/run_eval.py --n 81`.

## Production design (customer data never leaves the bank)
Everything above runs on CPU inside the perimeter. Model calls go through **Router**; **perimeter mode** (toggle on the System page, `CG_PERIMETER_MODE`) refuses any external call and routes to a local OpenAI-compatible endpoint (vLLM/Ollama, `CG_LOCAL_BASE_URL`). Without any model, OCRGate falls back to rules, FormalBrief to its deterministic template — the product degrades, it does not stop. Human in the loop: officer must confirm low-confidence fields; approving against a Refer/Decline view needs the committee role (four-eyes) and a written reason; all of it lands in the FGate chain. See `docs/ARCHITECTURE.md`.

## Data sources and licences
See `docs/DATA_SOURCES.md`. Short version: **all applicant data is synthetic, generated by `app/datagen`** (method documented there); no real personal or confidential data is used anywhere; thresholds and pricing are our assumptions, not MKBANK policy.

## AI-assisted development and prior work
This repository was written during the final with an AI coding assistant (Claude Code); the team is able to explain and modify every part. No code from earlier projects is reused. The module separation idea is inspired by the author's earlier, unrelated private project; no code was copied.

## Cost and ROI
`docs/BUSINESS_CASE.md` and `scripts/roi.py` (all inputs are stated assumptions to be replaced in pilot week 1).

## Licence
MIT for our code. Third-party licences in `docs/DATA_SOURCES.md`.
