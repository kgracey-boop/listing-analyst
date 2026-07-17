"""
The running, deduplicated feedback set for a property — persisted across
every report saved for it, mirroring comps_store.py's approach for comps.

Feedback entries don't have a stable real-world identity the way an address
or MLS# does, so they're keyed on (date, quote) instead — a slightly
reworded re-extraction of the same comment won't dedupe against an earlier
one. An accepted limitation given feedback has no natural stable ID.

Agent follow-up flagging ("this buyer's still worth watching") is a durable
judgment call, not something re-extraction should ever reset — same
"never touched by re-merging fresh data" rule comps_store.py already
follows for its own "excluded" field.
"""
from datetime import date

from market_stats import try_parse_date


def _feedback_key(entry: dict):
    """A plain string key, not a tuple — this dict gets persisted as JSONB,
    whose object keys must be strings."""
    quote = (entry.get("quote") or "").strip()
    if not quote:
        return None
    return f"{entry.get('date') or ''}|{quote.lower()}"


def update_known_feedback(known_feedback: dict, new_feedback: list, today: str = None) -> dict:
    """
    known_feedback: {key: entry_dict} — entry_dict includes "following_up"
    (bool) and "follow_up_note" (str or None) alongside the usual date/
    quote/source fields.
    new_feedback: freshly extracted/merged feedback from the current session.
    Returns the updated dict — does not mutate the input.
    """
    today = today or date.today().isoformat()
    updated = {k: dict(v) for k, v in known_feedback.items()}

    for entry in new_feedback:
        key = _feedback_key(entry)
        if not key:
            continue  # can't track feedback with no quote text

        if key in updated:
            existing = updated[key]
            if not existing.get("source") and entry.get("source"):
                existing["source"] = entry["source"]
            existing["last_seen_date"] = today
            # "following_up" / "follow_up_note" deliberately left untouched —
            # that's an agent judgment call, not something re-extraction
            # should ever reset.
        else:
            new_entry = dict(entry)
            new_entry["following_up"] = False
            new_entry["follow_up_note"] = None
            new_entry["first_seen_date"] = today
            new_entry["last_seen_date"] = today
            updated[key] = new_entry

    return updated


def apply_feedback_edits(known_feedback: dict, edited_rows: list, today: str = None) -> dict:
    """Rebuilds known_feedback directly from what the agent's editor
    currently shows. Distinct from update_known_feedback on purpose: that
    one protects following_up/follow_up_note from being reset by fresh
    re-extraction, but here the edited rows ARE the deliberate new state —
    the agent checking Follow-up, editing a quote, or deleting a row via
    the editor should always take effect, never be protected against."""
    today = today or date.today().isoformat()
    rebuilt = {}
    for row in edited_rows:
        key = _feedback_key(row)
        if not key:
            continue
        existing = known_feedback.get(key)
        entry = dict(row)
        entry["first_seen_date"] = existing.get("first_seen_date") if existing else today
        entry["last_seen_date"] = today
        rebuilt[key] = entry
    return rebuilt


def all_feedback_list(known_feedback: dict) -> list:
    """All known feedback, newest first by the feedback's own stated date
    (falling back to when we first saw it, if no date was given)."""
    def sort_key(entry):
        return (
            try_parse_date(entry.get("date"))
            or try_parse_date(entry.get("first_seen_date"))
            or try_parse_date("1900-01-01")
        )

    return sorted(known_feedback.values(), key=sort_key, reverse=True)
