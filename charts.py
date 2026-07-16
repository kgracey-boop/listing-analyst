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
own blue/navy since only two colors are needed. The status chart needs three
distinct categorical hues, which the brand palette doesn't supply — those
three (blue/aqua/yellow) are the skill's own validated categorical slots 1-3,
kept in their validated fixed order rather than reordered.
"""
import altair as alt
import pandas as pd

from branding import BRAND

NEUTRAL_GRAY = "#C3C2B7"

STATUS_ORDER = ["Active", "Pending", "Closed"]
STATUS_COLORS = {
    "Active": "#2a78d6",
    "Pending": "#1baf7a",
    "Closed": "#eda100",
}


def price_band_chart(price_bands: list, subject_band: str):
    """Emphasis bar chart: the subject's price band in brand blue, every
    other band in neutral gray. Returns None if there's nothing to plot."""
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
                scale=alt.Scale(domain=["Your listing", "Other bands"], range=[BRAND["blue"], NEUTRAL_GRAY]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[alt.Tooltip("band:N", title="Price band"), alt.Tooltip("showing_count:Q", title="Showings")],
        )
        .properties(height=280)
    )


def price_position_chart(comparable_listings: list, subject_price, subject_dom=None):
    """Scatter plot: price vs. days on market for active/pending/closed
    comps, colored by status. Returns None if there's nothing to plot."""
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
            color=BRAND["navy"], strokeDash=[4, 4], size=2
        ).encode(y="price:Q")
        layers.append(hline)

    if subject_dom is not None:
        vline = alt.Chart(pd.DataFrame({"days_on_market": [subject_dom]})).mark_rule(
            color=BRAND["navy"], strokeDash=[4, 4], size=2
        ).encode(x="days_on_market:Q")
        layers.append(vline)

    if subject_price and subject_dom is not None:
        marker_df = pd.DataFrame({"days_on_market": [subject_dom], "price": [subject_price], "label": ["Your listing"]})
        text = alt.Chart(marker_df).mark_text(color=BRAND["navy"], dy=-14, fontWeight="bold").encode(
            x="days_on_market:Q", y="price:Q", text="label:N"
        )
        layers.append(text)

    return alt.layer(*layers).properties(height=280)
