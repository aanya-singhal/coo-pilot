"""Print a readable summary of a claim result. Reads the JSON on stdin.

Used by scripts/run_case.sh; also handy on its own:
    curl -s localhost:8000/claims/<id>/result | python3 scripts/summarise_result.py
"""

import json
import sys


def main() -> None:
    data = json.load(sys.stdin)

    print()
    for name, doc in (data.get("extraction") or {}).items():
        if doc.get("error"):
            print(f"  {name:13} EXTRACTION FAILED - {doc['error'][:70]}")
        elif doc.get("skipped"):
            print(f"  {name:13} skipped - {doc.get('reason', '')[:60]}")
        else:
            fields = {
                k: v for k, v in doc.items() if k not in ("doc_type", "confidence")
            }
            print(f"  {name:13} " + ", ".join(f"{k}={v}" for k, v in fields.items()))

    reconciliation = data.get("reconciliation") or {}
    print(f"\n  reconciliation {reconciliation.get('summary', '-')}")
    for field in reconciliation.get("blocking_mismatches", []):
        print(f"    BLOCKING  {field}")
    for field in reconciliation.get("advisory_mismatches", []):
        print(f"    advisory  {field}")

    origin = (data.get("rules") or {}).get("origin") or {}
    value_content = origin.get("value_content")
    print(f"  origin         {origin.get('status')}", end="")
    if value_content:
        print(
            f" - RVC {value_content['regional_value_content_percent']}%"
            f" vs {value_content['threshold_percent']}% threshold"
        )
    else:
        print(f" - missing {origin.get('missing_fields', [])}")

    risk = data.get("risk") or {}
    print(f"  risk           {risk.get('score')} {risk.get('band')}")
    print(f"  decision       {data.get('decision')}\n")


if __name__ == "__main__":
    main()
