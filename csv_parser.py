"""
Deterministic CSV parsing for MLS comp exports (e.g. from Paragon) — no Gemini
call needed since this data is already structured. Tolerant of column-name
variation across different MLS systems via alias matching.
"""
import csv
import io

FIELD_ALIASES = {
    "address": ["address", "street address", "full address", "property address"],
    "status": ["status", "mls status", "listing status", "standard status"],
    "list_price": ["list price", "current price", "lp"],
    "original_list_price": ["original list price", "orig list price", "original price", "olp"],
    "sold_price": ["sold price", "close price", "sale price", "sp"],
    "square_feet": ["sqft", "sq ft", "square feet", "living area", "total sqft", "heated sqft"],
    "days_on_market": ["dom", "days on market", "cdom", "cumulative dom"],
    "close_date": ["close date", "sold date", "settlement date"],
    "list_date": ["listing contract date", "list date", "listing date"],
    "contract_date": ["purchase contract date", "contract date", "under contract date"],
    "new_construction": ["new construction yn", "new construction", "new construction y/n"],
    "link_or_reference": ["mls #", "mls#", "mls number", "listing id", "mls id"],
    "property_type": ["property sub type", "property type", "property subtype", "dwelling type", "type"],
    "subdivision": ["subdivision-free text", "subdivision", "neighborhood"],
    "city": ["city"],
    "postal_code": ["postal code", "zip", "zip code", "zipcode"],
}

# Stored as the RAW label from the source (e.g. "Single Family Residence"),
# not normalized here — normalization happens once, at grouping time, in
# market_stats.bucket_property_type(). That's what lets CSV-sourced comps
# ("Single Family Residence") and Gemini-extracted comps from a PDF (which
# might say just "Single Family") group together correctly instead of
# silently splitting into two buckets because the raw strings differ.

REQUIRED_FOR_ABSORPTION = ["status", "close_date"]


def _normalize(header: str) -> str:
    return header.strip().lower().replace("_", " ")


def _build_column_map(headers):
    normalized = {_normalize(h): h for h in headers}
    column_map = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                column_map[field] = normalized[alias]
                break
    return column_map


def _parse_number(value):
    if value is None:
        return None
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return round(float(cleaned))
        except ValueError:
            return None


def _parse_status(value):
    """Returns None only for a genuinely blank value. A non-blank value that
    doesn't match any known pattern returns "unrecognized" instead of None,
    so it gets tracked rather than silently vanishing from every count —
    real Paragon exports include statuses like "Hold" that don't map cleanly
    to active/pending/closed/expired/withdrawn."""
    if not value:
        return None
    v = value.strip().lower()
    if "closed" in v or "sold" in v:
        return "closed"
    if "expired" in v:
        return "expired"
    if "withdrawn" in v or "cancel" in v:
        return "withdrawn"
    if "hold" in v:
        return "hold"
    # Check before the plain "active" check — "active under contract" should
    # count as pending, not active, per Kevin's instruction.
    if "pending" in v or "under contract" in v or "contingent" in v:
        return "pending"
    if "active" in v or "coming soon" in v:
        return "active"
    return "unrecognized"


def _parse_yn(value):
    """Y/N flags don't guess on a blank or unrecognized value — None means
    "unknown", not "no", so callers filtering for new construction never
    silently misclassify a row the source just didn't answer."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("y", "yes", "true", "1"):
        return True
    if v in ("n", "no", "false", "0"):
        return False
    return None


def parse_mls_csv(file_obj) -> dict:
    """
    file_obj: a file-like object (e.g. from Streamlit's file_uploader).
    Returns {"comparable_listings": [...], "unmapped_fields": [...], "row_count": int}
    """
    raw = file_obj.read()
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    column_map = _build_column_map(headers)

    listings = []
    for row in reader:
        listing = {
            "address": (row.get(column_map.get("address"), "") or "").strip() or None,
            "status": _parse_status(row.get(column_map.get("status"), "")),
            "list_price": _parse_number(row.get(column_map.get("list_price"))),
            "original_list_price": _parse_number(row.get(column_map.get("original_list_price"))),
            "sold_price": _parse_number(row.get(column_map.get("sold_price"))),
            "square_feet": _parse_number(row.get(column_map.get("square_feet"))),
            "days_on_market": _parse_number(row.get(column_map.get("days_on_market"))),
            "close_date": (row.get(column_map.get("close_date"), "") or "").strip() or None,
            "list_date": (row.get(column_map.get("list_date"), "") or "").strip() or None,
            "contract_date": (row.get(column_map.get("contract_date"), "") or "").strip() or None,
            "new_construction": _parse_yn(row.get(column_map.get("new_construction"), "")),
            "link_or_reference": (row.get(column_map.get("link_or_reference"), "") or "").strip() or None,
            "property_type": (row.get(column_map.get("property_type"), "") or "").strip() or None,
            "subdivision": (row.get(column_map.get("subdivision"), "") or "").strip() or None,
            "city": (row.get(column_map.get("city"), "") or "").strip() or None,
            "postal_code": (row.get(column_map.get("postal_code"), "") or "").strip() or None,
        }
        if any(v is not None for v in listing.values()):
            listing["also_viewed"] = False
            listing["also_saved"] = False
            listings.append(listing)

    unmapped = [f for f in REQUIRED_FOR_ABSORPTION if f not in column_map]

    return {
        "comparable_listings": listings,
        "unmapped_fields": unmapped,
        "row_count": len(listings),
    }
