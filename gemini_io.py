"""
All Gemini calls in one place: reading activity reports, reading MLS cut
sheets, and writing client commentary.
"""
import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

ACTIVITY_PROMPT = """You are reading one real estate report about a listing or
its market — could be a listing activity report, an MLS comp sheet (active/
pending/closed listings), a pricing benchmark report, or a target-market/
price-band analysis. Not every field below will apply to every document — use
null or an empty list for anything not present. Do not guess or invent numbers.

Note on links: if you see a clickable link in the document, you cannot recover
its actual URL from a rendered page — only capture visible text (like an MLS#
or address) as `link_or_reference`, never invent a URL.

Note on status: "Active Under Contract" and "Coming Soon" are not standard
labels — map "Active Under Contract" to "pending" and "Coming Soon" to "active".

{
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
      "status": "active" or "pending" or "closed" or "expired" or "withdrawn" or null,
      "list_price": number or null,
      "original_list_price": number or null,
      "sold_price": number or null,
      "square_feet": number or null,
      "days_on_market": number or null,
      "close_date": string or null,
      "link_or_reference": string or null,
      "property_type": string or null,
      "subdivision": string or null,
      "city": string or null,
      "postal_code": string or null
    }
  ],
  "price_band_analysis": {
    "bands": [ {"band": string, "showing_count": number} ]
  },
  "notes_on_missing_or_unclear_data": [string]
}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""

PROFILE_PROMPT = """You are reading an MLS listing detail sheet ("cut sheet")
for a residential property — used to establish the basic facts about the
property, not its activity/performance.

These sheets often abbreviate fields. In particular, days on market is
commonly labeled "DOM" and often sits near the top of the sheet (frequently
top-right) rather than being spelled out — look for that abbreviation
specifically, not just the words "days on market".

Extract into this JSON shape. Use null for anything not present. Do not guess.

{
  "address": string or null,
  "list_price": number or null,
  "days_on_market": number or null,
  "bedrooms": number or null,
  "bathrooms": number or null,
  "square_feet": number or null,
  "property_type": string or null,
  "lot_size": string or null,
  "year_built": number or null,
  "mls_number": string or null,
  "remarks": string or null,
  "notes_on_missing_or_unclear_data": [string]
}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""

TONE_PRESETS = {
    "Warm & reassuring": "Write in a warm, reassuring, empathetic tone.",
    "Direct & data-driven": "Write in a direct, no-fluff, data-driven tone. Avoid filler and hedging.",
    "Brief & to the point": "Keep it very brief — 2-3 sentences maximum, no preamble.",
}

FALLBACK_STORIES = {
    "Priced too high": "Is there similar inventory available at a lower price?",
    "Market exhausted": "Has activity (showings/views) dropped off at this price?",
    "Waiting for the right buyer": "Are we at median days on market yet, or already beyond it?",
    "Doing well": "Strong activity so far — could this be heading toward an offer soon, or still in the new-listing honeymoon period?",
}


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Check the .env file.")
    return genai.Client(api_key=api_key)


def extract_json(client: genai.Client, file_path: str, prompt: str, model: str = MODEL) -> dict:
    uploaded = client.files.upload(file=file_path)
    response = client.models.generate_content(model=model, contents=[uploaded, prompt])
    return json.loads(response.text)


def generate_commentary(
    client: genai.Client,
    data: dict,
    history: list,
    hunch: str,
    tone_preset: str,
    tone_notes: str,
    model: str = MODEL,
) -> str:
    tone_instruction = TONE_PRESETS.get(tone_preset, "")
    prompt = f"""You are helping a real estate agent write a short client-facing
update about their listing's activity, for the seller to read. Ground every
claim in the numbers given below — never invent or assume data that isn't
provided.

Current report data:
{json.dumps(data, indent=2)}

History (previous saved reports for this property, oldest to newest):
{json.dumps(history, indent=2)}

Agent's hunch about what's going on: {hunch or "(none given — use your own read of the data)"}

Your job:
1. Check the agent's hunch against the data above. State clearly whether the
   data supports it, contradicts it, or isn't enough to tell either way. Be
   honest — do not confirm a hunch the numbers don't actually support.
2. Write 2-3 short paragraphs of client-ready commentary for the seller, grounded
   only in the numbers given above.

Tone: {tone_instruction} {tone_notes or ""}

Write the commentary now — no preamble, no markdown headers, just the paragraphs.
"""
    response = client.models.generate_content(model=model, contents=[prompt])
    return response.text
