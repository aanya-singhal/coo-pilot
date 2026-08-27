import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

INVOICE_PROMPT = """
You are extracting structured data from an invoice document.
Return ONLY valid JSON, no markdown, no explanation, matching exactly this shape:

{
  "doc_type": "invoice",
  "exporter": "<exporter/company name>",
  "product": "<product name>",
  "quantity": <number, no units or commas>,
  "value": <number, no currency symbol or commas>,
  "invoice_number": "<invoice number as shown>"
}

If a field is not present in the document, use null for that field.
"""

PACKING_LIST_PROMPT = """
You are extracting structured data from a packing list document.
Return ONLY valid JSON, no markdown, no explanation, matching exactly this shape:

{
  "doc_type": "packing_list",
  "exporter": "<exporter/company name>",
  "product": "<product name>",
  "quantity": <number, no units or commas>,
  "packages": <number of packages, integer>,
  "packing_list_number": "<packing list number as shown>"
}

If a field is not present in the document, use null for that field.
"""

def extract_document(file_path: str, doc_type: str) -> dict:
    """
    Extract structured data from a document image.
    doc_type must be either "invoice" or "packing_list".
    Returns a dict matching the schema, or a dict with an "error" key if extraction failed.
    """
    if doc_type == "invoice":
        prompt = INVOICE_PROMPT
    elif doc_type == "packing_list":
        prompt = PACKING_LIST_PROMPT
    else:
        return {"error": f"Unknown doc_type: {doc_type}"}

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}"}

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )
    except Exception as e:
        return {"error": f"Gemini API call failed: {e}"}

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Model did not return valid JSON", "raw_output": raw_text}

    return data


# Quick manual test when running this file directly
if __name__ == "__main__":
    result = extract_document("sample_invoice.png", "invoice")
    print(json.dumps(result, indent=2))

    result2 = extract_document("packing_list_sloppy.png", "packing_list")
    print(json.dumps(result2, indent=2))