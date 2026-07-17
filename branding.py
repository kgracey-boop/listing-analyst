"""
Brand settings for the app. Kept in one place so a future version can
swap these per agent instead of hardcoding one owner.

Palette/fonts pulled from graceyrealestate.com (Kevin's own site): navy +
gold, Belleza for display headings, Work Sans for body text.
"""
import base64
import html as html_lib
import os

import streamlit as st

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _load_base64(filename):
    path = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# Loaded once at import time — the header logo swaps in for the plain
# "RootedReports" text lockup on brand-identity pages (the menu and the
# passcode gate), not on pages whose title is page-specific content
# (a property address, "Terms of Use") where the logo would compete with it.
LOGO_HEADER_B64 = _load_base64("logo-header.png")

BRAND = {
    "agent_name": "Kevin Gracey",
    "navy": "#002244",
    "gold": "#F4B400",
    "slate": "#444444",
    "mist": "#F9F9F9",
    # {mls_number} gets substituted in — swap this per agent's own site once
    # this app supports more than one agent.
    "search_url_template": "https://aprilaumanrealestate.com/search/#location_search_field={mls_number}",
}


def inject_css():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Belleza&family=Work+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Work Sans', sans-serif;
            color: {BRAND['slate']};
        }}
        h1, h2, h3 {{
            font-family: 'Belleza', sans-serif;
            color: {BRAND['navy']};
            font-weight: 400;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        .brand-header {{
            background-color: {BRAND['navy']};
            padding: 1.5rem 1.75rem;
            border-radius: 0;
            border-bottom: 3px solid {BRAND['gold']};
            margin-bottom: 1.5rem;
        }}
        .brand-header-logo {{
            height: 88px;
            display: block;
            margin-bottom: 0.5rem;
        }}
        .brand-header h1 {{
            color: white;
            margin: 0;
            font-size: 1.9rem;
            letter-spacing: 3px;
        }}
        .brand-header p {{
            color: {BRAND['mist']};
            margin: 0.4rem 0 0 0;
            font-size: 0.95rem;
            font-family: 'Work Sans', sans-serif;
            text-transform: none;
            letter-spacing: normal;
        }}
        .brand-card {{
            background-color: {BRAND['mist']};
            padding: 1.25rem;
            border-radius: 0;
            border-left: 3px solid {BRAND['navy']};
        }}
        .brand-footer {{
            color: {BRAND['slate']};
            font-size: 0.8rem;
            text-align: center;
            margin-top: 2.5rem;
            padding-top: 1rem;
            border-top: 1px solid #e0e0e0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* Buttons — sharp corners, uppercase, letter-spaced, matching the
        navy/gold CTA style on graceyrealestate.com */
        [data-testid^="stBaseButton"] {{
            border-radius: 0 !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
            font-family: 'Work Sans', sans-serif;
        }}
        /* Jump-to-report / delete buttons sit in fixed-width flex columns
        (see .st-key-properties-list rules below) — nowrap only on those,
        so a long property address in the growing first column can still
        wrap onto two lines instead of being squeezed by its neighbors. */
        .st-key-properties-list [data-testid="stColumn"]:not(:first-child) [data-testid^="stBaseButton"] {{
            white-space: nowrap;
        }}
        [data-testid="stBaseButton-secondary"] {{
            border: 2px solid {BRAND['navy']} !important;
            color: {BRAND['navy']} !important;
            background-color: white !important;
        }}
        [data-testid="stBaseButton-secondary"]:hover {{
            background-color: {BRAND['navy']} !important;
            color: white !important;
        }}
        [data-testid="stBaseButton-primary"] {{
            background-color: {BRAND['navy']} !important;
            color: {BRAND['gold']} !important;
            border: 2px solid {BRAND['navy']} !important;
        }}
        [data-testid="stBaseButton-primary"]:hover {{
            background-color: {BRAND['gold']} !important;
            color: {BRAND['navy']} !important;
            border-color: {BRAND['gold']} !important;
        }}

        .st-key-properties-list [data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            align-items: center !important;
        }}
        .st-key-properties-list [data-testid="stColumn"] {{
            width: auto !important;
            min-width: 0 !important;
        }}
        .st-key-properties-list [data-testid="stColumn"]:first-child {{
            flex: 1 1 auto !important;
            min-width: 0 !important;
        }}
        .st-key-properties-list [data-testid="stColumn"]:not(:first-child) {{
            flex: 0 0 auto !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(subtitle: str = "RootedReports", prepared_by: str = None):
    # Falls back to the fixed brand owner (BRAND['agent_name']) only if the
    # user hasn't set their own name yet — "prepared by" is meant to reflect
    # whoever is actually using the tool right now, distinct from who legally
    # owns the software (that's fixed, and lives in the Terms of Use text).
    # Callers who need the fixed owner unconditionally (e.g. the Terms page)
    # can pass prepared_by explicitly — that also suppresses brokerage/contact,
    # since those are this session's user-entered details, not the owner's.
    fixed_owner = prepared_by is not None
    name = html_lib.escape(prepared_by or st.session_state.get("preparer_name") or BRAND["agent_name"])
    brokerage = None if fixed_owner else st.session_state.get("preparer_brokerage")
    contact = None if fixed_owner else st.session_state.get("preparer_contact")

    subtitle_line = f"{html_lib.escape(brokerage)} &middot; prepared by {name}" if brokerage else f"Prepared by {name}"
    contact_html = f'<p class="brand-header-contact">{html_lib.escape(contact)}</p>' if contact else ""

    if subtitle == "RootedReports" and LOGO_HEADER_B64:
        title_html = f'<img class="brand-header-logo" src="data:image/png;base64,{LOGO_HEADER_B64}" alt="Rooted Reports">'
    else:
        title_html = f"<h1>{subtitle}</h1>"

    st.markdown(
        f"""
        <div class="brand-header">
            {title_html}
            <p>{subtitle_line}</p>
            {contact_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer():
    name = html_lib.escape(st.session_state.get("preparer_name") or BRAND["agent_name"])
    brokerage = st.session_state.get("preparer_brokerage")
    footer_line = f"{name} &middot; {html_lib.escape(brokerage)}" if brokerage else name
    st.markdown(
        f"""
        <div class="brand-footer">
            {footer_line}
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([3, 1, 3])
    with mid:
        current_view = st.session_state.get("view")
        if current_view != "terms" and st.button("Terms", key=f"terms-link-{current_view}", width="stretch"):
            # Parks where we came from rather than calling app.py's goto() —
            # a detour to read the Terms shouldn't reset in-progress work
            # (uploaded CSVs, extracted comps, etc.) the way navigating to a
            # different property or starting fresh should.
            st.session_state["terms_return"] = {
                "view": current_view,
                "slug": st.session_state.get("slug"),
                "stage": st.session_state.get("stage", "csv"),
            }
            st.session_state["view"] = "terms"
            st.rerun()
