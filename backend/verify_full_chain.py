"""Verify the entire audit_logs table's hash chain.
Run: python3 -m backend.verify_full_chain
"""
from backend.database import get_database
from backend.services.hashing import verify_chain

db = get_database()
print(f"Using database: {type(db).__name__}")

entries = db.list_all_audit_logs()
print(f"Total entries in whole table: {len(entries)}")

is_valid, broken_index = verify_chain(entries)
print(f"Valid: {is_valid}, broken at: {broken_index}")
