import os
import json
import time
import hashlib
import mimetypes
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

INVOICE_PROMPT = """
You are extracting structured data from an invoice document.
Return ONLY valid JSON, no markdown, no explanation, matching exactly this shape:

{
  "doc_type": "invoice",
  "exporter": "<exporter/company name>",
  "product": "<product name>",
  "quantity": <number, no units or commas>,
  "value": <number, no currency symbol or commas>,
  "invoice_number": "<invoice number as shown>",
  "confidence": {
    "exporter": <float 0.0-1.0, how confident you are this field was read correctly>,
    "product": <float 0.0-1.0>,
    "quantity": <float 0.0-1.0>,
    "value": <float 0.0-1.0>,
    "invoice_number": <float 0.0-1.0>
  }
}

Use a lower confidence score if the text is blurry, ambiguous, partially cut off, or you had to guess.
If a field is not present in the document, use null for that field and 0.0 for its confidence.
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
  "packing_list_number": "<packing list number as shown>",
  "confidence": {
    "exporter": <float 0.0-1.0>,
    "product": <float 0.0-1.0>,
    "quantity": <float 0.0-1.0>,
    "packages": <float 0.0-1.0>,
    "packing_list_number": <float 0.0-1.0>
  }
}

Use a lower confidence score if the text is blurry, ambiguous, partially cut off, or you had to guess.
If a field is not present in the document, use null for that field and 0.0 for its confidence.
"""

# Simple in-memory cache: same file + same doc_type -> reuse the last result
# instead of calling Gemini again. Resets when the program restarts.
_cache = {}

def _file_hash(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def extract_document(file_path: str, doc_type: str, max_retries: int = 3) -> dict:
    """
    Extract structured data from a document image or PDF.
    doc_type must be either "invoice" or "packing_list".
    Retries on transient/rate-limit failures, and caches results so the
    same file isn't re-sent to Gemini twice during testing or a live demo.
    Returns a dict matching the schema, or a dict with an "error" key if
    extraction ultimately failed after retries.
    """
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    except Exception as e:
        return {"error": f"Extraction module unavailable: {e}"}

    if doc_type == "invoice":
        prompt = INVOICE_PROMPT
    elif doc_type == "packing_list":
        prompt = PACKING_LIST_PROMPT
    else:
        return {"error": f"Unknown doc_type: {doc_type}"}

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}"}

    # Check cache first
    cache_key = (_file_hash(file_path), doc_type)
    if cache_key in _cache:
        return _cache[cache_key]

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "image/png"

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                raw_text = raw_text.replace("json", "", 1).strip()

            data = json.loads(raw_text)
            _cache[cache_key] = data  # cache success only
            return data

        except json.JSONDecodeError:
            last_error = "Model did not return valid JSON"
            # Don't retry on bad JSON, retrying won't fix a parsing issue reliably
            break

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                wait_time = 2 * attempt  # 2s, 4s, 6s backoff
                time.sleep(wait_time)
                continue

    return {"error": f"Extraction failed after {max_retries} attempts: {last_error}"}


# Quick manual test when running this file directly
if __name__ == "__main__":
    result = extract_document("sample_invoice.png", "invoice")
    print(json.dumps(result, indent=2))

    result2 = extract_document("packing_list_sloppy.png", "packing_list")
    print(json.dumps(result2, indent=2))

    # Run the same extraction again to prove caching works (should be instant, no API call)
    print("\n--- Testing cache (should be instant) ---")
    start = time.time()
    result3 = extract_document("sample_invoice.png", "invoice")
    print(f"Took {time.time() - start:.3f}s")
    print(json.dumps(result3, indent=2))