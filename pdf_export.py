"""
Builds a simple branded one-pager PDF for the seller: key numbers plus the
agent's (edited) commentary. Uses fpdf2's built-in fonts, not the custom
Archivo/Roboto webfonts used on the Streamlit page.
"""
from fpdf import FPDF

from branding import BRAND


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def build_pdf(profile: dict, merged: dict, commentary: str) -> bytes:
    navy = _hex_to_rgb(BRAND["navy"])
    slate = _hex_to_rgb(BRAND["slate"])

    pdf = FPDF(unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_fill_color(*navy)
    pdf.rect(0, 0, pdf.w, 30, style="F")
    pdf.set_xy(10, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, profile.get("address") or "Listing Activity Report", ln=1)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"{BRAND['brokerage']} · prepared by {BRAND['agent_name']}", ln=1)

    pdf.set_xy(10, 38)
    pdf.set_text_color(*navy)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Key Numbers", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(0, 0, 0)

    stats = [
        ("List price", merged.get("list_price")),
        ("Original list price", merged.get("original_list_price")),
        ("Days on market", merged.get("days_on_market")),
        ("Showings (total)", merged.get("showings", {}).get("total")),
        ("Showings (last 30 days)", merged.get("showings", {}).get("last_30_days")),
    ]
    for label, value in stats:
        if value:
            pdf.cell(0, 7, f"{label}: {value}", ln=1)

    if merged.get("traffic_by_source"):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Online traffic", ln=1)
        pdf.set_font("Helvetica", "", 11)
        for entry in merged["traffic_by_source"]:
            pdf.cell(0, 6, f"{entry['source']}: {entry['views'] or 0} views, {entry['saves'] or 0} saves", ln=1)

    if commentary:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*navy)
        pdf.cell(0, 8, "Agent Commentary", ln=1)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, commentary)

    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*slate)
    pdf.cell(0, 10, f"{BRAND['agent_name']} · {BRAND['brokerage']}", align="C")

    return bytes(pdf.output())
