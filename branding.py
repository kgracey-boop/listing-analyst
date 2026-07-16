"""
Brand settings for the app. Kept in one place so a future version can
swap these per agent instead of hardcoding one brokerage.

Palette/fonts pulled from graceyrealestate.com (Kevin's own site): navy +
gold, Belleza for display headings, Work Sans for body text.
"""
import streamlit as st

BRAND = {
    "agent_name": "Kevin Gracey",
    "brokerage": "Coldwell Banker Advantage",
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


def render_header(subtitle: str = "RootedReports"):
    st.markdown(
        f"""
        <div class="brand-header">
            <h1>{subtitle}</h1>
            <p>{BRAND['brokerage']} &middot; prepared by {BRAND['agent_name']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer():
    st.markdown(
        f"""
        <div class="brand-footer">
            {BRAND['agent_name']} &middot; {BRAND['brokerage']}
        </div>
        """,
        unsafe_allow_html=True,
    )
