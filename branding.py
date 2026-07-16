"""
Brand settings for the app. Kept in one place so a future version can
swap these per agent instead of hardcoding one brokerage.
"""
import streamlit as st

BRAND = {
    "agent_name": "Kevin Gracey",
    "brokerage": "Coldwell Banker Advantage",
    "navy": "#012169",
    "blue": "#1F69FF",
    "slate": "#46587A",
    "mist": "#F3F6FB",
    # {mls_number} gets substituted in — swap this per agent's own site once
    # this app supports more than one agent.
    "search_url_template": "https://aprilaumanrealestate.com/search/#location_search_field={mls_number}",
}


def inject_css():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=Roboto:wght@400;500&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Roboto', sans-serif;
        }}
        h1, h2, h3 {{
            font-family: 'Archivo', sans-serif;
            color: {BRAND['navy']};
        }}
        .brand-header {{
            background-color: {BRAND['navy']};
            padding: 1.25rem 1.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1.5rem;
        }}
        .brand-header h1 {{
            color: white;
            margin: 0;
            font-size: 1.75rem;
        }}
        .brand-header p {{
            color: {BRAND['mist']};
            margin: 0.15rem 0 0 0;
            font-size: 0.95rem;
        }}
        .brand-card {{
            background-color: {BRAND['mist']};
            padding: 1.25rem;
            border-radius: 0.5rem;
        }}
        .brand-footer {{
            color: {BRAND['slate']};
            font-size: 0.8rem;
            text-align: center;
            margin-top: 2.5rem;
            padding-top: 1rem;
            border-top: 1px solid {BRAND['mist']};
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
        }}
        .st-key-properties-list [data-testid="stColumn"]:last-child {{
            flex: 0 0 auto !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(subtitle: str = "Listing Activity Report"):
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
