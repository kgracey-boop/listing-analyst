"""
Combine per-file extraction results into one merged view for a property.
Single-fact fields (address, price, days on market) reconcile to one value and
flag disagreement; per-platform metrics (views/saves) stay broken out by
source rather than being summed, since they're not the same underlying count.
"""

SINGLE_FIELDS = ["address", "list_price", "original_list_price", "days_on_market"]
SHOWINGS_FIELDS = ["total", "last_30_days"]


def merge_extractions(sources: list) -> dict:
    """sources: list of {"source": filename, "data": extracted_dict}"""
    merged = {
        "address": None,
        "list_price": None,
        "original_list_price": None,
        "days_on_market": None,
        "showings": {"total": None, "last_30_days": None},
        "traffic_by_source": [],
        "feedback_themes": [],
        "comparable_sales": [],
        "notes_on_missing_or_unclear_data": [],
        "_conflicts": {},
    }

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

    seen_comps = set()
    for s in sources:
        for comp in s["data"].get("comparable_sales") or []:
            key = (comp.get("address"), comp.get("sale_price"))
            if key not in seen_comps:
                seen_comps.add(key)
                merged["comparable_sales"].append(comp)

    for s in sources:
        for note in s["data"].get("notes_on_missing_or_unclear_data") or []:
            merged["notes_on_missing_or_unclear_data"].append(f"[{s['source']}] {note}")

    return merged


def total_views(snapshot: dict) -> int:
    return sum((t.get("views") or 0) for t in snapshot.get("traffic_by_source", []))
