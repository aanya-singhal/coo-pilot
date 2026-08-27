import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT = """
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

with open("packing_list_sloppy.png", "rb") as f:
    image_bytes = f.read()

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=[
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        PROMPT,
    ],
)

raw_text = response.text.strip()

if raw_text.startswith("```"):
    raw_text = raw_text.strip("`")
    raw_text = raw_text.replace("json", "", 1).strip()

print("Raw model output:")
print(raw_text)
print()

data = json.loads(raw_text)
print("Parsed JSON:")
print(json.dumps(data, indent=2))