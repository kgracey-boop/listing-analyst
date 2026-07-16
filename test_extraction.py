"""
Phase 1: Extraction Test
Uploads a single PDF to Gemini and asks it to pull out structured listing data.
Run: python3 test_extraction.py samples/some_report.pdf
     python3 test_extraction.py --list-models
"""
import argparse
import json
import sys

from dotenv import load_dotenv

from gemini_io import ACTIVITY_PROMPT, MODEL, extract_json, get_client

load_dotenv()


def extract(client, pdf_path: str, model_name: str):
    return json.dumps(extract_json(client, pdf_path, ACTIVITY_PROMPT, model_name))


def list_models(client):
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            print(m.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?", help="Path to a listing report PDF")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()

    try:
        client = get_client()
    except RuntimeError as e:
        sys.exit(str(e))

    if args.list_models:
        list_models(client)
        return

    if not args.pdf:
        sys.exit("Usage: python3 test_extraction.py <path-to-pdf>")

    raw = extract(client, args.pdf, args.model)
    print(raw)
    print("\n--- Parsed OK ---")
    print(json.dumps(json.loads(raw), indent=2))


if __name__ == "__main__":
    main()
