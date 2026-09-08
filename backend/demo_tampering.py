"""Demo: show a valid chain, tamper with one entry, show it break.
Run: python3 -m backend.demo_tampering
"""
from backend.database import get_database
from backend.services.hashing import verify_chain

db = get_database()
entries = db.list_all_audit_logs()

print("=== BEFORE: verifying real audit trail ===")
is_valid, broken = verify_chain(entries)
print(f"Valid: {is_valid}\n")

print("=== Tampering: editing entry 3's details directly in the database ===")
target = entries[3]
db._client.table("audit_logs").update({"details": {"document_count": 999}}).eq("id", target["id"]).execute()
print(f"Modified entry: {target['action']} (id={target['id'][:8]}...)\n")

print("=== AFTER: re-verifying ===")
entries_after = db.list_all_audit_logs()
is_valid, broken = verify_chain(entries_after)
print(f"Valid: {is_valid}, broken at index: {broken}")
if broken is not None:
    print(f"Detected tampering at: {entries_after[broken]['action']}")
