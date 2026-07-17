"""
Sample charts, built to match what April specifically praised in her own
report feedback:
  - Target Market Analysis: price band where showings concentrate, with the
    subject's own band highlighted (the source reports never do this
    highlighting themselves — we compute and draw it ourselves).
  - Pricing Benchmark: a visual showing where the subject is priced relative
    to active/pending/closed comps.

Color choices follow the dataviz skill's validated palette: the price-band
chart is "emphasis" form (one highlighted series + gray), using the brand's
own gold accent since only two colors are needed. The status chart needs
three distinct categorical hues, which the brand palette doesn't supply —
those three (blue/aqua/yellow) are the skill's own validated categorical
slots 1-3, kept in their validated fixed order rather than reordered.
"""
import altair as alt
import pandas as pd

NEUTRAL_GRAY = "#C3C2B7"

# The brand's UI gold (BRAND["gold"]) is tuned for text/buttons on a navy
# background, where it's high-contrast. As a filled bar on a white chart
# surface it validates far too washed-out (contrast 1.8, worse than a plain
# gray) — this deepened amber is the same brand family, calibrated instead
# for legibility as a chart mark (validated via the dataviz skill's script:
# contrast 2.99 vs the ~1.8 the literal brand gold gets).
CHART_GOLD = "#C98500"

STATUS_ORDER = ["Active", "Pending", "Closed"]
STATUS_COLORS = {
    "Active": "#2a78d6",
    "Pending": "#1baf7a",
    "Closed": "#eda100",
}

# The subject's own marker on the price-vs-DOM scatter — validated slot 5
# (violet) from the dataviz skill's categorical palette. Deliberately not
# reused from blue/aqua/yellow/gold already in play elsewhere on this chart:
# it's cool-toned against an otherwise warm palette, and carries no
# pre-existing good/bad connotation the way green or red might.
SUBJECT_COLOR = "#4a3aa7"

# The market-rate reference line (comps' median $/sqft, applied to the
# subject's own square footage) — validated slot 7 (magenta). A different
# color from SUBJECT_COLOR on purpose: these are two different concepts
# (where you're actually priced vs. where the market's typical $/sqft would
# put you) that can appear on the chart at the same time.
MARKET_RATE_COLOR = "#e87ba4"

# The closed-median DOM reference line — validated slot 8 (orange), the next
# unused categorical slot after blue/aqua/yellow (status dots), violet
# (subject), and magenta (market rate) are all already spoken for on this
# same chart. Orange carries no pre-existing good/bad connotation the way
# green or red would, which matters since a benchmark line isn't inherently
# good or bad news on its own.
DOM_BENCHMARK_COLOR = "#eb6834"


def price_band_chart(price_bands: list, subject_band: str):
    """Emphasis bar chart: the subject's price band in the brand's gold
    accent, every other band in neutral gray. Returns None if there's
    nothing to plot."""
    if not price_bands:
        return None

    df = pd.DataFrame(price_bands)
    df["highlight"] = df["band"].apply(lambda b: "Your listing" if b == subject_band else "Other bands")

    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("band:N", sort=None, title="Price band", axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("showing_count:Q", title="Showings"),
            color=alt.Color(
                "highlight:N",
                scale=alt.Scale(domain=["Your listing", "Other bands"], range=[CHART_GOLD, NEUTRAL_GRAY]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[alt.Tooltip("band:N", title="Price band"), alt.Tooltip("showing_count:Q", title="Showings")],
        )
        .properties(height=280)
    )


def price_position_chart(
    comparable_listings: list, subject_price, subject_dom=None, market_rate_price=None, closed_median_dom=None
):
    """Scatter plot: price vs. days on market for active/pending/closed
    comps, colored by status. Returns None if there's nothing to plot.
    market_rate_price (optional): comps' median $/sqft applied to the
    subject's own square footage — a horizontal reference line showing
    where the market's typical rate would price this listing, distinct
    from the subject's own actual list price.
    closed_median_dom (optional): median days-on-market among CLOSED comps
    only — a vertical reference line. Closed-only because a closed comp's
    DOM is a final, completed number; an active/pending comp's DOM is still
    climbing and would understate how long homes actually take to sell."""
    rows = []
    for c in comparable_listings:
        status = (c.get("status") or "").title()
        if status not in STATUS_ORDER:
            continue
        price = c.get("sold_price") if status == "Closed" else c.get("list_price")
        dom = c.get("days_on_market")
        if price and dom is not None:
            rows.append({"status": status, "price": price, "days_on_market": dom})

    if not rows:
        return None

    df = pd.DataFrame(rows)

    all_prices = df["price"].tolist() + ([subject_price] if subject_price else [])
    if market_rate_price:
        all_prices.append(market_rate_price)
    price_min, price_max = min(all_prices), max(all_prices)
    padding = max((price_max - price_min) * 0.1, 1)
    y_domain = [price_min - padding, price_max + padding]

    points = (
        alt.Chart(df)
        .mark_circle(size=90, opacity=0.75)
        .encode(
            x=alt.X("days_on_market:Q", title="Days on market"),
            y=alt.Y("price:Q", title="Price", scale=alt.Scale(domain=y_domain, nice=False), axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=STATUS_ORDER, range=[STATUS_COLORS[s] for s in STATUS_ORDER]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[
                alt.Tooltip("status:N", title="Status"),
                alt.Tooltip("price:Q", title="Price", format="$,.0f"),
                alt.Tooltip("days_on_market:Q", title="Days on market"),
            ],
        )
    )

    layers = [points]

    if subject_price:
        hline = alt.Chart(pd.DataFrame({"price": [subject_price]})).mark_rule(
            color=SUBJECT_COLOR, strokeDash=[4, 4], size=2
        ).encode(y="price:Q")
        layers.append(hline)

    if subject_dom is not None:
        vline = alt.Chart(pd.DataFrame({"days_on_market": [subject_dom]})).mark_rule(
            color=SUBJECT_COLOR, strokeDash=[4, 4], size=2
        ).encode(x="days_on_market:Q")
        layers.append(vline)

    if subject_price and subject_dom is not None:
        marker_df = pd.DataFrame({"days_on_market": [subject_dom], "price": [subject_price], "label": ["Your listing"]})
        text = alt.Chart(marker_df).mark_text(color=SUBJECT_COLOR, dy=-14, fontWeight="bold").encode(
            x="days_on_market:Q", y="price:Q", text="label:N"
        )
        layers.append(text)

    if market_rate_price:
        rate_df = pd.DataFrame({"price": [market_rate_price]})
        rate_line = alt.Chart(rate_df).mark_rule(color=MARKET_RATE_COLOR, strokeDash=[2, 2], size=2).encode(y="price:Q")
        layers.append(rate_line)

        rate_label_df = pd.DataFrame({"price": [market_rate_price], "label": ["Market $/sqft rate"]})
        rate_text = alt.Chart(rate_label_df).mark_text(
            color=MARKET_RATE_COLOR, dy=-8, align="left", fontWeight="bold"
        ).encode(y="price:Q", text="label:N")
        layers.append(rate_text)

    if closed_median_dom is not None:
        dom_line_df = pd.DataFrame({"days_on_market": [closed_median_dom]})
        dom_line = alt.Chart(dom_line_df).mark_rule(
            color=DOM_BENCHMARK_COLOR, strokeDash=[2, 2], size=2
        ).encode(x="days_on_market:Q")
        layers.append(dom_line)

        dom_label_df = pd.DataFrame({"days_on_market": [closed_median_dom], "label": ["Closed median"]})
        dom_text = alt.Chart(dom_label_df).mark_text(
            color=DOM_BENCHMARK_COLOR, dy=-8, align="left", fontWeight="bold", angle=270
        ).encode(x="days_on_market:Q", y=alt.value(10), text="label:N")
        layers.append(dom_text)

    return alt.layer(*layers).properties(height=280)


def absorption_chart(bucket_stats: list):
    """Bar chart: months of supply per property-type bucket (plus New
    Construction, if present) — one axis, one unit, genuinely comparable
    across bars even though New Construction's number is computed from a
    different qualifying date under the hood. bucket_stats is a list of
    {"label": str, "months_of_supply": float, "highlight": bool} —
    highlight marks the subject's own bucket in the brand's gold accent,
    the same emphasis treatment price_band_chart uses. Direct-labeled since
    there are only ever a handful of bars. Returns None if there's nothing
    to plot."""
    if not bucket_stats:
        return None

    df = pd.DataFrame(bucket_stats)
    df["color_key"] = df["highlight"].apply(lambda h: "Your property type" if h else "Other")

    bars = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("label:N", sort=None, title=None, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("months_of_supply:Q", title="Months of supply"),
            color=alt.Color(
                "color_key:N",
                scale=alt.Scale(domain=["Your property type", "Other"], range=[CHART_GOLD, NEUTRAL_GRAY]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Type"),
                alt.Tooltip("months_of_supply:Q", title="Months of supply"),
            ],
        )
    )

    labels = (
        alt.Chart(df)
        .mark_text(dy=-8, fontWeight="bold")
        .encode(x="label:N", y="months_of_supply:Q", text=alt.Text("months_of_supply:Q", format=".1f"))
    )

    return alt.layer(bars, labels).properties(height=280)


def weekly_contracts_chart(weekly_counts: list):
    """Bar chart: count of comps (already filtered to the subject's own
    property type) that went under contract each week, over roughly the
    last 2 years. Tooltip-only, no direct labels — with up to ~104 bars,
    labeling every one would be unreadable clutter rather than a helpful
    figure. Returns None if there's nothing to plot."""
    if not weekly_counts:
        return None

    df = pd.DataFrame(weekly_counts)

    return (
        alt.Chart(df)
        .mark_bar(color="#2a78d6")
        .encode(
            x=alt.X("week_start:T", title="Week"),
            y=alt.Y("count:Q", title="Contracts that week"),
            tooltip=[
                alt.Tooltip("week_start:T", title="Week of"),
                alt.Tooltip("count:Q", title="Contracts"),
            ],
        )
        .properties(height=280)
    )


def price_reduction_trend_chart(monthly_pcts: list):
    """Line chart: % of closed comps that had a price reduction before going
    under contract, one point per month, trailing 12 months. monthly_pcts
    comes from comp_price_reduction_stats()'s trend data, already gated
    there on MIN_MONTHS_WITH_DATA — an empty list means not enough history
    to trust a trend line yet. Returns None in that case."""
    if not monthly_pcts:
        return None

    df = pd.DataFrame(monthly_pcts)

    return (
        alt.Chart(df)
        .mark_line(color="#2a78d6", point=True, strokeWidth=2)
        .encode(
            x=alt.X("month:O", title="Month"),
            y=alt.Y("pct:Q", title="% price drop before contract", scale=alt.Scale(domainMin=0)),
            tooltip=[
                alt.Tooltip("month:O", title="Month"),
                alt.Tooltip("pct:Q", title="% price drop before contract"),
            ],
        )
        .properties(height=280)
    )
