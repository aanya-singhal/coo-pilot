#!/usr/bin/env bash
# Run one case end to end against a running backend, using your own files.
#
#   ./scripts/run_case.sh <invoice> <packing-list> [hs_code] [fob] [nom_hs] [nom_value]
#
# Example:
#   ./scripts/run_case.sh ~/Desktop/inv.pdf ~/Desktop/pl.png 630221 4200 520511 2400
#
# Omit the origin arguments to see the engine refuse to evaluate origin.
# Accepts PDF, PNG, JPG, JPEG up to 20 MB. Override the host with API=...

set -euo pipefail

API="${API:-http://127.0.0.1:8000}"
INVOICE="${1:?usage: run_case.sh <invoice> <packing-list> [hs_code fob nom_hs nom_value]}"
PACKING="${2:?missing packing list}"
HS="${3:-}"; FOB="${4:-}"; NOM_HS="${5:-}"; NOM_VALUE="${6:-}"

for f in "$INVOICE" "$PACKING"; do
  [ -f "$f" ] || { echo "no such file: $f" >&2; exit 1; }
done

CLAIM=$(curl -sS -X POST "$API/claims" \
  -H 'Content-Type: application/json' \
  -d "{\"reference\":\"$(basename "$INVOICE")\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "claim $CLAIM"

for pair in "$INVOICE:invoice" "$PACKING:packing_list"; do
  file="${pair%:*}"; kind="${pair##*:}"
  code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$API/claims/$CLAIM/documents" \
    -F "file=@$file" -F "doc_type=$kind")
  echo "  uploaded $(basename "$file") as $kind -> HTTP $code"
  [ "$code" = "201" ] || { echo "upload rejected" >&2; exit 1; }
done

if [ -n "$HS" ] && [ -n "$FOB" ]; then
  curl -sS -o /dev/null -X PUT "$API/claims/$CLAIM/origin-declaration" \
    -H 'Content-Type: application/json' \
    -d "{\"agreement\":\"AIFTA\",\"hs_code\":\"$HS\",\"fob_value\":$FOB,
         \"non_originating_materials\":[{\"description\":\"declared input\",
         \"hs_code\":\"${NOM_HS:-}\",\"value\":${NOM_VALUE:-0}}]}"
  echo "  origin declaration attached"
else
  echo "  no origin declaration - origin will report INSUFFICIENT_DATA"
fi

curl -sS -o /dev/null -X POST "$API/claims/$CLAIM/verify"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
curl -sS "$API/claims/$CLAIM/result" | python3 "$HERE/summarise_result.py"
echo "  full evidence: $API/claims/$CLAIM/result"
