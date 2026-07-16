"""
Scratch/diagnostic script — NOT part of the app. Tests an extended extraction
schema against April's real report files before committing to a final shape.
"""
import json
import os
import sys
import glob

from dotenv import load_dotenv
load_dotenv()

from gemini_io import get_client, extract_json

EXTENDED_PROMPT = """You are reading one page of real estate report material —
could be a listing activity report, an MLS comp sheet (active/pending/closed
listings), a pricing benchmark report, or a target-market/price-band analysis.
Not every field below will apply to every document — use null or an empty list
for anything not present. Do not guess or invent numbers.

{
  "report_type_guess": string,
  "address": string or null,
  "list_price": number or null,
  "original_list_price": number or null,
  "days_on_market": number or null,
  "square_feet": number or null,
  "price_history": [ {"date": string, "price": number} ],
  "showings": {"total": number or null, "last_30_days": number or null},
  "feedback_themes": [string],
  "online_traffic": {"views": number or null, "saves": number or null},
  "comparable_listings": [
    {
      "address": string or null,
      "status": "active" or "pending" or "closed" or null,
      "list_price": number or null,
      "original_list_price": number or null,
      "sold_price": number or null,
      "square_feet": number or null,
      "days_on_market": number or null,
      "close_date": string or null,
      "link_or_reference": string or null
    }
  ],
  "price_band_analysis": {
    "subject_price_band": string or null,
    "bands": [ {"band": string, "showing_count": number} ]
  },
  "notes_on_missing_or_unclear_data": [string]
}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""


def main():
    client = get_client()
    files = sorted(glob.glob("samples/*.pdf"))
    for f in files:
        print(f"\n{'=' * 70}\n{os.path.basename(f)}\n{'=' * 70}")
        try:
            result = extract_json(client, f, EXTENDED_PROMPT)
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
