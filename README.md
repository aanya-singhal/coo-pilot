# CoO-PILOT

Certificate of Origin pre-clearance assistant. Reads trade documents, checks
them against each other and against published rules of origin, and routes each
case to approve, reject, or human review — showing its working at every step.

Built for SIH 2026.

```
documents ──▶ extraction ──▶ reconciliation ──▶ origin rules ──▶ risk ──▶ decision
              (Gemini)       (invoice ↔ PL)     (RVC + CTC)              + audit trail
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # add GEMINI_API_KEY
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

- API docs: <http://localhost:8000/docs>
- Dashboard: open `console.html` in a browser

Without Supabase credentials the backend runs on in-memory storage, so it
starts with no setup — data is lost on restart. For persistence, set
`SUPABASE_URL` / `SUPABASE_KEY` and run [`backend/db/schema.sql`](backend/db/schema.sql)
once in the Supabase SQL editor.

```bash
pytest        # 76 tests, no credentials needed
```

## Layout

| Path | What | Owner |
| --- | --- | --- |
| [`extraction/`](extraction/) | Gemini document extraction | Person 1 |
| [`rules/`](rules/README.md) | Reconciliation, origin criteria, risk | Person 2 |
| [`backend/`](backend/README.md) | FastAPI, Supabase, pipeline, audit | Person 3 |
| `console.html` | Pre-clearance console UI | Person 4 |
| `schema.py` | Shared domain models | — |

Each module is called through a thin adapter, so any one can be replaced
without touching the others.

## Typical flow

```bash
CLAIM=$(curl -s -X POST localhost:8000/claims \
  -H 'Content-Type: application/json' \
  -d '{"reference":"EXP-2026-01"}' | jq -r .id)

curl -X POST localhost:8000/claims/$CLAIM/documents \
  -F file=@extraction/sample_invoice.png -F doc_type=invoice
curl -X POST localhost:8000/claims/$CLAIM/documents \
  -F file=@extraction/packing_list_clean.png -F doc_type=packing_list

# Cost statement — without this, origin cannot be established
curl -X PUT localhost:8000/claims/$CLAIM/origin-declaration \
  -H 'Content-Type: application/json' -d '{
    "agreement":"AIFTA","hs_code":"630231","fob_value":4200.00,
    "non_originating_materials":[
      {"description":"Greige cotton fabric","hs_code":"520811","value":1500.00}
    ]}'

curl -X POST localhost:8000/claims/$CLAIM/process
curl -s localhost:8000/claims/$CLAIM/result | jq
```

Full endpoint table in [`backend/README.md`](backend/README.md).

## What it will not do

Worth stating plainly, because it shapes what the system is honest about:

- **Documents alone cannot establish origin.** Regional value content needs a
  cost statement — FOB value plus the value and HS code of every
  non-originating material, the information CAROTAR 2020 requires an importer
  to hold in Form I. Without it the engine returns `INSUFFICIENT_DATA` and
  names the missing fields rather than inferring a percentage.
- **Product-specific rules are not implemented.** PSRs override the general
  rule for many tariff lines; only the general rule is applied.
- **Two agreements** are encoded (AIFTA, SAFTA), each with its source cited in
  [`rules/agreements.py`](rules/agreements.py). Thresholds were verified
  against those sources on 2026-08-27, but they are secondary sources — check
  the gazette before relying on them.
- **A document discrepancy never auto-rejects.** It routes to human review.

This is a prototype, not a compliance tool.

## Configuration

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Document extraction |
| `SUPABASE_URL` / `SUPABASE_KEY` | Persistence and file storage |
| `SUPABASE_BUCKET` | Storage bucket, defaults to `documents` |
| `CORS_ORIGINS` | Allowed dashboard origins, defaults to `*` |

Never commit `.env`.
