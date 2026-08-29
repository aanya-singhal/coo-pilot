# 2-Minute Demo Script

## Before you present (60 seconds, off-stage)

```bash
cd ~/Desktop/CoO-PILOT
./scripts/start_demo.sh        # starts both servers and warms the cache
```

Wait for **READY**. Open <http://127.0.0.1:5500/console.html> and leave it up.

> **The cache is the whole risk.** Extraction takes ~38s cold and ~0.05s warm,
> and the cache dies when the backend restarts. Restart anything, run the
> script again before anyone is watching.

---

## The script

### 0:00 — Frame it (15s)

> "Certificate of Origin claims are checked by hand. An officer reads an
> invoice, a packing list, and a cost statement, and decides whether the goods
> qualify for preferential tariff. CoO-PILOT prepares that case. It does not
> issue the certificate — the officer still decides."

### 0:15 — Clean submission (25s) → **GREEN**

**Select "Clean submission" → run it.**

> "Gemini reads both documents. Every field is tagged with the document it came
> from — that's what makes the decision auditable."

Point at reconciliation.

> "This stage is deterministic — no AI. It matched 'Nilgiri Textiles Pvt Ltd'
> against 'Private Limited' by normalising, not guessing."

Point at rules of origin.

> "AIFTA needs 35% regional value content plus a 6-digit tariff shift. This is
> 42.86%. The citation is on screen — Notification 189/2009-Customs."

**Result: ELIGIBLE · risk 0.**

### 0:40 — Correction required (25s) → **YELLOW**

**Select "Correction required" → run it.**

> "Same exporter. Invoice says 500 units, packing list says 480."

> "Origin still passes — the cost statement is unchanged. But the documents
> disagree, so it's held. A discrepancy never auto-rejects; it routes to a
> human. Risk 40."

**Result: REVIEW REQUIRED.**

### 1:05 — Origin requirement failed (25s) → **RED**

**Select "Origin requirement failed" → run it.**

> "Documents agree here. But the declared non-originating material value is
> higher, so regional value content comes to 31% — under the 35% threshold."

> "This is the only thing that gets an outright rejection: the origin rule was
> evaluated and failed. Not a paperwork problem — a substantive one."

**Result: NOT ELIGIBLE.**

### 1:30 — The refusal (20s) ← *the differentiator*

**Untick "Submit declaration with case" → rerun the clean case.**

> "Now I remove the cost statement and run the same clean documents."

> "It refuses. An invoice and a packing list cannot establish origin — you need
> the Form I cost statement under CAROTAR 2020. It names the three missing
> fields rather than guessing a percentage."

> "Any system can show a green tick. This one tells you when it doesn't know."

### 1:50 — Close (10s)

> "AI reads the documents. Deterministic logic decides. A human signs off — and
> the officer's decision is written to the claim's audit trail in the backend."

---

## If asked

**"Is the AI actually running?"**
Yes — Gemini reads the images live. Untick the declaration and the whole result
changes, or open the network tab.

**"Are those real trade rules?"**
The AIFTA thresholds and the notification are real and cited on screen. We
implement the *general* rule only — product-specific rules override it for many
tariff lines, and that's the next step. The risk weights are ours, not
statutory, and the interface says so.

**"What if extraction is wrong?"**
It never decides. It produces evidence; deterministic logic decides; a human
signs off. A misread field surfaces as a reconciliation mismatch and routes to
review rather than passing through.

**"Where's the data?"**
Postgres via Supabase, documents in object storage, seven tables, full audit
trail. *(Running in memory today — say so if pressed; don't claim persistence.)*

**"How is this different from OCR?"**
OCR gives you text. This gives you a decision with its working shown: which
document each value came from, which rule was applied, why it was held.

---

## If something breaks

| Symptom | Cause | Do this |
| --- | --- | --- |
| Spinner stuck ~40s | Cold cache | Let it finish — once per document only |
| "Backend unavailable" banner | Backend died | `./scripts/start_demo.sh` in another terminal |
| Officer buttons say "not submitted" | Run used recorded data | Rerun the case; needs a live run |

**The console never lies about its state.** If the backend is down it says so
and labels the data as recorded. If that happens live, say *"that's the fallback
path — it's telling you it isn't live"*, then fix it. That reads as
trustworthy, not broken.
