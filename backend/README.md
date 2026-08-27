# CoO-PILOT Backend (Person 3)

FastAPI service that connects the team's modules: it stores claims and
documents, calls Person 1's extraction module and Person 2's rules engine,
persists their results, and exposes them to Person 4's dashboard.

The backend implements **no** AI logic and **no** business rules.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
uvicorn backend.main:app --reload
```

Interactive docs: <http://localhost:8000/docs>

Without `SUPABASE_URL` / `SUPABASE_KEY` the backend starts anyway using
in-memory database and storage. Handy for frontend work; data is lost on
restart.

## Docker

```bash
docker build -t coo-pilot-backend .
docker run -p 8000:8000 --env-file .env coo-pilot-backend
```

## Supabase setup

Run [`backend/db/schema.sql`](db/schema.sql) once in the Supabase SQL editor.
It creates `claims`, `documents`, `extracted_data`, `verification_results`,
`audit_logs`, and the private `documents` storage bucket.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service info |
| GET | `/health` | Liveness + whether Supabase is configured |
| POST | `/claims` | Create a claim |
| GET | `/claims` | List recent claims |
| GET | `/claims/{claim_id}` | Get one claim |
| POST | `/claims/{claim_id}/documents` | Upload a PDF/PNG/JPG/JPEG |
| GET | `/claims/{claim_id}/documents` | List a claim's documents |
| POST | `/claims/{claim_id}/process` | Run the pipeline |
| GET | `/claims/{claim_id}/result` | Full result for the dashboard |
| GET | `/claims/{claim_id}/audit` | Audit trail |

### Typical flow

```bash
CLAIM=$(curl -s -X POST localhost:8000/claims \
  -H 'Content-Type: application/json' \
  -d '{"reference":"EXP-2026-01"}' | jq -r .id)

curl -X POST localhost:8000/claims/$CLAIM/documents \
  -F file=@invoice.png -F doc_type=invoice

curl -X POST localhost:8000/claims/$CLAIM/documents \
  -F file=@packing_list.png -F doc_type=packing_list

curl -X POST localhost:8000/claims/$CLAIM/process
curl -s localhost:8000/claims/$CLAIM/result | jq
```

`doc_type` is one of `invoice`, `packing_list`, `certificate_of_origin`,
`other`. Only the first two are sent to the extractor today; the rest are
stored and marked as skipped.

Claim statuses: `CREATED`, `PROCESSING`, `PENDING_REVIEW`, `APPROVED`,
`REJECTED`, `FAILED`.

## Module boundaries

| Concern | Owner | Where the backend touches it |
| --- | --- | --- |
| Extraction | Person 1 | [`services/extraction_adapter.py`](services/extraction_adapter.py) calls `extraction/extractor.py::extract_document` |
| Rules engine | Person 2 | [`services/rules_adapter.py`](services/rules_adapter.py) — **TODO**, see below |
| Frontend | Person 4 | consumes `GET /claims/{id}/result` |

### For Person 1

The adapter downloads the stored file to a temp path and calls your
`extract_document(file_path, doc_type)` unchanged. Whatever dict you return
is stored verbatim in `extracted_data.data`.

One note: `extractor.py` hardcodes `mime_type="image/png"`, so PDF and JPEG
uploads currently reach Gemini labelled as PNG. The backend accepts and
stores all four types — making the extractor mime-aware is an
extraction-side change.

### For Person 2

A first implementation now lives in [`rules/`](../rules/README.md) — see that
README for the criteria, sources, and the origin-data gap. It was written to
unblock the demo and is yours to take over, replace, or extend.

The adapter finds it by importing `rules.engine.evaluate`; it also checks
`rules.rules_engine`, `rules_engine`, and `logic.rules_engine`, or add a path
to `CANDIDATE_MODULES`. The contract is:

```python
def evaluate(extraction: dict) -> dict:
    ...
```

Input is `{"invoice": {...}, "packing_list": {...}}`, plus an optional
`origin_declaration`. Return any of `reconciliation`, `rules`, `risk`,
`decision` — anything else is preserved under `raw`. If no engine is
importable the adapter returns a `NOT_IMPLEMENTED` placeholder rather than
inventing a verdict.

If `decision` is one of the claim statuses the backend mirrors it onto the
claim; otherwise the claim stays `PENDING_REVIEW`. The backend never derives
a verdict itself.

## Tests

```bash
pytest
```

No Supabase or Gemini credentials required — the suite runs entirely against
in-memory database/storage with Person 1 and Person 2's modules mocked.
