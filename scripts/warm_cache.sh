#!/usr/bin/env bash
# Pre-warm the extraction cache before a demo.
#
#   ./scripts/warm_cache.sh
#
# Extraction caches on (file hash, doc_type) inside the backend process, so a
# cold call costs one Gemini round trip per document - tens of seconds - while
# a warm one is instant. That cache dies with the process.
#
# RUN THIS AFTER EVERY BACKEND RESTART, and before anyone is watching.

set -euo pipefail

API="${API:-http://127.0.0.1:8000}"

DECL='"origin_declaration":{"agreement":"AIFTA","hs_code":"630221","fob_value":4200.00,
  "non_originating_materials":[{"description":"Greige cotton fabric","hs_code":"520511","value":2400.00}]}'

if ! curl -sS --max-time 5 "$API/health" > /dev/null 2>&1; then
  echo "backend not reachable at $API - start it first" >&2
  exit 1
fi

warm () {
  local label="$1" case_id="$2" packing="$3"
  printf '  %-22s ' "$label"
  local t
  t=$(curl -sS -o /dev/null -w '%{time_total}' --max-time 300 \
    -X POST "$API/process" -H 'Content-Type: application/json' \
    -d "{\"case_id\":\"$case_id\",\"files\":[\"sample_invoice.png\",\"$packing\"],$DECL}")
  printf '%ss\n' "$t"
}

echo "warming extraction cache at $API"
warm "clean submission"   case-clean-01  packing_list_clean.png
warm "correction required" case-sloppy-01 packing_list_sloppy.png

echo
echo "verifying both are now warm:"
warm "clean (repeat)"      case-clean-01  packing_list_clean.png
warm "sloppy (repeat)"     case-sloppy-01 packing_list_sloppy.png
echo
echo "done - the console's two buttons will now respond instantly."
echo "if you restart the backend, run this again."
