# 2-Minute Demo Script

## Before you present (60 seconds, off-stage)

```bash
cd ~/Desktop/CoO-PILOT
./scripts/start_demo.sh        # starts both servers and warms the cache
```

Wait for **"READY"**. Open <http://127.0.0.1:5500/console.html> and leave it on screen.

> **The cache is the whole risk.** Extraction takes ~38s cold and ~0.05s warm,
> and the cache dies when the backend restarts. If you restart anything, run
> the script again before anyone is watching.

---

## The script

### 0:00 — Frame it (15s)

> "Certificate of Origin claims are checked by hand. An officer reads an
> invoice, a packing list, and a cost statement, and decides whether the goods
> qualify for preferential tariff. CoO-PILOT prepares that case. It does not
> issue the certificate — the officer still decides."

### 0:15 — Clean case (30s)

**Click `case-clean-01` → Run pre-clearance.**

> "Gemini reads both documents. Every field is tagged with the document it came
> from — that's stage 2, and it's what makes the decision auditable."

Point at the reconciliation table.

> "Reconciliation is deterministic — no AI. It matched 'Nilgiri Textiles Pvt
> Ltd' against 'Private Limited' by normalising, not by guessing."

Point at stage 4.

> "AIFTA requires 35% regional value content plus a 6-digit tariff shift. This
> one is 42.86%. The citation is on screen — Notification 189/2009-Customs."

**Result: GREEN, risk 0.**

### 0:45 — Sloppy case (30s)

**Click `case-sloppy-01` → Run pre-clearance.**

> "Same exporter, but the invoice says 500 units and the packing list says 480."

> "Origin still passes — the cost statement is unchanged. But the documents
> disagree, so it's held. A discrepancy never auto-rejects; it routes to a
> human. Risk 40, medium."

**Result: YELLOW, held.**

### 1:15 — The refusal (30s) ← *the differentiator*

**Uncheck "Submit declaration with case" → rerun the clean case.**

> "Now I remove the cost statement and run the same clean documents again."

> "It refuses. An invoice and a packing list cannot establish origin — you need
> the Form I cost statement under CAROTAR 2020. It names the three missing
> fields rather than guessing a percentage."

> "Any system can show a green tick. This one tells you when it doesn't know."

### 1:45 — Close (15s)

**Click "Open full evidence file".**

> "Every run is a real claim in the backend with a full audit trail. This is the
> record, served by the API — the officer's decision is written to it too."

> "AI reads the documents. Deterministic logic decides. A human signs off."

---

## If asked

**"Is the AI actually running?"**
Yes — Gemini reads the images live. Uncheck the declaration and the whole
result changes, or open the network tab.

**"Are those real trade rules?"**
The AIFTA thresholds and the notification are real and cited on screen. We
implement the *general* rule only — product-specific rules override it for many
tariff lines, and that's the next step. The risk weights are ours, not
statutory, and the UI says so.

**"What if extraction is wrong?"**
It never decides. It produces evidence; deterministic logic decides; a human
signs off. A field it misreads shows up as a reconciliation mismatch, which
routes to review rather than through.

**"Where's the data?"**
Postgres via Supabase, with the original documents in object storage.
*(Running in-memory today — say so if pressed; don't claim persistence.)*

---

## If something breaks

| Symptom | Cause | Do this |
| --- | --- | --- |
| Spinner stuck ~40s | Cold cache | Let it finish. It only happens once per document. |
| "Backend unavailable" banner | Backend died | `./scripts/start_demo.sh` in another terminal |
| Officer buttons say "not submitted" | Run used recorded data | Rerun the case; needs a live run |

**The console never lies about its state.** If the backend is down it says so and
labels the data as recorded. That's a feature — if it happens live, say
"that's the fallback path, and it's telling you it isn't live." Then fix it.
