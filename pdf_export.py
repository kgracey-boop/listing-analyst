"""
Builds a branded PDF for the seller: key numbers, price history, market
comparison stats, and the same sample charts shown on the review screen,
plus the agent's (edited) commentary. Uses fpdf2's built-in fonts, not the
custom Archivo/Roboto webfonts used on the Streamlit page.
"""
import io
import re

import vl_convert as vlc
from fpdf import FPDF
from fpdf.fonts import FontFace

from branding import BRAND
from charts import price_band_chart, price_position_chart
from market_stats import (
    bucket_property_type,
    compute_absorption,
    absorption_by_property_type,
    data_scope_summary,
    dom_benchmark,
    match_price_band,
    median_comp_price_per_sqft,
    price_per_sqft,
    price_reductions,
    try_parse_date,
)

MIN_TOTAL_COMPS = 10
MIN_TRAILING_SALES = 6

PAGE_MARGIN = 10

MAX_COMP_ROWS = 8


def _build_listing_url(link_or_reference):
    """MLS# -> a search link on the agent's own site. Only meaningful for
    active listings -- pending/closed ones won't show up in an active search.
    (Same logic as app.py's build_listing_url, duplicated here to avoid a
    circular import between pdf_export.py and app.py.)"""
    if not link_or_reference:
        return None
    match = re.search(r"\d+", str(link_or_reference))
    if not match:
        return None
    return BRAND["search_url_template"].format(mls_number=match.group())


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _fmt_money(value) -> str:
    if value is None:
        return None
    return f"${value:,.0f}"


def _absorption_caption(stats: dict) -> str:
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


def _data_confidence_warning(row_count: int, stats: dict) -> str:
    if row_count == 0:
        return None
    if row_count < MIN_TOTAL_COMPS:
        return f"Only {row_count} comparable listings found - with this little data, the numbers below may not be reliable."
    if stats["months_of_supply"] is not None and stats["closed_count_trailing"] < MIN_TRAILING_SALES:
        return (
            f"Only {stats['closed_count_trailing']} sales in the trailing 12 months - "
            "the absorption rate may not be reliable with this few data points."
        )
    return None


class Report(FPDF):
    def __init__(self, navy, slate):
        super().__init__(unit="mm", format="Letter")
        self.navy = navy
        self.slate = slate
        self.set_auto_page_break(auto=True, margin=20)

    def section_title(self, text):
        self.ln(3)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*self.navy)
        self.cell(0, 8, text, ln=1)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(0, 0, 0)

    def body_line(self, text):
        self.set_font("Helvetica", "", 11)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    def caption_line(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.slate)
        self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def comp_table(self, headers, rows, col_widths, link_col=None):
        """A simple table of comp rows. If link_col is given, that column's
        cell becomes a clickable link using the row's last element (the link
        URL, not displayed as its own column)."""
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        mist = _hex_to_rgb(BRAND["mist"])
        headings_style = FontFace(emphasis="B", color=self.navy, fill_color=mist)
        with self.table(
            col_widths=col_widths, text_align="LEFT", width=190, line_height=5.5, headings_style=headings_style
        ) as table:
            header_row = table.row()
            for h in headers:
                header_row.cell(h)
            for row in rows:
                link = row[-1] if link_col is not None else None
                values = row[:-1] if link_col is not None else row
                table_row = table.row()
                for i, value in enumerate(values):
                    if link_col is not None and i == link_col:
                        table_row.cell(str(value), link=link)
                    else:
                        table_row.cell(str(value))
        self.set_font("Helvetica", "", 11)

    def add_chart(self, chart, max_width=190):
        """Renders an Altair chart to PNG and places it, page-breaking first
        if it wouldn't fit in the remaining space on the current page."""
        if chart is None:
            return
        png_bytes = vlc.vegalite_to_png(chart.to_json(), scale=2)
        img = io.BytesIO(png_bytes)

        from PIL import Image

        pil_img = Image.open(io.BytesIO(png_bytes))
        w_px, h_px = pil_img.size
        w = max_width
        h = w * (h_px / w_px)

        if self.get_y() + h > self.page_break_trigger:
            self.add_page()

        self.image(img, x=PAGE_MARGIN, w=w, h=h)
        self.ln(3)


def build_pdf(profile: dict, merged: dict, commentary: str, calc_comps: list = None) -> bytes:
    navy = _hex_to_rgb(BRAND["navy"])
    slate = _hex_to_rgb(BRAND["slate"])

    pdf = Report(navy, slate)
    pdf.add_page()

    pdf.set_fill_color(*navy)
    pdf.rect(0, 0, pdf.w, 30, style="F")
    pdf.set_fill_color(255, 255, 255)
    pdf.set_xy(10, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, profile.get("address") or "Listing Activity Report", ln=1)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"{BRAND['brokerage']} · prepared by {BRAND['agent_name']}", ln=1)

    pdf.set_xy(10, 38)
    pdf.set_text_color(*navy)

    # ---------------------------------------------------------- Key Numbers
    pdf.section_title("Key Numbers")
    stats_lines = [
        ("List price", _fmt_money(merged.get("list_price"))),
        ("Original list price", _fmt_money(merged.get("original_list_price"))),
        ("List date", merged.get("list_date")),
        ("Days on market", merged.get("days_on_market")),
        ("Square feet", f"{merged['square_feet']:,}" if merged.get("square_feet") else None),
        ("Showings (total)", merged.get("showings", {}).get("total")),
        ("Showings (last 30 days)", merged.get("showings", {}).get("last_30_days")),
    ]
    any_stats = False
    for label, value in stats_lines:
        if value:
            pdf.cell(0, 7, f"{label}: {value}", ln=1)
            any_stats = True
    if not any_stats:
        pdf.caption_line("No basic facts captured yet for this property.")

    # ------------------------------------------------- Price history section
    if merged.get("list_date") or merged.get("original_list_price") or merged.get("price_history"):
        pdf.section_title("Price History")
        if merged.get("list_date") or merged.get("original_list_price"):
            date_part = f"Listed {merged['list_date']}" if merged.get("list_date") else "Listed"
            price_part = f" at {_fmt_money(merged['original_list_price'])}" if merged.get("original_list_price") else ""
            pdf.body_line(f"{date_part}{price_part}.")

        reductions = price_reductions(merged.get("price_history") or [])
        if reductions["chronological"]:
            if reductions["count"]:
                pdf.body_line(
                    f"Reduced {reductions['count']} time{'s' if reductions['count'] != 1 else ''}, "
                    f"totaling {_fmt_money(reductions['total_amount'])}."
                )
            else:
                pdf.caption_line("No reductions - price has only gone up or stayed flat in the data we have.")

    # ------------------------------------------------- Market comparison
    if calc_comps:
        pdf.section_title("Market Comparison")
        row_count = len(calc_comps)
        stats = compute_absorption(calc_comps)

        pdf.body_line(f"Total comparable listings used: {row_count}")
        warning = _data_confidence_warning(row_count, stats)
        if warning:
            pdf.caption_line(warning)

        pdf.body_line(
            f"Active: {stats['active_count']}   Pending: {stats['pending_count']}   "
            f"Sold (trailing 12mo): {stats['closed_count_trailing']}"
        )
        if stats["months_of_supply"] is not None:
            pdf.body_line(f"Months of supply: {stats['months_of_supply']}")
            pdf.caption_line(_absorption_caption(stats))

        by_type = absorption_by_property_type(calc_comps)
        if len(by_type) > 1:
            subject_bucket = bucket_property_type(profile.get("property_type")) if profile.get("property_type") else None
            pdf.body_line("By property type:")
            for bucket, b_stats in sorted(by_type.items(), key=lambda kv: -kv[1]["active_count"] - kv[1]["closed_count_total"]):
                marker = " (your listing)" if subject_bucket and bucket == subject_bucket else ""
                if b_stats["months_of_supply"] is not None:
                    pdf.caption_line(
                        f"{bucket}{marker}: {b_stats['months_of_supply']} months of supply "
                        f"({b_stats['active_count']} active, ~{b_stats['monthly_pace']}/month sold)"
                    )
                else:
                    pdf.caption_line(f"{bucket}{marker}: {b_stats['active_count']} active, not enough sold data to calculate a rate")

        median_psf = median_comp_price_per_sqft(calc_comps)
        if median_psf:
            subject_psf = price_per_sqft(merged.get("list_price"), merged.get("square_feet"))
            you = _fmt_money(subject_psf) if subject_psf else "unknown"
            pdf.body_line(f"Price per sq ft: you're at {you}, comps median {_fmt_money(median_psf)}")

        dom_stats = dom_benchmark(calc_comps)
        if dom_stats["active_median_dom"] or dom_stats["pending_median_dom"]:
            if dom_stats["pending_median_dom"]:
                pdf.caption_line(
                    f"Comps that went pending typically did so by day {dom_stats['pending_median_dom']} - "
                    "a rough benchmark for when a listing 'should' go under contract, if it's going to."
                )
            if dom_stats["active_median_dom"]:
                pdf.caption_line(f"Comps still active have a median of {dom_stats['active_median_dom']} days on market so far.")
            subject_dom = merged.get("days_on_market")
            if subject_dom and dom_stats["pending_median_dom"]:
                diff = subject_dom - dom_stats["pending_median_dom"]
                if diff > 0:
                    pdf.caption_line(f"You're at {subject_dom} days - {diff} days past that benchmark.")
                else:
                    pdf.caption_line(f"You're at {subject_dom} days - still within that typical window.")

        scope = data_scope_summary(calc_comps)
        scope_parts = []
        if scope["geography"]:
            scope_parts.append(scope["geography"])
        if scope["property_types"]:
            scope_parts.append(", ".join(scope["property_types"]))
        if scope["price_range"]:
            scope_parts.append(f"{_fmt_money(scope['price_range'][0])} - {_fmt_money(scope['price_range'][1])} observed")
        if scope["sqft_range"]:
            scope_parts.append(f"{scope['sqft_range'][0]:,}-{scope['sqft_range'][1]:,} sqft observed")
        if scope_parts:
            pdf.ln(1)
            pdf.caption_line("Data scope: " + " · ".join(scope_parts))

        pdf.add_chart(price_position_chart(calc_comps, merged.get("list_price"), merged.get("days_on_market")))

        # ---------------------------------------- Active listings (with links)
        active_comps = [c for c in calc_comps if c.get("status") == "active" and c.get("list_price")]
        subject_price = merged.get("list_price")
        active_comps.sort(key=lambda c: abs(c["list_price"] - subject_price) if subject_price else 0)
        if active_comps:
            pdf.section_title("Active Listings You're Competing With")
            pdf.caption_line("Tap \"View\" to see that listing's current search result.")
            rows = []
            for c in active_comps[:MAX_COMP_ROWS]:
                psf = price_per_sqft(c.get("list_price"), c.get("square_feet"))
                url = _build_listing_url(c.get("link_or_reference"))
                rows.append([
                    c.get("address") or "Unknown address",
                    _fmt_money(c.get("list_price")) or "-",
                    c.get("days_on_market") if c.get("days_on_market") is not None else "-",
                    _fmt_money(psf) or "-",
                    "View" if url else "-",
                    url,
                ])
            pdf.comp_table(
                ["Address", "List Price", "DOM", "$/sqft", "Link"],
                rows,
                col_widths=(6, 3, 2, 2, 2),
                link_col=4,
            )
            if len(active_comps) > MAX_COMP_ROWS:
                pdf.caption_line(f"Showing the {MAX_COMP_ROWS} closest in price to yours, of {len(active_comps)} active comps total.")

        # ------------------------------------------------------ Closed comps
        closed_comps = [c for c in calc_comps if c.get("status") == "closed" and c.get("sold_price")]
        closed_comps.sort(key=lambda c: try_parse_date(c.get("close_date")) or try_parse_date("1900-01-01"), reverse=True)
        if closed_comps:
            pdf.section_title("Recently Closed Comps")
            rows = []
            for c in closed_comps[:MAX_COMP_ROWS]:
                psf = price_per_sqft(c.get("sold_price"), c.get("square_feet"))
                orig = _fmt_money(c.get("original_list_price")) or "-"
                sold = _fmt_money(c.get("sold_price")) or "-"
                rows.append([
                    c.get("address") or "Unknown address",
                    f"{orig} -> {sold}",
                    c.get("days_on_market") if c.get("days_on_market") is not None else "-",
                    _fmt_money(psf) or "-",
                ])
            pdf.comp_table(["Address", "Original -> Sold", "DOM", "$/sqft"], rows, col_widths=(6, 4, 2, 2))
            if len(closed_comps) > MAX_COMP_ROWS:
                pdf.caption_line(f"Showing the {MAX_COMP_ROWS} most recent closings, of {len(closed_comps)} closed comps total.")

    # ------------------------------------------------------------ Price bands
    if merged.get("price_bands"):
        pdf.section_title("Showings by Price Band")
        band = match_price_band(merged.get("list_price"), merged["price_bands"])
        pdf.add_chart(price_band_chart(merged["price_bands"], band))
        for b in merged["price_bands"]:
            marker = "  <- your listing" if band and b.get("band") == band else ""
            pdf.caption_line(f"{b['band']}: {b['showing_count']} showings{marker}")

    # ------------------------------------------------------------- Feedback
    if merged.get("feedback"):
        pdf.section_title("Buyer Feedback")
        rows = [[f.get("date") or "Date unknown", f.get("quote") or ""] for f in merged["feedback"]]
        pdf.comp_table(["Date", "Feedback"], rows, col_widths=(2, 8))

    # ---------------------------------------------------------- Online traffic
    if merged.get("traffic_by_source"):
        pdf.section_title("Online Traffic")
        for entry in merged["traffic_by_source"]:
            pdf.body_line(f"{entry['source']}: {entry['views'] or 0} views, {entry['saves'] or 0} saves")

    # ------------------------------------------------------- Agent commentary
    if commentary:
        pdf.section_title("Agent Commentary")
        pdf.body_line(commentary)

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*slate)
    pdf.cell(0, 10, f"{BRAND['agent_name']} · {BRAND['brokerage']}", align="C", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
