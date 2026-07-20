import os
import random
import re
import tempfile
import threading
from datetime import date

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Bridge Streamlit Cloud's secrets manager into os.environ, since the rest of
# this app reads config via os.environ (works locally via .env too). No-op
# if there's no secrets.toml (e.g. running locally).
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:
    pass

import db_storage as storage
from branding import BRAND, inject_css, render_footer, render_header
from legal import render_terms
from charts import (
    absorption_chart,
    price_band_chart,
    price_position_chart,
    price_reduction_trend_chart,
    weekly_contracts_chart,
)
from comps_store import active_for_calculation, all_comps_list, also_saved_comps, also_viewed_comps, update_known_comps
from csv_parser import parse_mls_csv
from feedback_store import all_feedback_list, apply_feedback_edits, update_known_feedback
from gemini_io import ACTIVITY_PROMPT, PROFILE_PROMPT, extract_json, get_client
from market_stats import (
    MIN_MONTHS_WITH_DATA,
    absorption_by_property_type,
    bucket_property_type,
    comp_price_reduction_stats,
    compute_absorption,
    compute_new_construction_absorption,
    data_scope_summary,
    dom_benchmark,
    filter_by_subdivision,
    filter_recent_closed,
    match_price_band,
    median_comp_days_on_market,
    median_comp_price_per_sqft,
    median_list_to_contract_days,
    price_per_sqft,
    price_reductions,
    subdivision_vs_zip_absorption,
    weekly_contracts,
)
from merge import address_key, empty_merged, merge_extractions, total_views
from pdf_export import build_pdf

st.set_page_config(page_title="RootedReports", page_icon="assets/favicon.png", layout="wide")
inject_css()


def require_passcode():
    """Simple shared-passcode gate. No-op if APP_PASSCODE isn't set (e.g. local dev)."""
    passcode = os.environ.get("APP_PASSCODE")
    if not passcode or st.session_state.get("authenticated"):
        return
    render_header("RootedReports")
    entered = st.text_input("Enter passcode", type="password")
    if st.button("Enter"):
        if entered == passcode:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect passcode.")
    st.stop()


require_passcode()

RALEIGH_FACTS = [
    'Raleigh is nicknamed the "City of Oaks" — we\'re rooting for your listing too.',
    "An oak tree takes 20 to 50 years to grow its first acorn. This will not take that long.",
    "Squirrels bury thousands of acorns a season and forget most of them. We're keeping better notes.",
    "Turning your reports into acorns of wisdom...",
    "Some Raleigh oaks are 300+ years old. Your download, mercifully, is not.",
    "Barking up the right tree with your data.",
    "A squirrel's filing system is 'bury it and hope.' Ours is slightly more rigorous.",
    "Raleigh's tree canopy covers over half the city — great shade, tough on curb-appeal photos.",
    "Gathering your acorns... er, data.",
    "Even squirrels double-check their math before winter. So are we, right now.",
    "An oak's root system often spreads wider than its branches — kind of like a good comp radius.",
    "Every oak was once an acorn that refused to quit. Every listing deserves the same energy.",
    "Squirrels can find buried acorns under a foot of snow by smell alone. We're just as good at sniffing out your comps.",
    "A squirrel's front teeth never stop growing — kind of like your list price, if the market's on your side.",
    "Squirrels plant more trees than any landscaper ever has, purely by forgetting where they buried lunch.",
    "Gray squirrels can rotate their ankles 180 degrees to climb down headfirst. We prefer to keep this report right-side up.",
    "Squirrels 'deceptive cache' — pretending to bury a nut to fool onlookers. Our numbers, unlike theirs, are not a decoy.",
    "A squirrel's memory for its stashes is only so-so. Good thing we wrote everything down.",
    "Squirrels have been clocked jumping 10 feet in a single leap. Your report should be ready before you'd even land.",
    "Baby squirrels are called kits — and about this size, our loading bar. Almost there.",
    "Squirrels test a branch's strength with their front paws before committing. We did the same with your data.",
    "A squirrel's tail acts as a parachute, a blanket, and a signal flag. Our loading screen only has one job, and it's this one.",
    "Squirrels spend up to 80% of their waking hours foraging. We spent about that much time on your absorption rate.",
    "Some squirrels cache tens of thousands of nuts a year across thousands of spots. Comparatively, your comp list is very manageable.",
    "Squirrels will fake-bury a nut in front of a rival, then stash the real one elsewhere. No sleight of hand here — just your real numbers.",
    "A squirrel can smell a buried acorn through a foot of dirt, but somehow still loses the car keys. We haven't lost anything, promise.",
    "Squirrels' back legs rotate almost backward for a headfirst descent — showing off, mostly. Our report will land more gracefully.",
    "Squirrels don't hibernate — they just nap a lot and hoard snacks. Honestly, relatable, and also basically what your data's been doing until now.",
    "A single mature oak can drop 10,000 acorns in a good year. We were slightly more selective with your comps.",
    "Oaks can live over 400 years — this loading screen will not test that patience.",
    "It takes an oak about 20 years before it produces its first real acorn crop. Yours is coming up momentarily.",
    "Oak wood was once the gold standard for shipbuilding — sturdy, reliable, built to last. We had the same goal for this report.",
    "An oak's canopy can shade a quarter acre on its own. Your market data, similarly, covers a lot of ground.",
    "Oaks host more caterpillar species than almost any other tree — busy little ecosystem. Your comp list is a bit tidier.",
    "A 'mast year' is when oaks produce way more acorns than usual, all at once. Consider this report your mast year for market data.",
    "The word 'acorn' descends from an Old English word basically meaning 'berry of the open field.' We've upgraded the packaging since then.",
    "Oaks are wind-pollinated, not bee-pollinated — no middleman required. We cut out a few of those too.",
    "Some oak roots run deeper than the tree is tall, quietly doing the real work underground. Kind of like everything behind this loading screen.",
    "Raleigh has planted tens of thousands of trees through its urban forestry efforts. We only had to plant one report today: yours.",
    "An oak tree can support over 500 species of moths and butterflies. Your listing just needs to support one really good offer.",
    "Acorns are technically a fruit, not a nut. We're not going to argue technicalities about your listing, though — a good comp's a good comp.",
    "The oldest oaks in North Carolina predate the state itself. This app, mercifully, does not run on that timeline.",
    "Cracking this nut open for you now.",
    "Squirreling away your data point by point.",
    "Sorting the good acorns from the empty shells — your comps edition.",
    "No nuts were harmed in the making of this report.",
    "Stashing your stats where we can actually find them again.",
    "This is the part where we act very busy and very squirrelly.",
    "Counting acorns so you don't have to.",
    "Digging through the underbrush for your market data.",
    "We promise this cache won't be forgotten by spring.",
    "Assembling your report, nut by nut.",
    "Foraging through the fine print now.",
    "Your data is out of its shell and almost ready.",
    "Filing this one under 'definitely not lost in the yard.'",
    "Bushy-tailed and ready to report.",
    "Climbing out on a limb to get you the good numbers.",
    "Hoarding insights, one comp at a time.",
    "Shaking the tree to see what data falls out.",
    "Building you a report sturdy enough to survive a Raleigh windstorm.",
    "Almost there — no acorns were left behind.",
    "Your report is ripening nicely on the branch.",
]


def money(value) -> str:
    """Dollar-formats a number for markdown text, with the $ escaped. Real
    bug we hit: two unescaped $ amounts in one st.caption/st.write string
    (e.g. "you're at $188, comps median $190") get parsed as a pair of LaTeX
    math delimiters by Streamlit's markdown renderer, producing garbled
    italic text instead of two plain numbers. Escaping avoids that entirely."""
    return f"\\${value:,.0f}"


def absorption_caption(stats: dict) -> str:
    if stats["months_of_supply"] is None:
        return ""
    period = "trailing 12 months" if stats["divisor_months"] == 12 else f"trailing {stats['divisor_months']} months (limited history available)"
    extra = []
    if stats["expired_count"]:
        extra.append(f"{stats['expired_count']} expired")
    if stats["withdrawn_count"]:
        extra.append(f"{stats['withdrawn_count']} withdrawn")
    if stats["hold_count"]:
        extra.append(f"{stats['hold_count']} on hold")
    if stats["unrecognized_count"]:
        extra.append(f"{stats['unrecognized_count']} with an unrecognized status")
    extra_note = f" ({', '.join(extra)}, excluded from the calculation)" if extra else ""
    return (
        f"Based on {stats['closed_count_trailing']} sales in the {period} (~{stats['monthly_pace']}/month). "
        f"{stats['closed_count_total']} total sold in the full data pulled{extra_note}."
    )


MIN_TOTAL_COMPS = 10
MIN_TRAILING_SALES = 6


def data_confidence_warning(row_count: int, stats: dict) -> str:
    """Small sample sizes make derived stats unreliable — surface that
    plainly rather than let a thin dataset masquerade as a solid number."""
    if row_count == 0:
        return None  # handled separately as an error, not a warning
    if row_count < MIN_TOTAL_COMPS:
        return f"Only {row_count} comparable listings found — with this little data, the numbers below may not be reliable."
    if stats["months_of_supply"] is not None and stats["closed_count_trailing"] < MIN_TRAILING_SALES:
        return (
            f"Only {stats['closed_count_trailing']} sales in the trailing 12 months — "
            "the absorption rate may not be reliable with this few data points."
        )
    return None


def render_property_type_breakdown(comparable_listings: list, subject_bucket: str = None):
    """Absorption rate per property type, as a bar chart — blending
    townhomes and single family (say) into one number hides real
    differences in how fast each actually moves in the same market at the
    same time. New Construction (if present) gets its own bar computed
    from contract date instead of close date, since a new-construction
    close date is stretched out by real build time rather than reflecting
    market speed the way it does for resale — same months-of-supply units,
    genuinely comparable to the other bars."""
    by_type = absorption_by_property_type(comparable_listings)
    nc_stats = compute_new_construction_absorption(comparable_listings)

    bars, skipped = [], []
    for bucket, stats in sorted(by_type.items(), key=lambda kv: -kv[1]["active_count"] - kv[1]["closed_count_total"]):
        if stats["months_of_supply"] is not None:
            bars.append({"label": bucket, "months_of_supply": stats["months_of_supply"], "highlight": bucket == subject_bucket})
        else:
            skipped.append(bucket)

    has_new_construction = nc_stats["months_of_supply"] is not None
    if has_new_construction:
        postal_codes = sorted({c["postal_code"] for c in comparable_listings if c.get("postal_code")})
        nc_label = f"New Construction in {postal_codes[0]}" if len(postal_codes) == 1 else "New Construction"
        bars.append({"label": nc_label, "months_of_supply": nc_stats["months_of_supply"], "highlight": False})

    if len(bars) <= 1:
        return  # nothing worth breaking out — not enough distinct, computable buckets to compare

    st.write("By property type:")
    chart = absorption_chart(bars)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)

    if has_new_construction:
        st.caption(
            "New Construction reflects time from listing to going under contract, not closing — "
            "this accounts for build/completion time that doesn't apply to resale homes."
        )
        nc_days = median_list_to_contract_days(comparable_listings, new_construction=True)
        resale_days = median_list_to_contract_days(comparable_listings, new_construction=False)
        if nc_days is not None or resale_days is not None:
            stat_cols = st.columns(2)
            if nc_days is not None:
                stat_cols[0].metric("New Construction: list to contract", f"{nc_days:.0f} days")
            if resale_days is not None:
                stat_cols[1].metric("Resale: list to contract", f"{resale_days:.0f} days")

    if skipped:
        st.caption(f"Not enough sold data yet to calculate a rate for: {', '.join(skipped)}.")


def render_zip_vs_subdivision_comparison(comparable_listings: list, subject_subdivision: str, subject_property_type: str):
    """Side-by-side comparison of the subject's own subdivision against the
    rest of the zip it sits in, both filtered to the subject's own property
    type first. Only renders when the subject's subdivision is known and
    Amy's CSV pull is zip-wide enough to actually have something outside
    the subdivision to compare against."""
    result = subdivision_vs_zip_absorption(comparable_listings, subject_subdivision, subject_property_type)
    if result is None:
        return

    sub_stats, zip_stats = result["subdivision"], result["rest_of_zip"]
    bars = []
    if sub_stats["months_of_supply"] is not None:
        bars.append({"label": subject_subdivision, "months_of_supply": sub_stats["months_of_supply"], "highlight": True})
    if zip_stats["months_of_supply"] is not None:
        postal_codes = sorted({c["postal_code"] for c in comparable_listings if c.get("postal_code")})
        zip_label = f"Rest of {postal_codes[0]}" if len(postal_codes) == 1 else "Rest of ZIP"
        bars.append({"label": zip_label, "months_of_supply": zip_stats["months_of_supply"], "highlight": False})

    if len(bars) < 2:
        return  # not enough data on one or both sides yet to show a meaningful comparison

    st.write(f"{subject_subdivision} vs. the rest of the zip:")
    chart = absorption_chart(bars)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)


def render_weekly_contracts_chart(comparable_listings: list, subject_property_type: str):
    """Weekly contract-signing pace for the subject's own property type,
    over roughly the last 2 years — a market-pulse view, not a comparison,
    so it's filtered narrower than the absorption charts on purpose:
    townhome and single-family buyers can react to rate moves on very
    different timelines."""
    if not subject_property_type:
        return
    weekly = weekly_contracts(comparable_listings, subject_property_type)
    if not any(w["count"] for w in weekly):
        return  # no contract-date data yet for this property type

    bucket = bucket_property_type(subject_property_type)
    st.write(f"Weekly contracts — {bucket} (last ~2 years):")
    chart = weekly_contracts_chart(weekly)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)


def build_listing_url(link_or_reference):
    """MLS# → a search link on the agent's own site. Only meaningful for
    active listings — pending/closed ones won't show up in an active search."""
    if not link_or_reference:
        return None
    match = re.search(r"\d+", str(link_or_reference))
    if not match:
        return None
    return BRAND["search_url_template"].format(mls_number=match.group())


def with_listing_links(comparable_listings: list) -> list:
    enriched = []
    for c in comparable_listings:
        c = dict(c)
        c["listing_url"] = build_listing_url(c.get("link_or_reference")) if c.get("status") == "active" else None
        enriched.append(c)
    return enriched


COMP_STATUS_GROUPS = [
    ("active", "Active"),
    ("pending", "Pending"),
    ("closed", "Closed"),
    ("failed", "Failed (expired/withdrawn)"),
    ("other", "Other"),
]

SOLDS_WINDOW_OPTIONS = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12, "All time": None}
DEFAULT_SOLDS_WINDOW = "Last 3 months"

COMPS_SCOPE_OPTIONS = {"All": "all", "Subdivision only": "subdivision"}
DEFAULT_COMPS_SCOPE = "All"


def comps_by_status(comparable_listings: list) -> dict:
    """Splits comps into Active / Pending / Closed / Failed (expired or
    withdrawn) / Other (hold, unrecognized statuses) — a flat table mixing all
    of these together makes it hard to tell what's actually competing right
    now vs. what already sold or came off market without selling."""
    buckets = {key: [] for key, _ in COMP_STATUS_GROUPS}
    for c in comparable_listings:
        status = c.get("status")
        if status in ("active", "pending", "closed"):
            buckets[status].append(c)
        elif status in ("expired", "withdrawn"):
            buckets["failed"].append(c)
        else:
            buckets["other"].append(c)
    return buckets


def render_comps_tables(comparable_listings: list):
    buckets = comps_by_status(comparable_listings)
    for key, label in COMP_STATUS_GROUPS:
        rows = buckets[key]
        if not rows:
            continue
        st.write(f"{label} ({len(rows)}):")
        if key == "active":
            st.dataframe(
                with_listing_links(rows),
                width="stretch",
                column_config={"listing_url": st.column_config.LinkColumn("Listing", display_text="View")},
            )
        else:
            st.dataframe(rows, width="stretch")


COMP_DISPLAY_COLUMNS = [
    "address", "status", "list_price", "original_list_price", "sold_price",
    "square_feet", "days_on_market", "close_date", "property_type", "source",
    "excluded", "excluded_reason",
]


def _project_comp_for_display(row: dict, include_link: bool) -> dict:
    projected = {col: row.get(col) for col in COMP_DISPLAY_COLUMNS}
    if include_link:
        projected["listing_url"] = build_listing_url(row.get("link_or_reference")) if row.get("status") == "active" else None
    return projected


def _project_viewer_overlap_comp(row: dict, since_field: str) -> dict:
    """For the "people who viewed/saved your listing also viewed/saved"
    tables — a curated subset of fields plus the date the overlap was first
    flagged, and a link for active comps."""
    return {
        "address": row.get("address"),
        "status": row.get("status"),
        "list_price": row.get("list_price"),
        "sold_price": row.get("sold_price"),
        since_field: row.get(since_field),
        "listing_url": build_listing_url(row.get("link_or_reference")) if row.get("status") == "active" else None,
    }


def render_viewer_overlap_table(comps: list, since_field: str, label: str):
    st.write(f"**{label}** ({len(comps)}):")
    st.dataframe(
        [_project_viewer_overlap_comp(c, since_field) for c in comps],
        width="stretch",
        column_config={
            since_field: st.column_config.TextColumn("First flagged"),
            "listing_url": st.column_config.LinkColumn("Listing", display_text="View"),
        },
        hide_index=True,
    )


def render_comps_editor(known_comps: dict) -> dict:
    """Editable comps tables, split by status. Only Exclude + Reason are
    editable — everything else is read-only, pulled straight from
    extraction. Excluded comps still show here (never hidden), just get left
    out of the absorption/median/property-type math. Returns the
    possibly-edited known_comps dict for the caller to persist."""
    updated = {k: dict(v) for k, v in known_comps.items()}
    buckets = comps_by_status(all_comps_list(known_comps))

    for key, label in COMP_STATUS_GROUPS:
        rows = buckets[key]
        if not rows:
            continue
        st.write(f"{label} ({len(rows)}):")
        is_active = key == "active"
        display_rows = [_project_comp_for_display(r, include_link=is_active) for r in rows]

        column_config = {
            "excluded": st.column_config.CheckboxColumn("Exclude"),
            "excluded_reason": st.column_config.TextColumn("Reason"),
        }
        disabled_cols = [c for c in COMP_DISPLAY_COLUMNS if c not in ("excluded", "excluded_reason")]
        if is_active:
            column_config["listing_url"] = st.column_config.LinkColumn("Listing", display_text="View")

        edited = st.data_editor(
            display_rows,
            width="stretch",
            column_config=column_config,
            disabled=disabled_cols,
            key=f"comps_editor_{key}",
            hide_index=True,
        )

        for row in edited:
            comp_key = address_key(row.get("address"))
            if comp_key and comp_key in updated:
                updated[comp_key]["excluded"] = row.get("excluded", False)
                updated[comp_key]["excluded_reason"] = row.get("excluded_reason")

    return updated


def filter_stale_notes(notes: list, merged: dict) -> list:
    """Drop notes complaining a specific file lacks comp-level detail (addresses,
    prices, sqft for its comps) when the overall merged report already has
    comparable-listing data from another source — e.g. a ShowingTime PDF that
    only shows aggregate comp stats isn't actually a data gap if the CSV
    already gives us those same comps' full details."""
    if not merged.get("comparable_listings"):
        return notes
    filtered = []
    for note in notes:
        lower = note.lower()
        about_comp_detail = "comparable" in lower and ("individual" in lower or "detail" in lower or "address" in lower)
        if about_comp_detail:
            continue
        filtered.append(note)
    return filtered


def render_data_scope(comparable_listings: list, stats: dict):
    """Discloses what scope actually produced these figures — geography,
    price/sqft range, property types, and the date window used — the same
    kind of transparency April liked in her ShowingTime report's 'Applied
    filters' section, built from the data itself rather than guessed intent."""
    scope = data_scope_summary(comparable_listings)
    lines = []
    if scope["geography"]:
        lines.append(scope["geography"])
    if scope["property_types"]:
        lines.append(", ".join(scope["property_types"]))
    if scope["price_range"]:
        lo, hi = scope["price_range"]
        lines.append(f"{money(lo)} - {money(hi)} observed")
    if scope["sqft_range"]:
        lo, hi = scope["sqft_range"]
        lines.append(f"{lo:,}-{hi:,} sqft observed")
    if stats.get("closed_window_date_range"):
        lo, hi = stats["closed_window_date_range"]
        lines.append(f"sold-comp window: {lo} to {hi}")

    if lines:
        st.caption("Data scope: " + " · ".join(lines))


DEFAULTS = {
    "view": "menu",
    "slug": None,
    "stage": "csv",
    "sources": [],
    "processed_files": set(),
    "csv_result": None,
    "csv_source_name": None,
    "quiet_errors": [],
    "known_comps": None,
    "known_feedback": None,
    "preparer_name": "April Auman",
    "preparer_brokerage": "Coldwell Banker Advantage",
    "preparer_contact": "",
    "preparer_code": "",
    "review_autosaved": False,
    "conflict_resolutions": {},
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def current_agent_slug() -> str:
    """Derives the isolation key from "Prepared by" plus a private numeric
    code — not real per-user authentication (see property_slug()'s
    docstring), just harder to guess than a name alone. Someone would need
    to know both to land on the same slug and see another agent's saved
    properties."""
    name = st.session_state.get("preparer_name") or ""
    code = st.session_state.get("preparer_code") or ""
    return storage.slugify(f"{name}-{code}")


def goto(view, slug=None, stage="csv"):
    st.session_state["view"] = view
    st.session_state["slug"] = slug
    st.session_state["stage"] = stage
    st.session_state["sources"] = []
    st.session_state["processed_files"] = set()
    st.session_state["csv_result"] = None
    st.session_state["csv_source_name"] = None
    st.session_state["quiet_errors"] = []
    st.session_state["known_comps"] = None
    st.session_state["known_feedback"] = None
    st.session_state["review_autosaved"] = False
    st.session_state["conflict_resolutions"] = {}


def _scroll_facts(placeholder, header_text, stop_event, progress=None):
    """Runs on a background thread so the fact rotates *during* a blocking
    Gemini call, not just once per file. Shuffled fresh per call rather than
    always starting at index 0 — most uploads are quick enough that a
    plain in-order cycle only ever showed the first couple of facts.
    progress (optional): a 0-1 fraction shown as a progress bar — e.g. while
    working on file 1 of 5, pass 0.2, not 0.0, since the bar reflects how far
    through the batch we're currently positioned, not how many are fully
    done."""
    facts = random.sample(RALEIGH_FACTS, len(RALEIGH_FACTS))
    i = 0
    while not stop_event.is_set():
        with placeholder.container():
            st.info(header_text)
            if progress is not None:
                st.progress(progress)
            st.caption(f"🌳🐿️ {facts[i % len(facts)]}")
        i += 1
        stop_event.wait(5.0)


class scrolling_loader:
    """Context manager: shows `header_text` in `placeholder` with a Raleigh
    fact that scrolls every ~2 seconds for as long as the block runs.
    Optionally shows a progress bar (see _scroll_facts)."""

    def __init__(self, placeholder, header_text, progress=None):
        self.placeholder = placeholder
        self.header_text = header_text
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=_scroll_facts, args=(placeholder, header_text, self.stop_event, progress)
        )
        add_script_run_ctx(self.thread)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        self.thread.join()


# ---------------------------------------------------------------- MENU VIEW
def render_menu():
    render_header("RootedReports")
    st.subheader("Get started")

    properties = storage.list_properties(current_agent_slug())

    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.markdown("**Work on an existing property**")
        if not properties:
            st.caption("No properties yet — add one to get started.")
        else:
            with st.container(key="properties-list"):
                for slug, profile in properties:
                    has_saved_report = bool(storage.load_history(slug))
                    row, jump_col, delete_col = st.columns([4, 2, 1])
                    with row:
                        if st.button(profile.get("address") or slug, key=f"select-{slug}", width="stretch"):
                            goto("property", slug)
                            st.rerun()
                    with jump_col:
                        if has_saved_report:
                            if st.button("Jump to report", key=f"jump-{slug}", width="stretch"):
                                goto("property", slug, stage="review")
                                st.rerun()
                    with delete_col:
                        with st.popover("🗑️"):
                            st.write(f"Delete **{profile.get('address') or slug}**? This removes all saved reports too.")
                            if st.button("Yes, delete", key=f"confirm-delete-{slug}"):
                                storage.delete_property(slug)
                                st.rerun()

    with col2, st.container(border=True):
        st.markdown("**Add a new property**")
        st.caption("Upload an MLS cut sheet, or just type the address, to get started.")
        if st.button("Add a new property", width="stretch"):
            goto("new_property")
            st.rerun()

    render_footer()


# --------------------------------------------------------- NEW PROPERTY VIEW
def render_new_property():
    render_header("Add a new property")
    if st.button("← Back to menu"):
        goto("menu")
        st.rerun()

    cut_sheet = st.file_uploader("MLS cut sheet", type=["pdf"])
    address = st.text_input(
        "Property address" + ("" if cut_sheet is None else " (optional — we'll read it from the cut sheet)")
    )

    if st.button("Create property", type="primary", disabled=not address.strip() and cut_sheet is None):
        profile = {"address": address.strip()} if address.strip() else {}

        if cut_sheet is not None:
            client = get_client()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(cut_sheet.getvalue())
                tmp_path = tmp.name
            try:
                loading = st.empty()
                with scrolling_loader(loading, "Reading the cut sheet..."):
                    extracted = extract_json(client, tmp_path, PROFILE_PROMPT)
                loading.empty()
                if address.strip():  # manual entry wins if the agent typed one anyway
                    extracted["address"] = address.strip()
                profile = extracted
            except Exception as e:
                print(f"[extraction error] {cut_sheet.name}: {e}")
            finally:
                os.unlink(tmp_path)

        final_address = profile.get("address")
        if not final_address:
            st.error("Couldn't find an address in that cut sheet — type it in above and try again.")
            st.stop()

        agent_slug = current_agent_slug()
        slug = storage.property_slug(agent_slug, final_address)
        storage.save_profile(slug, profile, agent_slug)
        goto("property", slug)
        st.rerun()

    render_footer()


# -------------------------------------------------------------- PROPERTY VIEW
def render_property():
    slug = st.session_state["slug"]
    profile = storage.load_profile(slug)
    if profile is None:
        st.error("Couldn't find that property.")
        if st.button("← Back to menu"):
            goto("menu")
            st.rerun()
        return

    render_header(profile.get("address") or slug)
    if st.button("← Back to menu"):
        goto("menu")
        st.rerun()

    history = storage.load_history(slug)
    stage = st.session_state["stage"]

    if stage == "csv":
        with st.expander("Property details (from MLS cut sheet)"):
            for field in ["list_date", "days_on_market", "bedrooms", "bathrooms", "square_feet", "subdivision", "lot_size", "year_built", "mls_number"]:
                if profile.get(field):
                    st.write(f"**{field.replace('_', ' ').title()}:** {profile[field]}")
            if profile.get("remarks"):
                st.write(profile["remarks"])

        if history:
            with st.expander(f"Past reports ({len(history)})"):
                for entry in reversed(history):
                    st.markdown(f"**{entry['date']}**")
                    stats = []
                    if entry.get("list_price"):
                        stats.append(f"List price: {entry['list_price']}")
                    if entry.get("days_on_market"):
                        stats.append(f"DOM: {entry['days_on_market']}")
                    showings = entry.get("showings") or {}
                    if showings.get("total"):
                        stats.append(f"Showings: {showings['total']}")
                    if stats:
                        st.caption(" · ".join(stats))
                    if entry.get("commentary"):
                        st.write(entry["commentary"])
                    st.divider()

        render_csv_stage(profile)
    elif stage == "reports":
        render_reports_stage()
    elif stage == "conflicts":
        render_conflicts_stage(slug, profile, history)
    elif stage == "review":
        render_review_stage(slug, profile, history)

    render_footer()


CONFLICT_FIELD_LABELS = {
    "address": "Address",
    "list_price": "List price",
    "original_list_price": "Original list price",
    "list_date": "List date",
    "days_on_market": "Days on market",
    "square_feet": "Square feet",
    "showings.total": "Showings (total)",
    "showings.last_30_days": "Showings (last 30 days)",
}

CONFLICT_FIELD_FORMATTERS = {
    "list_price": lambda v: f"${v:,.0f}",
    "original_list_price": lambda v: f"${v:,.0f}",
    "square_feet": lambda v: f"{v:,} sqft",
    "days_on_market": lambda v: f"{v} days",
}


def format_conflict_value(field, value):
    formatter = CONFLICT_FIELD_FORMATTERS.get(field)
    if formatter:
        try:
            return formatter(value)
        except (TypeError, ValueError):
            pass
    return str(value)


def build_merged(history):
    """The merged view for this visit — fresh sources if any were uploaded,
    else the last saved snapshot (which never carries `_conflicts`, since
    save_snapshot strips it, so falling back to history never re-surfaces
    conflicts already settled on a prior visit)."""
    if st.session_state["sources"]:
        return merge_extractions(st.session_state["sources"])
    if history:
        return {**empty_merged(), **{k: v for k, v in history[-1].items() if k != "date"}}
    return empty_merged()


def merged_with_resolutions(history):
    """build_merged() plus whatever the agent already picked on the Resolve
    conflicts step. A stored resolution for a field no longer in
    `_conflicts` (e.g. the agent went back and re-uploaded a different set
    of reports) is simply ignored rather than force-applied."""
    merged = build_merged(history)
    for field, value in st.session_state["conflict_resolutions"].items():
        if field not in merged["_conflicts"]:
            continue
        if "." in field:
            parent, child = field.split(".", 1)
            merged[parent][child] = value
        else:
            merged[field] = value
        merged["_conflicts"].pop(field, None)
    return merged


def render_conflicts_stage(slug, profile, history):
    merged = merged_with_resolutions(history)

    if not merged["_conflicts"]:
        st.session_state["stage"] = "review"
        st.rerun()
        return

    st.subheader("Step 3 of 4: Resolve conflicts")
    st.caption("Your reports didn't agree on these — pick the correct value for each.")

    for field, candidates in merged["_conflicts"].items():
        label = CONFLICT_FIELD_LABELS.get(field, field.replace("_", " ").replace(".", " ").title())
        options = [f"{format_conflict_value(field, c['value'])}  —  {c['source']}" for c in candidates]
        choice = st.radio(label, options, index=None, key=f"conflict_radio_{field}")
        if choice is not None:
            st.session_state["conflict_resolutions"][field] = candidates[options.index(choice)]["value"]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state["stage"] = "reports"
            st.rerun()
    with col2:
        if st.button("Continue to review", type="primary"):
            st.session_state["stage"] = "review"
            st.rerun()


def render_csv_stage(profile):
    name_col, code_col, brokerage_col = st.columns([2, 1, 2])
    with name_col:
        st.text_input("Prepared by", key="preparer_name")
    with code_col:
        st.text_input("Access code", key="preparer_code", type="password", help="A private code only you know — combined with your name to keep your saved properties from being guessed by someone else typing your name.")
    with brokerage_col:
        st.text_input("Brokerage", key="preparer_brokerage")
    st.text_input("Contact info (optional — shown on the report if filled in)", key="preparer_contact")

    st.subheader("Step 1 of 4: MLS comp data")
    st.caption(
        "Upload a CSV export covering the last 2 years — active, pending, active under contract, "
        "closed/sold, expired, withdrawn, and coming soon. Needed for an industry-standard absorption "
        "rate calculation. Don't have one yet? Skip this step for now."
    )
    csv_file = st.file_uploader("MLS CSV export", type=["csv"], label_visibility="collapsed")

    if csv_file is not None and st.session_state["csv_source_name"] != csv_file.name:
        st.session_state["csv_result"] = parse_mls_csv(csv_file)
        st.session_state["csv_source_name"] = csv_file.name

    result = st.session_state["csv_result"]
    if result:
        stats = compute_absorption(result["comparable_listings"])

        st.metric("Total comparable listings found", result["row_count"])
        warning = data_confidence_warning(result["row_count"], stats)
        if warning:
            st.warning(warning)

        cols = st.columns(4)
        cols[0].metric("Active", stats["active_count"])
        cols[1].metric("Pending", stats["pending_count"])
        cols[2].metric("Sold (trailing 12mo)", stats["closed_count_trailing"])
        if stats["months_of_supply"] is not None:
            cols[3].metric("Months of supply", stats["months_of_supply"])
        st.caption(absorption_caption(stats))
        if result["unmapped_fields"]:
            st.caption("Some columns in this file weren't recognized — the counts above might be incomplete.")
        with st.expander("See the comps"):
            render_comps_tables(result["comparable_listings"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue", type="primary", disabled=result is None or result["row_count"] == 0):
            st.session_state["sources"].append(
                {"source": "MLS CSV export", "data": {"comparable_listings": result["comparable_listings"]}}
            )
            st.session_state["stage"] = "reports"
            st.rerun()
    with col2:
        if st.button("Skip this step"):
            st.session_state["stage"] = "reports"
            st.rerun()

    if result is not None and result["row_count"] == 0:
        st.error("This file didn't produce any recognizable comps — double-check it's the right export, or skip this step.")


def render_reports_stage():
    st.subheader("Step 2 of 4: Other reports")
    st.caption("Upload activity or marketing reports for this property — Doorify, ShowingTime, etc.")
    uploaded_files = st.file_uploader(
        "Upload reports",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    unprocessed = [f for f in uploaded_files if f.name not in st.session_state["processed_files"]]
    if unprocessed:
        client = get_client()
        loading = st.empty()
        for i, f in enumerate(unprocessed):
            header = f"Analyzing **{f.name}**  ·  file {i + 1} of {len(unprocessed)}"
            suffix = "." + f.name.split(".")[-1]
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(f.getvalue())
                tmp_path = tmp.name
            try:
                with scrolling_loader(loading, header, progress=(i + 1) / len(unprocessed)):
                    data = extract_json(client, tmp_path, ACTIVITY_PROMPT)
                st.session_state["sources"].append({"source": f.name, "data": data})
            except Exception as e:
                print(f"[extraction error] {f.name}: {e}")  # kept out of the user-facing UI on purpose
                st.session_state["quiet_errors"].append(f.name)
            finally:
                os.unlink(tmp_path)
            st.session_state["processed_files"].add(f.name)
        loading.empty()

    if st.session_state["quiet_errors"]:
        names = ", ".join(st.session_state["quiet_errors"])
        st.caption(f"Heads up — we couldn't fully read: {names}. You can still continue; just double-check the numbers.")

    report_sources = [s for s in st.session_state["sources"] if s["source"] != "MLS CSV export"]
    if report_sources:
        st.success(f"{len(report_sources)} report{'s' if len(report_sources) != 1 else ''} processed.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state["stage"] = "csv"
            st.rerun()
    with col2:
        if st.button("Continue", type="primary"):
            st.session_state["stage"] = "conflicts"
            st.rerun()


def render_review_stage(slug, profile, history):
    st.subheader("Step 4 of 4: Review")
    st.caption("Each section below is collapsed by default — open whichever ones you need to check or edit.")

    if not st.session_state["sources"] and history:
        st.info(f"No new reports uploaded this visit — showing your last saved report ({history[-1]['date']}).")
    merged = merged_with_resolutions(history)

    if st.session_state["known_comps"] is None:
        st.session_state["known_comps"] = storage.load_known_comps(slug)
    if merged["comparable_listings"]:
        st.session_state["known_comps"] = update_known_comps(
            st.session_state["known_comps"], merged["comparable_listings"]
        )

    if st.session_state["known_feedback"] is None:
        st.session_state["known_feedback"] = storage.load_known_feedback(slug)
    if merged["feedback"]:
        st.session_state["known_feedback"] = update_known_feedback(
            st.session_state["known_feedback"], merged["feedback"]
        )

    with st.expander("Basic facts", expanded=True):
        merged["list_price"] = st.number_input("List price", value=float(merged.get("list_price") or 0), step=1000.0)
        merged["original_list_price"] = st.number_input(
            "Original list price", value=float(merged.get("original_list_price") or 0), step=1000.0
        )
        merged["list_date"] = st.text_input("List date", value=merged.get("list_date") or "")
        merged["days_on_market"] = st.number_input(
            "Days on market", value=int(merged.get("days_on_market") or 0), step=1
        )
        merged["square_feet"] = st.number_input(
            "Square feet", value=int(merged.get("square_feet") or 0), step=50
        )

    with st.expander("Price history & reductions"):
        if merged.get("list_date") or merged.get("original_list_price"):
            date_part = f"Listed {merged['list_date']}" if merged.get("list_date") else "Listed"
            price_part = f" at {money(merged['original_list_price'])}" if merged.get("original_list_price") else ""
            st.caption(f"{date_part}{price_part}.")

        reductions = price_reductions(merged["price_history"])
        if reductions["chronological"]:
            if reductions["count"]:
                st.metric(
                    "Total reduced",
                    f"${reductions['total_amount']:,}",
                    delta=f"-{reductions['count']} reduction{'s' if reductions['count'] != 1 else ''}",
                )
            else:
                st.caption("No reductions found — price has only gone up or stayed flat in the data we have.")
            st.dataframe(reductions["chronological"], width="stretch")
        else:
            st.caption("No price history found in the uploaded reports.")

        calc_comps_for_reductions = active_for_calculation(st.session_state["known_comps"]) if st.session_state["known_comps"] else []
        if calc_comps_for_reductions:
            comp_reduction_stats = comp_price_reduction_stats(calc_comps_for_reductions)
            st.write("Price drops among comps:")

            pending_stats = comp_reduction_stats["pending"]
            if pending_stats["pct"] is not None:
                st.caption(
                    f"- Pending: {pending_stats['reduced']} of {pending_stats['known']} had a price drop "
                    f"before going pending (~{pending_stats['pct']}%)."
                )
            elif pending_stats["known"]:
                st.caption(
                    f"- Pending: only {pending_stats['known']} pending comp{'s' if pending_stats['known'] != 1 else ''} "
                    "with known pricing — too few to trust a percentage."
                )
            else:
                st.caption("- Pending: no pending comps with known original/current list price yet.")

            closed_stats = comp_reduction_stats["closed"]
            if closed_stats["pct"] is not None:
                st.caption(
                    f"- Closed: {closed_stats['reduced']} of {closed_stats['known']} had a price drop "
                    f"before selling (~{closed_stats['pct']}%)."
                )
            elif closed_stats["known"]:
                st.caption(
                    f"- Closed: only {closed_stats['known']} closed comp{'s' if closed_stats['known'] != 1 else ''} "
                    "with known pricing — too few to trust a percentage."
                )
            else:
                st.caption("- Closed: no closed comps with known original/current list price yet.")

            trend = comp_reduction_stats["trend"]
            if trend["enough_data"]:
                st.caption(
                    f"- Price-drop rate among closed comps looks **{trend['direction']}** over the last year "
                    f"(~{trend['earlier_pct']}% earlier vs ~{trend['recent_pct']}% more recently)."
                )
                trend_chart = price_reduction_trend_chart(trend["monthly_pcts"])
                if trend_chart is not None:
                    st.altair_chart(trend_chart, use_container_width=True)
            else:
                st.caption(
                    f"- Not enough data yet to tell whether price drops are trending over the last year "
                    f"(usable data for {trend['months_with_data']} of the last 12 months — need at least "
                    f"{MIN_MONTHS_WITH_DATA})."
                )

    with st.expander("Showings & Feedback on Subject"):
        merged["showings"]["total"] = st.number_input(
            "Showings (total)", value=int(merged["showings"].get("total") or 0), step=1
        )
        merged["showings"]["last_30_days"] = st.number_input(
            "Showings (last 30 days)", value=int(merged["showings"].get("last_30_days") or 0), step=1
        )
        st.write("Feedback — verbatim quotes, not summarized themes. Check Follow-up to flag a buyer worth watching; it persists across future visits.")
        feedback_rows = all_feedback_list(st.session_state["known_feedback"])
        feedback_df = pd.DataFrame(
            feedback_rows, columns=["date", "quote", "source", "following_up", "follow_up_note"]
        )
        edited_feedback = st.data_editor(
            feedback_df,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "quote": st.column_config.TextColumn("Quote", width="large"),
                "source": st.column_config.TextColumn("Source", disabled=True),
                "following_up": st.column_config.CheckboxColumn("Follow-up"),
                "follow_up_note": st.column_config.TextColumn("Note"),
            },
            column_order=["date", "quote", "source", "following_up", "follow_up_note"],
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key="feedback_editor",
        )
        edited_feedback_rows = edited_feedback.where(edited_feedback.notna(), None).to_dict("records")
        st.session_state["known_feedback"] = apply_feedback_edits(
            st.session_state["known_feedback"], edited_feedback_rows
        )

    with st.expander("Online traffic"):
        if merged["traffic_by_source"]:
            st.caption("Kept separate — different platforms count differently:")
            for entry in merged["traffic_by_source"]:
                st.caption(f"- {entry['source']}: {entry['views'] or 0} views, {entry['saves'] or 0} saves")
        else:
            st.caption("No online traffic data found in the uploaded reports.")

    with st.expander("Momentum"):
        current_views = total_views(merged)
        if not history:
            st.info("This is the first report for this property — momentum will show starting next time.")
        else:
            last_date = date.fromisoformat(history[-1]["date"])
            days_ago = (date.today() - last_date).days
            st.caption(f"Last report saved {days_ago} day{'s' if days_ago != 1 else ''} ago ({history[-1]['date']})")
            if len(history) == 1:
                gain = current_views - total_views(history[-1])
                st.write(f"Views gained since last report: {gain:+d}")
            else:
                labels, gains = [], []
                for i in range(1, len(history)):
                    gains.append(total_views(history[i]) - total_views(history[i - 1]))
                    labels.append(history[i]["date"])
                gains.append(current_views - total_views(history[-1]))
                labels.append("Today")
                st.bar_chart(dict(zip(labels, gains)))

    known_comps = st.session_state["known_comps"]
    if known_comps or merged["price_bands"]:
        with st.expander("Market comparison"):
            if known_comps:
                st.write("Comparable listings — check Exclude on any comp that isn't a fair comparison (e.g. a unique property) to leave it out of the numbers below:")
                known_comps = render_comps_editor(known_comps)
                st.session_state["known_comps"] = known_comps

                calc_comps = active_for_calculation(known_comps)
                excluded_count = len(known_comps) - len(calc_comps)
                if excluded_count:
                    st.caption(f"{excluded_count} comp{'s' if excluded_count != 1 else ''} excluded from the numbers below.")

                stats = compute_absorption(calc_comps)
                row_count = len(calc_comps)

                st.metric("Total comparable listings used", row_count)
                warning = data_confidence_warning(row_count, stats)
                if warning:
                    st.warning(warning)

                cols = st.columns(4)
                cols[0].metric("Active", stats["active_count"])
                cols[1].metric("Pending", stats["pending_count"])
                cols[2].metric("Sold (trailing 12mo)", stats["closed_count_trailing"])
                if stats["months_of_supply"] is not None:
                    cols[3].metric("Months of supply", stats["months_of_supply"])
                    st.caption(absorption_caption(stats))
                subject_bucket = bucket_property_type(profile.get("property_type")) if profile.get("property_type") else None
                render_property_type_breakdown(calc_comps, subject_bucket)
                render_zip_vs_subdivision_comparison(calc_comps, profile.get("subdivision"), profile.get("property_type"))
                render_weekly_contracts_chart(calc_comps, profile.get("property_type"))

                median_psf = median_comp_price_per_sqft(calc_comps)
                if median_psf:
                    subject_psf = price_per_sqft(merged.get("list_price"), merged.get("square_feet"))
                    you = money(subject_psf) if subject_psf else "unknown"
                    st.write("Compared to the comps:")
                    st.caption(f"- Price per sq ft: you're at {you}, comps median {money(median_psf)}")

                dom_stats = dom_benchmark(calc_comps)
                if dom_stats["active_median_dom"] or dom_stats["pending_median_dom"]:
                    st.write("Days on market — active vs. pending:")
                    if dom_stats["pending_median_dom"]:
                        st.caption(
                            f"- Comps that went pending typically did so by day {dom_stats['pending_median_dom']} — "
                            "a rough benchmark for when a listing 'should' go under contract, if it's going to."
                        )
                    if dom_stats["active_median_dom"]:
                        st.caption(f"- Comps still active have a median of {dom_stats['active_median_dom']} days on market so far.")
                    subject_dom = merged.get("days_on_market")
                    if subject_dom and dom_stats["pending_median_dom"]:
                        diff = subject_dom - dom_stats["pending_median_dom"]
                        if diff > 0:
                            st.caption(f"- You're at {subject_dom} days — {diff} days past that benchmark.")
                        else:
                            st.caption(f"- You're at {subject_dom} days — still within that typical window.")

                render_data_scope(calc_comps, stats)

                st.write("**Sample chart** — price vs. days on market for active/pending/closed comps *(prototype)*:")
                scope_col, recency_col = st.columns(2)
                with scope_col:
                    scope_label = st.selectbox(
                        "Comps shown in chart", list(COMPS_SCOPE_OPTIONS.keys()),
                        index=list(COMPS_SCOPE_OPTIONS.keys()).index(DEFAULT_COMPS_SCOPE),
                        key="comps_scope_label",
                    )
                with recency_col:
                    solds_window_label = st.selectbox(
                        "Solds shown in chart", list(SOLDS_WINDOW_OPTIONS.keys()),
                        index=list(SOLDS_WINDOW_OPTIONS.keys()).index(DEFAULT_SOLDS_WINDOW),
                        key="solds_window_label",
                    )
                scoped_comps = calc_comps
                if COMPS_SCOPE_OPTIONS[scope_label] == "subdivision":
                    scoped_comps = filter_by_subdivision(calc_comps, profile.get("subdivision"))
                comps_for_chart = filter_recent_closed(scoped_comps, months=SOLDS_WINDOW_OPTIONS[solds_window_label])
                market_rate_price = median_psf * merged["square_feet"] if median_psf and merged.get("square_feet") else None
                closed_median_dom = median_comp_days_on_market(
                    [c for c in comps_for_chart if c.get("status") == "closed"]
                )
                position_chart = price_position_chart(
                    comps_for_chart, merged.get("list_price"), merged.get("days_on_market"),
                    market_rate_price, closed_median_dom,
                )
                if position_chart is not None:
                    st.altair_chart(position_chart, use_container_width=True)
                else:
                    st.caption("Not enough comps with both a price and days-on-market to plot yet.")

                viewed = also_viewed_comps(calc_comps)
                if viewed:
                    render_viewer_overlap_table(viewed, "also_viewed_since", "People who viewed your listing also viewed")

                saved = also_saved_comps(calc_comps)
                if saved:
                    render_viewer_overlap_table(saved, "also_saved_since", "People who saved your listing also saved")

            if merged["price_bands"]:
                band = match_price_band(merged.get("list_price"), merged["price_bands"])

                st.write("**Sample chart** — showings by price band *(prototype)*:")
                band_chart = price_band_chart(merged["price_bands"], band)
                if band_chart is not None:
                    st.altair_chart(band_chart, use_container_width=True)

    if merged["_conflicts"] or merged["notes_on_missing_or_unclear_data"]:
        with st.expander("Data quality notes"):
            if merged["_conflicts"]:
                st.caption("Skipped on the Resolve conflicts step — pick the right value in Basic facts above:")
                for field, values in merged["_conflicts"].items():
                    label = CONFLICT_FIELD_LABELS.get(field, field.replace("_", " ").replace(".", " ").title())
                    detail = ", ".join(f"{format_conflict_value(field, v['value'])} ({v['source']})" for v in values)
                    st.caption(f"- {label}: {detail}")
            relevant_notes = filter_stale_notes(merged["notes_on_missing_or_unclear_data"], merged)
            if relevant_notes:
                st.caption("Notes on missing or unclear data:")
                for note in relevant_notes:
                    st.caption(f"- {note}")

    if not st.session_state.get("review_autosaved"):
        # Fires once per visit to this stage (not on every widget rerun —
        # see the flag reset in goto() and "Back to add more reports" below)
        # so reaching the point where a report can be printed is what saves
        # it, not a separate manual step the agent could forget to click.
        snapshot = {
            "date": date.today().isoformat(),
            **{k: v for k, v in merged.items() if k != "_conflicts"},
        }
        storage.save_snapshot(slug, snapshot)
        storage.save_known_comps(slug, st.session_state["known_comps"])
        storage.save_known_feedback(slug, st.session_state["known_feedback"])
        st.session_state["review_autosaved"] = True

    st.subheader("Save & export")
    st.caption("Saved — the next report for this property will compare against this one.")
    pdf_calc_comps = active_for_calculation(st.session_state["known_comps"]) if st.session_state["known_comps"] else None
    pdf_solds_window_label = st.session_state.get("solds_window_label", DEFAULT_SOLDS_WINDOW)
    pdf_solds_window_months = SOLDS_WINDOW_OPTIONS.get(pdf_solds_window_label, SOLDS_WINDOW_OPTIONS[DEFAULT_SOLDS_WINDOW])
    pdf_scope_label = st.session_state.get("comps_scope_label", DEFAULT_COMPS_SCOPE)
    pdf_comps_scope = COMPS_SCOPE_OPTIONS.get(pdf_scope_label, COMPS_SCOPE_OPTIONS[DEFAULT_COMPS_SCOPE])
    pdf_feedback = all_feedback_list(st.session_state["known_feedback"]) if st.session_state["known_feedback"] else None
    st.download_button(
        "Download PDF report",
        data=build_pdf(
            profile, merged, "", pdf_calc_comps, pdf_solds_window_months, pdf_feedback,
            st.session_state.get("preparer_name"),
            st.session_state.get("preparer_brokerage"),
            st.session_state.get("preparer_contact"),
            pdf_comps_scope,
        ),
        file_name=f"{slug}-report-{date.today().isoformat()}.pdf",
        mime="application/pdf",
    )

    if st.button("← Back to add more reports"):
        st.session_state["stage"] = "reports"
        st.session_state["review_autosaved"] = False
        st.session_state["conflict_resolutions"] = {}
        st.rerun()


view = st.session_state["view"]
if view == "menu":
    render_menu()
elif view == "new_property":
    render_new_property()
elif view == "property":
    render_property()
elif view == "terms":
    render_terms()
