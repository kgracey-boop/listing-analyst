"""
Combine per-file extraction results into one merged view for a property.
Single-fact fields (address, price, days on market) reconcile to one value and
flag disagreement; per-platform metrics (views/saves) stay broken out by
source rather than being summed, since they're not the same underlying count.
"""

SINGLE_FIELDS = ["address", "list_price", "original_list_price", "days_on_market", "square_feet"]
SHOWINGS_FIELDS = ["total", "last_30_days"]

BACKFILL_FIELDS = ["property_type", "subdivision", "city", "postal_code"]


def address_key(address):
    """Match on the street-address portion only (before the first comma) —
    different sources format the same address inconsistently (some append
    city/state/zip inline, some don't), so an exact full-string match would
    miss real matches."""
    if not address:
        return None
    return address.split(",")[0].strip().lower()


def backfill_comp_fields(comparable_listings: list) -> list:
    """Some report formats (e.g. Doorify) don't show property type — or
    subdivision/city/zip — per comp at all. If the same address shows up
    elsewhere in this report with that field known (e.g. from a CSV export
    that does list it), use that instead of leaving it blank."""
    known = {}
    for c in comparable_listings:
        key = address_key(c.get("address"))
        if not key:
            continue
        for field in BACKFILL_FIELDS:
            if c.get(field) and (key, field) not in known:
                known[(key, field)] = c[field]

    for c in comparable_listings:
        key = address_key(c.get("address"))
        if not key:
            continue
        for field in BACKFILL_FIELDS:
            if not c.get(field) and (key, field) in known:
                c[field] = known[(key, field)]

    return comparable_listings


def empty_merged() -> dict:
    """The blank template every merged/saved report is built from. Used both
    as the starting point for a fresh merge and to backfill any keys missing
    from an older saved snapshot (from before a field like price_history
    existed) so the review screen never hits a missing key on old data."""
    return {
        "address": None,
        "list_price": None,
        "original_list_price": None,
        "days_on_market": None,
        "square_feet": None,
        "showings": {"total": None, "last_30_days": None},
        "traffic_by_source": [],
        "feedback_themes": [],
        "comparable_listings": [],
        "price_bands": [],
        "price_history": [],
        "notes_on_missing_or_unclear_data": [],
        "_conflicts": {},
    }


def merge_extractions(sources: list) -> dict:
    """sources: list of {"source": filename, "data": extracted_dict}"""
    merged = empty_merged()

    for field in SINGLE_FIELDS:
        values = [(s["source"], s["data"].get(field)) for s in sources if s["data"].get(field) is not None]
        if values:
            merged[field] = values[0][1]
            if len({v for _, v in values}) > 1:
                merged["_conflicts"][field] = [{"source": src, "value": val} for src, val in values]

    for sub_field in SHOWINGS_FIELDS:
        values = [
            (s["source"], (s["data"].get("showings") or {}).get(sub_field))
            for s in sources
            if (s["data"].get("showings") or {}).get(sub_field) is not None
        ]
        if values:
            merged["showings"][sub_field] = values[0][1]
            if len({v for _, v in values}) > 1:
                merged["_conflicts"][f"showings.{sub_field}"] = [
                    {"source": src, "value": val} for src, val in values
                ]

    for s in sources:
        traffic = s["data"].get("online_traffic") or {}
        if traffic.get("views") is not None or traffic.get("saves") is not None:
            merged["traffic_by_source"].append(
                {"source": s["source"], "views": traffic.get("views"), "saves": traffic.get("saves")}
            )

    seen_feedback = set()
    for s in sources:
        for theme in s["data"].get("feedback_themes") or []:
            if theme not in seen_feedback:
                seen_feedback.add(theme)
                merged["feedback_themes"].append(theme)

    comps_by_key = {}
    comp_order = []
    for s in sources:
        for comp in s["data"].get("comparable_listings") or []:
            key = comp.get("link_or_reference") or (comp.get("address"), comp.get("status"))
            if key in comps_by_key:
                # Same listing cited by more than one source (e.g. Doorify and
                # the CSV both list the same MLS#) — fill gaps rather than
                # discarding the duplicate's data, since one source alone
                # (like Doorify) often has fewer fields than another.
                existing = comps_by_key[key]
                for field, value in comp.items():
                    if value and not existing.get(field):
                        existing[field] = value
            else:
                comps_by_key[key] = dict(comp)
                comp_order.append(key)
    merged["comparable_listings"] = backfill_comp_fields([comps_by_key[k] for k in comp_order])

    seen_bands = set()
    for s in sources:
        for band in (s["data"].get("price_band_analysis") or {}).get("bands") or []:
            label = band.get("band")
            if label and label not in seen_bands:
                seen_bands.add(label)
                merged["price_bands"].append(band)

    seen_price_points = set()
    for s in sources:
        for point in s["data"].get("price_history") or []:
            key = (point.get("date"), point.get("price"))
            if key not in seen_price_points:
                seen_price_points.add(key)
                merged["price_history"].append(point)

    for s in sources:
        for note in s["data"].get("notes_on_missing_or_unclear_data") or []:
            merged["notes_on_missing_or_unclear_data"].append(f"[{s['source']}] {note}")

    return merged


def total_views(snapshot: dict) -> int:
    return sum((t.get("views") or 0) for t in snapshot.get("traffic_by_source", []))
