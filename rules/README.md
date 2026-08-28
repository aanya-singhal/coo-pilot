# Rules Engine

Evaluates one Certificate of Origin case. The backend discovers
`rules.engine.evaluate` automatically — no backend configuration.

```python
from rules.engine import evaluate
result = evaluate({"invoice": {...}, "packing_list": {...}})
```

Returns `{"reconciliation": {...}, "rules": {...}, "risk": {...}, "decision": ...}`.

## Modules

| File | Does |
| --- | --- |
| [engine.py](engine.py) | Entry point; composes the stages and decides |
| [reconciliation.py](reconciliation.py) | Invoice ↔ packing list field comparison |
| [origin.py](origin.py) | Value content + change in tariff classification |
| [agreements.py](agreements.py) | Per-agreement thresholds, each with its source |
| [risk.py](risk.py) | Itemised triage score |

## Decisions

| Decision | When |
| --- | --- |
| `APPROVED` | Documents reconcile **and** the origin criterion is met |
| `REJECTED` | The origin criterion was evaluated and failed |
| `PENDING_REVIEW` | Everything else — including whenever origin cannot be evaluated |

A document discrepancy never auto-rejects; it routes to human review, as a
customs officer would.

## The data gap that matters

**An invoice and a packing list cannot establish origin.** Determining it
requires a cost statement: FOB value plus the value and HS classification of
every non-originating material — the information CAROTAR 2020 requires an
importer to hold in Form I.

When that is absent the engine returns `INSUFFICIENT_DATA` and names the
missing fields. It does not estimate, default, or infer a percentage. So with
only the two sample documents, the honest outcome is `PENDING_REVIEW`, not a
GREEN pass.

To evaluate origin properly, supply `origin_declaration`:

```python
evaluate({
  "invoice": {...},
  "packing_list": {...},
  "origin_declaration": {
    "agreement": "AIFTA",
    "hs_code": "630231",
    "fob_value": 4200.00,
    "non_originating_materials": [
      {"description": "Greige cotton fabric", "hs_code": "520811", "value": 1500.00}
    ]
  }
})
```

Regional value content is computed by the indirect (build-down) method:
`(FOB − non-originating value) / FOB × 100`. Set `"wholly_obtained": true` to
skip both tests.

## Agreements

| Code | Value content | Tariff shift |
| --- | --- | --- |
| `AIFTA` | ≥ 35% of FOB | CTSH (6-digit) |
| `SAFTA` | ≥ 40% of FOB | CTH (4-digit) |
| `SAFTA_LDC` | ≥ 30% of FOB | CTH (4-digit) |

Both criteria must be met. Every entry in [agreements.py](agreements.py)
carries a `citation` and `source_url`, and the engine reports which criterion
it applied so a reviewer can check the working.

> **Verify before operational use.** These are *general* rules; product-specific
> rules override them for many tariff lines, and agreements are amended.
> Thresholds were confirmed against their cited sources on 2026-08-27.

## Risk score

A triage aid, not a regulatory measure. The weights in [risk.py](risk.py) are
a policy choice of this tool with no statutory basis; they exist so the most
doubtful claims queue first. Every contribution is itemised in `factors`.

## Tests

```bash
pytest tests/test_rules_engine.py
```
