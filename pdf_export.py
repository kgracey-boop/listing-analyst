"""
Builds a branded PDF for the seller: key numbers, price history, market
comparison stats, and the same sample charts shown on the review screen,
plus the agent's (edited) commentary.

Rendered as real HTML/CSS through WeasyPrint rather than drawn with fpdf2's
manual coordinate API — the same brand fonts/palette as the rest of the app
(Belleza/Work Sans, navy/gold), and charts embedded as crisp inline SVG
instead of rasterized images. WeasyPrint needs Pango/Cairo installed at the
system level (see packages.txt for the Streamlit Cloud apt packages) —
that's the one tradeoff for the richer visual result.
"""
import html as html_lib

import vl_convert as vlc
from weasyprint import HTML as WeasyHTML

from branding import BRAND, LOGO_HEADER_B64
from charts import (
    absorption_chart,
    price_band_chart,
    price_position_chart,
    price_reduction_trend_chart,
    weekly_contracts_chart,
)
from comps_store import also_saved_comps, also_viewed_comps
from market_stats import (
    MIN_MONTHS_WITH_DATA,
    bucket_property_type,
    compute_absorption,
    compute_new_construction_absorption,
    absorption_by_property_type,
    comp_price_reduction_stats,
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
    try_parse_date,
    weekly_contracts,
)

MIN_TOTAL_COMPS = 10
MIN_TRAILING_SALES = 6
MAX_COMP_ROWS = 8


def _esc(value) -> str:
    """HTML-escapes any dynamic value before it goes into the template —
    most of this data comes from Gemini extraction or agent-typed text
    (feedback quotes, commentary, addresses), never assume it's safe to
    drop straight into markup."""
    if value is None:
        return ""
    return html_lib.escape(str(value))


def _css_str_esc(value) -> str:
    """Escapes a value for use inside a CSS string literal (the @page
    footer's `content: "..."`) — backslash and double-quote only, since
    HTML-escaping would be the wrong kind of escaping here."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _build_listing_url(link_or_reference):
    """MLS# -> a search link on the agent's own site. Confirmed 2026-07-23:
    resolves for active and pending listings, but not closed ones -- the
    public IDX site doesn't index sold data, only agent-side MLS access
    does, so don't build this link for closed comps."""
    import re

    if not link_or_reference:
        return None
    match = re.search(r"\d+", str(link_or_reference))
    if not match:
        return None
    return BRAND["search_url_template"].format(mls_number=match.group())


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
        return f"Only {row_count} comparable listings found — with this little data, the numbers below may not be reliable."
    if stats["months_of_supply"] is not None and stats["closed_count_trailing"] < MIN_TRAILING_SALES:
        return (
            f"Only {stats['closed_count_trailing']} sales in the trailing 12 months — "
            "the absorption rate may not be reliable with this few data points."
        )
    return None


def _chart_svg(chart) -> str:
    """Renders an Altair chart to inline SVG — crisper than a rasterized
    PNG and no image-sizing math needed, since it flows in the page like
    any other block element. Returns an empty string if there's no chart
    to plot (the caller can safely concatenate this into a template)."""
    if chart is None:
        return ""
    svg = vlc.vegalite_to_svg(chart.to_json())
    return f'<div class="chart">{svg}</div>'


def _section(title: str, body_html: str, page_break_before: bool = False) -> str:
    if not body_html:
        return ""
    classes = "section page-break" if page_break_before else "section"
    return f'<section class="{classes}"><h2>{_esc(title)}</h2>{body_html}</section>'


def _section_enabled(section_toggles, key) -> bool:
    """section_toggles is None (no toggles passed — e.g. older callers)
    means everything's on; otherwise missing keys also default to on, so a
    newly added section doesn't silently vanish for an agent whose choices
    predate it."""
    return section_toggles is None or section_toggles.get(key, True)


def _chart_row(*column_htmls) -> str:
    """Lays out 1+ pre-rendered columns (each already a label + chart,
    etc.) side by side, for a shorter/cleaner PDF than stacking every
    chart full-width. Falls back to full width for a lone column instead
    of stretching one chart across a half-width slot when its sibling
    didn't compute (too little data, e.g.)."""
    columns = [html for html in column_htmls if html]
    if not columns:
        return ""
    if len(columns) == 1:
        return columns[0]
    cols_html = "".join(f'<div class="chart-col">{html}</div>' for html in columns)
    return f'<div class="chart-row">{cols_html}</div>'


def _table(headers, rows, link_col=None, highlight_cols=None) -> str:
    """rows: list of lists of already-escaped cell HTML strings. link_col
    (if given) is the index whose cell is wrapped in an <a> using the row's
    last element as the href. highlight_cols (if given) is a set of column
    indices to visually call out, e.g. the dates that justify a sort order
    the reader might not otherwise notice."""
    highlight_cols = highlight_cols or set()
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        url = row[-1] if link_col is not None else None
        values = row[:-1] if link_col is not None else row
        cells = []
        for i, value in enumerate(values):
            if link_col is not None and i == link_col and url:
                cells.append(f'<td><a href="{_esc(url)}">{_esc(value)}</a></td>')
            elif i in highlight_cols:
                cells.append(f'<td class="highlight-cell">{_esc(value)}</td>')
            else:
                cells.append(f"<td>{_esc(value)}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="comp-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'


def _viewer_overlap_section(comps, since_field, title) -> str:
    if not comps:
        return ""
    rows = []
    for c in comps[:MAX_COMP_ROWS]:
        price = c.get("sold_price") if c.get("status") == "closed" else c.get("list_price")
        url = _build_listing_url(c.get("link_or_reference")) if c.get("status") == "active" else None
        rows.append([
            c.get("address") or "Unknown address",
            (c.get("status") or "-").title(),
            _fmt_money(price) or "-",
            c.get(since_field) or "-",
            "View" if url else "-",
            url,
        ])
    body = _table(["Address", "Status", "Price", "First Flagged", "Link"], rows, link_col=4)
    if len(comps) > MAX_COMP_ROWS:
        body += f'<p class="caption">Showing the {MAX_COMP_ROWS} most recently flagged, of {len(comps)} total.</p>'
    return _section(title, body)


CSS_TEMPLATE = """
@import url('https://fonts.googleapis.com/css2?family=Belleza&family=Work+Sans:wght@400;500;600;700&display=swap');

@page {{
    size: Letter;
    margin: 14mm 12mm 16mm 12mm;
    @bottom-center {{
        content: "{footer_text}  |  Page " counter(page);
        font-family: 'Work Sans', sans-serif;
        font-size: 8.5pt;
        color: {slate};
    }}
}}

* {{ box-sizing: border-box; }}

body {{
    font-family: 'Work Sans', sans-serif;
    color: #1a1a1a;
    font-size: 10.5pt;
    line-height: 1.45;
}}

.hero {{
    background: {navy};
    color: white;
    margin: -14mm -12mm 6mm -12mm;
    padding: 10mm 12mm 6mm 12mm;
    border-bottom: 3px solid {gold};
    position: relative;
}}
.hero-text {{
    max-width: 140mm;
}}
.hero-logo {{
    position: absolute;
    top: 8mm;
    right: 12mm;
    width: 20mm;
    height: auto;
}}
.hero h1 {{
    font-family: 'Belleza', sans-serif;
    font-weight: 400;
    font-size: 20pt;
    letter-spacing: 1px;
    margin: 0 0 2mm 0;
}}
.hero p {{
    margin: 0;
    font-size: 10.5pt;
    color: {mist};
}}

h2 {{
    font-family: 'Belleza', sans-serif;
    font-weight: 400;
    color: {navy};
    font-size: 14pt;
    letter-spacing: 0.5px;
    margin: 0 0 3mm 0;
    break-after: avoid;
}}

.section {{
    margin-bottom: 7mm;
}}
.section.page-break {{
    break-before: page;
    page-break-before: always;
}}

.stat-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 3mm;
    margin-bottom: 2mm;
}}
.stat-tile {{
    background: {mist};
    border-radius: 3px;
    padding: 3mm 4mm;
    min-width: 38mm;
    flex: 1 1 auto;
}}
.stat-tile .label {{
    font-size: 8.5pt;
    color: {slate};
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 1mm;
}}
.stat-tile .value {{
    font-size: 13pt;
    font-weight: 600;
    color: {navy};
}}

p.body-line {{ margin: 0 0 2mm 0; }}
p.caption {{ margin: 0 0 1.5mm 0; font-size: 9pt; color: {slate}; }}

.chart {{ margin: 2mm 0 4mm 0; break-inside: avoid; }}
.chart svg {{ width: 100%; height: auto; display: block; }}

.chart-row {{ display: flex; gap: 5mm; align-items: flex-start; break-inside: avoid; }}
.chart-row .chart-col {{ flex: 1 1 0; min-width: 0; }}

table.comp-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
    margin-bottom: 2mm;
}}
table.comp-table th {{
    background: {mist};
    color: {navy};
    text-align: left;
    font-weight: 600;
    padding: 1.8mm 2.5mm;
    border-bottom: 1px solid #ddd;
}}
table.comp-table td {{
    padding: 1.6mm 2.5mm;
    border-bottom: 1px solid #eee;
}}
table.comp-table a {{ color: {navy}; text-decoration: underline; }}
table.comp-table td.highlight-cell {{
    background: rgba(244, 180, 0, 0.2);
    font-weight: 600;
    color: {navy};
}}
"""


def build_pdf(
    profile: dict,
    merged: dict,
    commentary: str,
    calc_comps: list = None,
    solds_window_months: int = 3,
    known_feedback: list = None,
    prepared_by: str = None,
    brokerage: str = None,
    contact: str = None,
    comps_scope: str = "all",
    section_toggles: dict = None,
) -> bytes:
    title_text = profile.get("address") or "RootedReports"
    # "Prepared by"/brokerage/contact reflect whoever's actually using the
    # tool for this report, distinct from who owns the software (that's
    # fixed to BRAND['agent_name'], and lives in the Terms of Use, not here).
    prepared_by = prepared_by or BRAND["agent_name"]
    footer_text = f"{prepared_by} · {brokerage}" if brokerage else prepared_by

    css = CSS_TEMPLATE.format(
        navy=BRAND["navy"], gold=BRAND["gold"], slate=BRAND["slate"], mist=BRAND["mist"],
        footer_text=_css_str_esc(footer_text),
    )

    sections = []

    # ---------------------------------------------------------- Key Numbers
    stats_lines = [
        ("List price", _fmt_money(merged.get("list_price"))),
        ("Original list price", _fmt_money(merged.get("original_list_price"))),
        ("List date", merged.get("list_date")),
        ("Days on market", merged.get("days_on_market")),
        ("Square feet", f"{merged['square_feet']:,}" if merged.get("square_feet") else None),
        ("Showings (total)", merged.get("showings", {}).get("total")),
        ("Showings (last 30 days)", merged.get("showings", {}).get("last_30_days")),
    ]
    tiles = "".join(
        f'<div class="stat-tile"><div class="label">{_esc(label)}</div><div class="value">{_esc(value)}</div></div>'
        for label, value in stats_lines if value
    )
    key_numbers_body = f'<div class="stat-grid">{tiles}</div>' if tiles else '<p class="caption">No basic facts captured yet for this property.</p>'
    sections.append(_section("Key Numbers", key_numbers_body))

    # ------------------------------------------------- Price history section
    if _section_enabled(section_toggles, "price_history") and (
        merged.get("list_date") or merged.get("original_list_price") or merged.get("price_history") or calc_comps
    ):
        parts = []
        if merged.get("list_date") or merged.get("original_list_price"):
            date_part = f"Listed {merged['list_date']}" if merged.get("list_date") else "Listed"
            price_part = f" at {_fmt_money(merged['original_list_price'])}" if merged.get("original_list_price") else ""
            parts.append(f'<p class="body-line">{_esc(date_part + price_part)}.</p>')

        reductions = price_reductions(merged.get("price_history") or [])
        if reductions["chronological"]:
            if reductions["count"]:
                parts.append(
                    f'<p class="body-line">Reduced {reductions["count"]} '
                    f'time{"s" if reductions["count"] != 1 else ""}, totaling {_esc(_fmt_money(reductions["total_amount"]))}.</p>'
                )
            else:
                parts.append('<p class="caption">No reductions — price has only gone up or stayed flat in the data we have.</p>')

        if calc_comps:
            comp_stats = comp_price_reduction_stats(calc_comps)
            pending_stats, closed_stats, trend = comp_stats["pending"], comp_stats["closed"], comp_stats["trend"]

            if pending_stats["pct"] is not None:
                parts.append(
                    f'<p class="caption">Pending comps: {pending_stats["reduced"]} of {pending_stats["known"]} had a price drop '
                    f'before going pending (~{pending_stats["pct"]}%).</p>'
                )
            elif pending_stats["known"]:
                parts.append(f'<p class="caption">Pending comps: only {pending_stats["known"]} with known pricing — too few to trust a percentage.</p>')

            if closed_stats["pct"] is not None:
                parts.append(
                    f'<p class="caption">Closed comps: {closed_stats["reduced"]} of {closed_stats["known"]} had a price drop '
                    f'before selling (~{closed_stats["pct"]}%).</p>'
                )
            elif closed_stats["known"]:
                parts.append(f'<p class="caption">Closed comps: only {closed_stats["known"]} with known pricing — too few to trust a percentage.</p>')

            if trend["enough_data"]:
                parts.append(
                    f'<p class="caption">Price-drop rate among closed comps looks {trend["direction"]} over the last year '
                    f'(~{trend["earlier_pct"]}% earlier vs ~{trend["recent_pct"]}% more recently).</p>'
                )
                parts.append(_chart_svg(price_reduction_trend_chart(trend["monthly_pcts"])))
            else:
                parts.append(
                    f'<p class="caption">Not enough data yet to tell whether price drops are trending over the last year '
                    f'(usable data for {trend["months_with_data"]} of the last 12 months, need at least {MIN_MONTHS_WITH_DATA}).</p>'
                )

        sections.append(_section("Price History", "".join(parts), page_break_before=True))

    # ------------------------------------------------- Market comparison
    if calc_comps:
        parts = []
        row_count = len(calc_comps)
        stats = compute_absorption(calc_comps)

        parts.append(f'<p class="body-line">Total comparable listings used: {row_count}</p>')
        warning = _data_confidence_warning(row_count, stats)
        if warning:
            parts.append(f'<p class="caption">{_esc(warning)}</p>')

        parts.append(
            f'<p class="body-line">Active: {stats["active_count"]}   Pending: {stats["pending_count"]}   '
            f'Sold (trailing 12mo): {stats["closed_count_trailing"]}</p>'
        )
        if stats["months_of_supply"] is not None:
            parts.append(f'<p class="body-line">Months of supply: {stats["months_of_supply"]}</p>')
            parts.append(f'<p class="caption">{_esc(_absorption_caption(stats))}</p>')

        by_type = absorption_by_property_type(calc_comps)
        nc_stats = compute_new_construction_absorption(calc_comps)
        subject_bucket = bucket_property_type(profile.get("property_type")) if profile.get("property_type") else None

        bars, skipped = [], []
        for bucket, b_stats in sorted(by_type.items(), key=lambda kv: -kv[1]["active_count"] - kv[1]["closed_count_total"]):
            if b_stats["months_of_supply"] is not None:
                bars.append({"label": bucket, "months_of_supply": b_stats["months_of_supply"], "highlight": bucket == subject_bucket})
            else:
                skipped.append(bucket)

        has_new_construction = nc_stats["months_of_supply"] is not None
        if has_new_construction:
            postal_codes = sorted({c["postal_code"] for c in calc_comps if c.get("postal_code")})
            nc_label = f"New Construction in {postal_codes[0]}" if len(postal_codes) == 1 else "New Construction"
            bars.append({"label": nc_label, "months_of_supply": nc_stats["months_of_supply"], "highlight": False})

        by_type_col = ""
        if len(bars) > 1:
            by_type_col = '<p class="body-line">By property type:</p>' + _chart_svg(absorption_chart(bars))

        zip_compare = subdivision_vs_zip_absorption(calc_comps, profile.get("subdivision"), profile.get("property_type"))
        zip_col = ""
        if zip_compare is not None:
            sub_stats, zip_stats = zip_compare["subdivision"], zip_compare["rest_of_zip"]
            zip_bars = []
            if sub_stats["months_of_supply"] is not None:
                zip_bars.append({"label": profile["subdivision"], "months_of_supply": sub_stats["months_of_supply"], "highlight": True})
            if zip_stats["months_of_supply"] is not None:
                postal_codes = sorted({c["postal_code"] for c in calc_comps if c.get("postal_code")})
                zip_label = f"Rest of {postal_codes[0]}" if len(postal_codes) == 1 else "Rest of ZIP"
                zip_bars.append({"label": zip_label, "months_of_supply": zip_stats["months_of_supply"], "highlight": False})

            if len(zip_bars) == 2:
                zip_col = f'<p class="body-line">{_esc(profile["subdivision"])} vs. the rest of the zip:</p>' + _chart_svg(absorption_chart(zip_bars))

        # Side by side when both computed — same chart type (months-of-supply
        # bars), just different breakdowns, so pairing them reads as one
        # comparison instead of two stacked, near-identical-looking charts.
        parts.append(_chart_row(by_type_col, zip_col))

        if len(bars) > 1:
            if has_new_construction:
                parts.append(
                    '<p class="caption">New Construction reflects time from listing to going under contract, not closing — '
                    'this accounts for build/completion time that doesn\'t apply to resale homes.</p>'
                )
                nc_days = median_list_to_contract_days(calc_comps, new_construction=True)
                resale_days = median_list_to_contract_days(calc_comps, new_construction=False)
                if nc_days is not None:
                    parts.append(f'<p class="caption">New Construction: {nc_days:.0f} days from list to contract</p>')
                if resale_days is not None:
                    parts.append(f'<p class="caption">Resale: {resale_days:.0f} days from list to contract</p>')

            if skipped:
                parts.append(f'<p class="caption">Not enough sold data yet to calculate a rate for: {_esc(", ".join(skipped))}.</p>')

        if profile.get("property_type"):
            weekly = weekly_contracts(calc_comps, profile["property_type"])
            if any(w["count"] for w in weekly):
                bucket_label = bucket_property_type(profile["property_type"])
                parts.append(f'<p class="body-line">Weekly contracts — {_esc(bucket_label)} (last ~2 years):</p>')
                parts.append(_chart_svg(weekly_contracts_chart(weekly)))

        median_psf = median_comp_price_per_sqft(calc_comps)
        if median_psf:
            subject_psf = price_per_sqft(merged.get("list_price"), merged.get("square_feet"))
            you = _fmt_money(subject_psf) if subject_psf else "unknown"
            parts.append(f'<p class="body-line">Price per sq ft: you\'re at {_esc(you)}, comps median {_esc(_fmt_money(median_psf))}</p>')

        dom_stats = dom_benchmark(calc_comps)
        if dom_stats["active_median_dom"] or dom_stats["pending_median_dom"]:
            if dom_stats["pending_median_dom"]:
                parts.append(
                    f'<p class="caption">Comps that went pending typically did so by day {dom_stats["pending_median_dom"]} — '
                    'a rough benchmark for when a listing \'should\' go under contract, if it\'s going to.</p>'
                )
            if dom_stats["active_median_dom"]:
                parts.append(f'<p class="caption">Comps still active have a median of {dom_stats["active_median_dom"]} days on market so far.</p>')
            subject_dom = merged.get("days_on_market")
            if subject_dom and dom_stats["pending_median_dom"]:
                diff = subject_dom - dom_stats["pending_median_dom"]
                if diff > 0:
                    parts.append(f'<p class="caption">You\'re at {subject_dom} days — {diff} days past that benchmark.</p>')
                else:
                    parts.append(f'<p class="caption">You\'re at {subject_dom} days — still within that typical window.</p>')

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
            parts.append(f'<p class="caption">Data scope: {_esc(" · ".join(scope_parts))}</p>')

        scoped_comps = filter_by_subdivision(calc_comps, profile.get("subdivision")) if comps_scope == "subdivision" else calc_comps
        chart_comps = filter_recent_closed(scoped_comps, months=solds_window_months)
        market_rate_price = median_psf * merged["square_feet"] if median_psf and merged.get("square_feet") else None
        closed_median_dom = median_comp_days_on_market([c for c in chart_comps if c.get("status") == "closed"])
        parts.append(_chart_svg(price_position_chart(
            chart_comps, merged.get("list_price"), merged.get("days_on_market"),
            market_rate_price, closed_median_dom,
        )))

        if _section_enabled(section_toggles, "market_comparison"):
            sections.append(_section("Market Comparison", "".join(parts)))

        # ---------------------------------------- Active listings (with links)
        active_comps = [c for c in calc_comps if c.get("status") == "active" and c.get("list_price")]
        subject_price = merged.get("list_price")
        active_comps.sort(key=lambda c: abs(c["list_price"] - subject_price) if subject_price else 0)
        if active_comps and _section_enabled(section_toggles, "active_listings"):
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
            body = '<p class="caption">Tap "View" to see that listing\'s current search result.</p>'
            body += _table(["Address", "List Price", "DOM", "$/sqft", "Link"], rows, link_col=4)
            if len(active_comps) > MAX_COMP_ROWS:
                body += f'<p class="caption">Showing the {MAX_COMP_ROWS} closest in price to yours, of {len(active_comps)} active comps total.</p>'
            sections.append(_section("Active Listings You're Competing With", body))

        # --------------------------------------- Pending listings (with links)
        # Sorted by expected closing date, soonest first — not price
        # proximity like Active — since the point of this table is watching
        # what's about to close ahead of you. Comps with no stated closing
        # date sort to the end rather than falsely reading as "soonest."
        pending_comps = [c for c in calc_comps if c.get("status") == "pending" and c.get("list_price")]
        pending_comps.sort(key=lambda c: try_parse_date(c.get("close_date")) or try_parse_date("9999-12-31"))
        if pending_comps and _section_enabled(section_toggles, "pending_listings"):
            rows = []
            for c in pending_comps[:MAX_COMP_ROWS]:
                psf = price_per_sqft(c.get("list_price"), c.get("square_feet"))
                url = _build_listing_url(c.get("link_or_reference"))
                rows.append([
                    c.get("address") or "Unknown address",
                    _fmt_money(c.get("list_price")) or "-",
                    c.get("days_on_market") if c.get("days_on_market") is not None else "-",
                    _fmt_money(psf) or "-",
                    c.get("contract_date") or "-",
                    c.get("close_date") or "-",
                    "View" if url else "-",
                    url,
                ])
            body = '<p class="caption">Sorted by expected closing date, soonest first. Tap "View" to see that listing\'s current search result.</p>'
            body += _table(
                ["Address", "List Price", "DOM", "$/sqft", "Contract Date", "Expected Close", "Link"],
                rows, link_col=6, highlight_cols={4, 5},
            )
            if len(pending_comps) > MAX_COMP_ROWS:
                body += f'<p class="caption">Showing the {MAX_COMP_ROWS} soonest to close, of {len(pending_comps)} pending comps total.</p>'
            sections.append(_section("Pending Listings About to Close", body))

        # ------------------------------------------------------ Closed comps
        closed_comps = [c for c in calc_comps if c.get("status") == "closed" and c.get("sold_price")]
        closed_comps.sort(key=lambda c: try_parse_date(c.get("close_date")) or try_parse_date("1900-01-01"), reverse=True)
        if closed_comps and _section_enabled(section_toggles, "closed_comps"):
            shown_closed = closed_comps[:MAX_COMP_ROWS]
            rows = []
            for c in shown_closed:
                psf = price_per_sqft(c.get("sold_price"), c.get("square_feet"))
                orig = _fmt_money(c.get("original_list_price")) or "-"
                sold = _fmt_money(c.get("sold_price")) or "-"
                rows.append([
                    c.get("address") or "Unknown address",
                    f"{orig} → {sold}",
                    c.get("days_on_market") if c.get("days_on_market") is not None else "-",
                    _fmt_money(psf) or "-",
                    _fmt_money(c.get("concessions_amount")) or "(no info)",
                ])
            body = _table(["Address", "Original → Sold", "DOM", "$/sqft", "Concessions"], rows)
            if len(closed_comps) > MAX_COMP_ROWS:
                body += f'<p class="caption">Showing the {MAX_COMP_ROWS} most recent closings, of {len(closed_comps)} closed comps total.</p>'
            # Comments as a caption list rather than a table column — free
            # text varies too much in length to sit next to four tight
            # numeric columns without overflowing or squeezing the rest
            # unreadable, so only listing rows that actually have one.
            commented = [c for c in shown_closed if c.get("concessions_comments")]
            if commented:
                body += '<p class="caption">Concessions notes:</p>'
                for c in commented:
                    address = c.get("address") or "Unknown address"
                    body += f'<p class="caption">- {_esc(address)}: {_esc(c["concessions_comments"])}</p>'
            sections.append(_section("Recently Closed Comps", body))

        # -------------------------------------------------- Viewer overlap
        if _section_enabled(section_toggles, "viewer_overlap"):
            sections.append(_viewer_overlap_section(also_viewed_comps(calc_comps), "also_viewed_since", "People Who Viewed Your Listing Also Viewed"))
            sections.append(_viewer_overlap_section(also_saved_comps(calc_comps), "also_saved_since", "People Who Saved Your Listing Also Saved"))

    # ------------------------------------------------------------ Price bands
    if merged.get("price_bands") and _section_enabled(section_toggles, "price_bands"):
        band = match_price_band(merged.get("list_price"), merged["price_bands"])
        sections.append(_section("Showings by Price Band", _chart_svg(price_band_chart(merged["price_bands"], band))))

    # ------------------------------------------------------------- Feedback
    feedback_entries = known_feedback if known_feedback is not None else (merged.get("feedback") or [])
    if feedback_entries and _section_enabled(section_toggles, "feedback"):
        rows = [[f.get("date") or "Date unknown", f.get("quote") or ""] for f in feedback_entries]
        sections.append(_section("Buyer Feedback", _table(["Date", "Feedback"], rows)))

    # ---------------------------------------------------------- Online traffic
    if merged.get("traffic_by_source") and _section_enabled(section_toggles, "online_traffic"):
        lines = "".join(
            f'<p class="body-line">{_esc(entry["source"])}: {entry["views"] or 0} views, {entry["saves"] or 0} saves</p>'
            for entry in merged["traffic_by_source"]
        )
        sections.append(_section("Online Traffic", lines))

    # ------------------------------------------------------- Agent commentary
    if commentary:
        sections.append(_section("Agent Commentary", f'<p class="body-line">{_esc(commentary)}</p>'))

    subtitle_line = f"{_esc(brokerage)} · prepared by {_esc(prepared_by)}" if brokerage else f"Prepared by {_esc(prepared_by)}"
    contact_html = f'<p class="hero-contact">{_esc(contact)}</p>' if contact else ""

    logo_html = f'<img class="hero-logo" src="data:image/png;base64,{LOGO_HEADER_B64}" alt="Rooted Reports">' if LOGO_HEADER_B64 else ""

    body_html = "".join(sections)
    full_html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><style>{css}</style></head>
<body>
<div class="hero">
    <div class="hero-text">
        <h1>{_esc(title_text)}</h1>
        <p>{subtitle_line}</p>
        {contact_html}
    </div>
    {logo_html}
</div>
{body_html}
</body>
</html>"""

    return WeasyHTML(string=full_html).write_pdf()
