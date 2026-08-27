from extractor import extract_document

# --- TEMPORARY STAND-INS (replace these once Person 2 and Person 3 push their real code) ---

def mock_reconcile_and_verdict(invoice_data: dict, packing_list_data: dict) -> dict:
    """Fake version of Person 2's rule engine, just for testing today."""
    if invoice_data.get("quantity") != packing_list_data.get("quantity"):
        return {
            "verdict": "YELLOW",
            "reason": f"Invoice quantity {invoice_data.get('quantity')} vs Packing List quantity {packing_list_data.get('quantity')}",
            "rule_applied": "quantity_match (mock)",
            "rule_satisfied": False,
        }
    return {
        "verdict": "GREEN",
        "reason": "All fields match, rule satisfied",
        "rule_applied": "quantity_match (mock)",
        "rule_satisfied": True,
    }

def mock_write_to_supabase(case_id: str, invoice_data: dict, packing_list_data: dict, verdict: dict):
    """Fake version of Person 3's Supabase write, just prints for now."""
    print(f"[MOCK SUPABASE WRITE] case_id={case_id}")
    print(f"  invoice: {invoice_data}")
    print(f"  packing_list: {packing_list_data}")
    print(f"  verdict: {verdict}")

# --- REAL ORCHESTRATION ---

def process_case(case_id: str, invoice_path: str, packing_list_path: str) -> dict:
    invoice_data = extract_document(invoice_path, "invoice")
    if "error" in invoice_data:
        return {"error": f"Invoice extraction failed: {invoice_data['error']}"}

    packing_list_data = extract_document(packing_list_path, "packing_list")
    if "error" in packing_list_data:
        return {"error": f"Packing list extraction failed: {packing_list_data['error']}"}

    verdict = mock_reconcile_and_verdict(invoice_data, packing_list_data)
    mock_write_to_supabase(case_id, invoice_data, packing_list_data, verdict)

    return {
        "case_id": case_id,
        "invoice": invoice_data,
        "packing_list": packing_list_data,
        "verdict": verdict,
    }


if __name__ == "__main__":
    import json

    print("=== Clean case ===")
    result = process_case("case-clean-01", "sample_invoice.png", "packing_list_clean.png")
    print(json.dumps(result, indent=2))

    print("\n=== Sloppy case ===")
    result2 = process_case("case-sloppy-01", "sample_invoice.png", "packing_list_sloppy.png")
    print(json.dumps(result2, indent=2))