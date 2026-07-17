"""
The running, deduplicated comp set for a property — persisted across every
report saved for it, not just within one session. Two different merge rules
depending on the field:
  - Time-varying (status, prices, DOM, close_date): newest report wins.
  - Stable (property type, subdivision, city, MLS#): keep once known.
Manual exclusion (agent judgment that a comp isn't a fair comparison) is
tracked per comp and survives future updates — it's never touched by re-merging
fresh extraction data.
"""
from datetime import date

from merge import address_key

TIME_VARYING_FIELDS = ["status", "list_price", "original_list_price", "sold_price", "days_on_market", "close_date"]
STABLE_FIELDS = [
    "address", "property_type", "subdivision", "city", "postal_code", "link_or_reference",
    "source", "also_viewed", "also_saved",
]

# Booleans that, once flagged true, get a companion "when did we first learn
# this" date stamped alongside them — set once, on the first report where the
# flag is true, and never touched again (even if a later report re-confirms
# or omits it). Distinct from first_seen_date/last_seen_date below, which
# track the comp overall, not this specific flag.
FIRST_FLAGGED_DATE_FIELDS = [("also_viewed", "also_viewed_since"), ("also_saved", "also_saved_since")]


def update_known_comps(known_comps: dict, new_comps: list, today: str = None) -> dict:
    """
    known_comps: {address_key: comp_dict} — comp_dict includes "excluded" (bool)
    and "excluded_reason" (str or None) alongside the usual comp fields.
    new_comps: freshly extracted/merged comps from the current session.
    Returns the updated dict — does not mutate the input.
    """
    today = today or date.today().isoformat()
    updated = {k: dict(v) for k, v in known_comps.items()}

    for comp in new_comps:
        key = address_key(comp.get("address"))
        if not key:
            continue  # can't track a comp we can't identify by address

        if key in updated:
            existing = updated[key]
            for field in TIME_VARYING_FIELDS:
                if comp.get(field) is not None:
                    existing[field] = comp[field]
            for field in STABLE_FIELDS:
                if not existing.get(field) and comp.get(field):
                    existing[field] = comp[field]
            for flag_field, since_field in FIRST_FLAGGED_DATE_FIELDS:
                if comp.get(flag_field) and not existing.get(since_field):
                    existing[since_field] = today
            existing["last_seen_date"] = today
            # "excluded" / "excluded_reason" deliberately left untouched —
            # that's an agent judgment call, not something re-extraction
            # should ever reset.
        else:
            entry = dict(comp)
            entry["excluded"] = False
            entry["excluded_reason"] = None
            entry["first_seen_date"] = today
            entry["last_seen_date"] = today
            for flag_field, since_field in FIRST_FLAGGED_DATE_FIELDS:
                if entry.get(flag_field):
                    entry[since_field] = today
            updated[key] = entry

    return updated


def all_comps_list(known_comps: dict) -> list:
    """All known comps, for display — including excluded ones, since hiding
    them would break the "always surface data-quality info" rule the rest of
    the app follows. Sorted by first-seen date, newest first."""
    return sorted(known_comps.values(), key=lambda c: c.get("first_seen_date") or "", reverse=True)


def active_for_calculation(known_comps: dict) -> list:
    """Only non-excluded comps — feed this into absorption rate, median
    stats, property-type breakdown, data scope, etc. Excluded comps still
    show up in the table, just don't count toward the math."""
    return [c for c in known_comps.values() if not c.get("excluded")]


def also_viewed_comps(comparable_listings: list) -> list:
    """Comps flagged from a Doorify-style "people who viewed this listing
    also viewed" table — including excluded ones, same "never hide
    data-quality info" rule the rest of the comps tables follow. Sorted by
    when the overlap was first flagged, most recent first."""
    comps = [c for c in comparable_listings if c.get("also_viewed")]
    return sorted(comps, key=lambda c: c.get("also_viewed_since") or "", reverse=True)


def also_saved_comps(comparable_listings: list) -> list:
    """Same as also_viewed_comps, for the "people who saved this listing
    also saved" table."""
    comps = [c for c in comparable_listings if c.get("also_saved")]
    return sorted(comps, key=lambda c: c.get("also_saved_since") or "", reverse=True)
