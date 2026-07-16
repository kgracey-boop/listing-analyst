import os
import tempfile
from datetime import date

import streamlit as st

# Bridge Streamlit Cloud's secrets manager into os.environ, since the rest of
# this app reads config via os.environ (works locally via .env too). No-op
# if there's no secrets.toml (e.g. running locally).
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:
    pass

import db_storage as storage
from branding import inject_css, render_footer, render_header
from gemini_io import (
    ACTIVITY_PROMPT,
    FALLBACK_STORIES,
    PROFILE_PROMPT,
    TONE_PRESETS,
    extract_json,
    generate_commentary,
    get_client,
)
from merge import merge_extractions, total_views
from pdf_export import build_pdf

st.set_page_config(page_title="Listing Activity Report App", page_icon="🏠", layout="wide")
inject_css()


def require_passcode():
    """Simple shared-passcode gate. No-op if APP_PASSCODE isn't set (e.g. local dev)."""
    passcode = os.environ.get("APP_PASSCODE")
    if not passcode or st.session_state.get("authenticated"):
        return
    render_header("Listing Activity Report App")
    entered = st.text_input("Enter passcode", type="password")
    if st.button("Enter"):
        if entered == passcode:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect passcode.")
    st.stop()


require_passcode()

DEFAULTS = {
    "view": "menu",
    "slug": None,
    "sources": [],
    "processed_files": set(),
    "hunch": "",
    "tone_preset": "Warm & reassuring",
    "tone_notes": "",
    "commentary": "",
    "fallback_story": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def goto(view, slug=None):
    st.session_state["view"] = view
    st.session_state["slug"] = slug
    st.session_state["sources"] = []
    st.session_state["processed_files"] = set()
    st.session_state["hunch"] = ""
    st.session_state["tone_notes"] = ""
    st.session_state["commentary"] = ""
    st.session_state["fallback_story"] = None


# ---------------------------------------------------------------- MENU VIEW
def render_menu():
    render_header("Listing Activity Report App")
    st.subheader("Get started")

    properties = storage.list_properties()

    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.markdown("**Work on an existing property**")
        if not properties:
            st.caption("No properties yet — add one to get started.")
        else:
            with st.container(key="properties-list"):
                for slug, profile in properties:
                    row, delete_col = st.columns([5, 1])
                    with row:
                        if st.button(profile.get("address") or slug, key=f"select-{slug}", use_container_width=True):
                            goto("property", slug)
                            st.rerun()
                    with delete_col:
                        with st.popover("🗑️"):
                            st.write(f"Delete **{profile.get('address') or slug}**? This removes all saved reports too.")
                            if st.button("Yes, delete", key=f"confirm-delete-{slug}"):
                                storage.delete_property(slug)
                                st.rerun()

    with col2, st.container(border=True):
        st.markdown("**Add a new property**")
        st.caption("Type the address and upload the MLS cut sheet to get started.")
        if st.button("Add a new property", use_container_width=True):
            goto("new_property")
            st.rerun()

    render_footer()


# --------------------------------------------------------- NEW PROPERTY VIEW
def render_new_property():
    render_header("Add a new property")
    if st.button("← Back to menu"):
        goto("menu")
        st.rerun()

    address = st.text_input("Property address")
    cut_sheet = st.file_uploader("MLS cut sheet (optional, but fills in the details below)", type=["pdf"])

    if st.button("Create property", type="primary", disabled=not address.strip()):
        profile = {"address": address.strip()}

        if cut_sheet is not None:
            with st.spinner("Reading cut sheet with Gemini..."):
                client = get_client()
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(cut_sheet.getvalue())
                    tmp_path = tmp.name
                extracted = extract_json(client, tmp_path, PROFILE_PROMPT)
                os.unlink(tmp_path)
            extracted["address"] = address.strip()
            profile = extracted

        slug = storage.slugify(address)
        storage.save_profile(slug, profile)
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

    with st.expander("Property details (from MLS cut sheet)"):
        for field in ["days_on_market", "bedrooms", "bathrooms", "square_feet", "lot_size", "year_built", "mls_number"]:
            if profile.get(field):
                st.write(f"**{field.replace('_', ' ').title()}:** {profile[field]}")
        if profile.get("remarks"):
            st.write(profile["remarks"])

    history = storage.load_history(slug)
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
                if entry.get("hunch"):
                    st.caption(f"Agent's hunch: {entry['hunch']}")
                if entry.get("commentary"):
                    st.write(entry["commentary"])
                st.divider()

    st.subheader("Upload activity reports")
    st.caption("Add as many as you have for this property — MLS activity PDF, Zillow screenshot, etc.")
    uploaded_files = st.file_uploader(
        "Upload reports",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        client = None
        for f in uploaded_files:
            if f.name in st.session_state["processed_files"]:
                continue
            if client is None:
                client = get_client()
            with st.spinner(f"Reading {f.name} with Gemini..."):
                suffix = "." + f.name.split(".")[-1]
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(f.getvalue())
                    tmp_path = tmp.name
                try:
                    data = extract_json(client, tmp_path, ACTIVITY_PROMPT)
                    st.session_state["sources"].append({"source": f.name, "data": data})
                except Exception as e:
                    st.error(f"Couldn't read {f.name}: {e}")
                finally:
                    os.unlink(tmp_path)
            st.session_state["processed_files"].add(f.name)

    if not st.session_state["sources"]:
        st.info("Upload at least one report above to continue.")
        render_footer()
        return

    merged = merge_extractions(st.session_state["sources"])

    left, right = st.columns(2)

    with left, st.container(border=True):
        st.subheader("Report data (edit anything Gemini missed)")
        merged["list_price"] = st.number_input("List price", value=float(merged.get("list_price") or 0), step=1000.0)
        merged["original_list_price"] = st.number_input(
            "Original list price", value=float(merged.get("original_list_price") or 0), step=1000.0
        )
        merged["days_on_market"] = st.number_input(
            "Days on market", value=int(merged.get("days_on_market") or 0), step=1
        )
        merged["showings"]["total"] = st.number_input(
            "Showings (total)", value=int(merged["showings"].get("total") or 0), step=1
        )
        merged["showings"]["last_30_days"] = st.number_input(
            "Showings (last 30 days)", value=int(merged["showings"].get("last_30_days") or 0), step=1
        )

        if merged["traffic_by_source"]:
            st.caption("Online traffic by source (kept separate — different platforms count differently):")
            for entry in merged["traffic_by_source"]:
                st.caption(f"- {entry['source']}: {entry['views'] or 0} views, {entry['saves'] or 0} saves")

        feedback_text = st.text_area("Feedback themes (one per line)", "\n".join(merged["feedback_themes"]))
        merged["feedback_themes"] = [line.strip() for line in feedback_text.splitlines() if line.strip()]

        if merged["_conflicts"]:
            st.caption("Agent note — sources disagreed on these, pick the right value above:")
            for field, values in merged["_conflicts"].items():
                detail = ", ".join(f"{v['value']} ({v['source']})" for v in values)
                st.caption(f"- {field}: {detail}")

        if merged["notes_on_missing_or_unclear_data"]:
            st.caption("Gemini's notes on missing/unclear data:")
            for note in merged["notes_on_missing_or_unclear_data"]:
                st.caption(f"- {note}")

    with right, st.container(border=True):
        st.subheader("Momentum")
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

        st.subheader("What's your read on this listing?")
        st.session_state["hunch"] = st.text_area(
            "Your hunch (optional but preferred)",
            value=st.session_state["hunch"],
            placeholder="e.g. I think buyers are put off by the busy road",
        )
        if not st.session_state["hunch"].strip():
            st.caption("No hunch yet? Pick a fallback story instead:")
            st.session_state["fallback_story"] = st.radio(
                "Fallback story", list(FALLBACK_STORIES.keys()), label_visibility="collapsed"
            )
            st.caption(FALLBACK_STORIES[st.session_state["fallback_story"]])

        st.session_state["tone_preset"] = st.radio("Tone", list(TONE_PRESETS.keys()))
        st.session_state["tone_notes"] = st.text_input(
            "Extra tone notes (optional)",
            value=st.session_state["tone_notes"],
            placeholder="e.g. this seller is an engineer, keep it data-heavy",
        )

        if st.button("Generate commentary draft", type="primary"):
            effective_hunch = st.session_state["hunch"].strip() or FALLBACK_STORIES.get(
                st.session_state["fallback_story"], ""
            )
            with st.spinner("Writing draft with Gemini..."):
                client = get_client()
                st.session_state["commentary"] = generate_commentary(
                    client,
                    merged,
                    history,
                    effective_hunch,
                    st.session_state["tone_preset"],
                    st.session_state["tone_notes"],
                )

        if st.session_state["commentary"]:
            st.session_state["commentary"] = st.text_area(
                "Commentary draft (edit before sending)", value=st.session_state["commentary"], height=200
            )

        if st.button("Save this report to history"):
            snapshot = {
                "date": date.today().isoformat(),
                **{k: v for k, v in merged.items() if k != "_conflicts"},
                "hunch": st.session_state["hunch"].strip(),
                "tone_preset": st.session_state["tone_preset"],
                "commentary": st.session_state["commentary"],
            }
            storage.save_snapshot(slug, snapshot)
            st.success("Saved. Next report for this property will compare against this one.")

        st.download_button(
            "Download PDF report",
            data=build_pdf(profile, merged, st.session_state["commentary"]),
            file_name=f"{slug}-report-{date.today().isoformat()}.pdf",
            mime="application/pdf",
        )

    render_footer()


view = st.session_state["view"]
if view == "menu":
    render_menu()
elif view == "new_property":
    render_new_property()
elif view == "property":
    render_property()
