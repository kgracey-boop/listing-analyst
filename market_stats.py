"""
Derived market math — absorption rate, price/sqft, price-band matching.
Deliberately plain arithmetic, not Gemini output: these numbers should never
vary between runs or risk an LLM's arithmetic mistake.
"""
from datetime import datetime, timedelta

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y")

# Buckets for grouping — different property types can move at very different
# paces in the same area/timeframe (e.g. townhomes vs. single family), so
# absorption rate should be computed per bucket, not blended across all of them.
# Normalization happens here, at grouping time, not at ingestion — that's what
# lets a CSV's "Single Family Residence" and a Gemini-extracted PDF's "Single
# Family" land in the same bucket instead of silently splitting in two because
# the raw source strings differ.
PROPERTY_TYPE_BUCKETS = {
    "single family": "Single Family",
    "detached": "Single Family",
    "townhouse": "Townhome",
    "townhome": "Townhome",
    "attached": "Townhome",
    "condo": "Condo",
    "condominium": "Condo",
}


def bucket_property_type(value):
    if not value:
        return "Other/Unknown"
    v = value.strip().lower()
    for key, bucket in PROPERTY_TYPE_BUCKETS.items():
        if key in v:
            return bucket
    return "Other/Unknown"


def price_per_sqft(price, sqft):
    if not price or not sqft:
        return None
    return round(price / sqft)


def try_parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


TRAILING_DAYS = 365
STANDARD_DIVISOR_MONTHS = 12


def compute_absorption(comparable_listings: list, as_of=None) -> dict:
    """
    Industry-standard months of supply = current active listings ÷ average
    monthly sold pace, where the pace is a trailing-12-month average (NAR/
    appraisal convention) — not a single short window — because real estate
    sales are seasonal and lumpy; a 30-day slice is too noisy to trust.

    Expired and withdrawn listings are tracked but excluded from the
    calculation entirely — they're neither current inventory nor completed
    sales. Pending and "active under contract" are the same bucket.
    """
    as_of = as_of or datetime.today()
    cutoff = as_of - timedelta(days=TRAILING_DAYS)

    active = [c for c in comparable_listings if c.get("status") == "active"]
    pending = [c for c in comparable_listings if c.get("status") == "pending"]
    closed = [c for c in comparable_listings if c.get("status") == "closed"]
    expired = [c for c in comparable_listings if c.get("status") == "expired"]
    withdrawn = [c for c in comparable_listings if c.get("status") == "withdrawn"]
    hold = [c for c in comparable_listings if c.get("status") == "hold"]
    unrecognized = [c for c in comparable_listings if c.get("status") == "unrecognized"]

    result = {
        "active_count": len(active),
        "pending_count": len(pending),
        "closed_count_total": len(closed),
        "closed_count_trailing": 0,
        "closed_window_date_range": None,
        "expired_count": len(expired),
        "withdrawn_count": len(withdrawn),
        "hold_count": len(hold),
        "unrecognized_count": len(unrecognized),
        "divisor_months": None,
        "monthly_pace": None,
        "absorption_rate": None,
        "months_of_supply": None,
    }

    all_closed_dates = [d for d in (try_parse_date(c.get("close_date")) for c in closed) if d]
    if not active or not all_closed_dates:
        return result

    closed_in_window = [d for d in all_closed_dates if d >= cutoff]
    result["closed_count_trailing"] = len(closed_in_window)
    if closed_in_window:
        result["closed_window_date_range"] = (min(closed_in_window).date().isoformat(), max(closed_in_window).date().isoformat())

    # If we don't actually have a full 12 months of history yet (e.g. a newer
    # subdivision), use however much history exists instead of assuming a
    # full year of opportunity to sell — otherwise the pace understates.
    earliest = min(all_closed_dates)
    available_months = max((as_of - earliest).days / 30.0, 1)
    divisor_months = min(STANDARD_DIVISOR_MONTHS, available_months)
    result["divisor_months"] = round(divisor_months, 1)

    if closed_in_window:
        monthly_pace = len(closed_in_window) / divisor_months
        result["monthly_pace"] = round(monthly_pace, 1)
        result["absorption_rate"] = round(monthly_pace / len(active), 3)
        result["months_of_supply"] = round(len(active) / monthly_pace, 1)

    return result


def absorption_by_property_type(comparable_listings: list, as_of=None) -> dict:
    """
    Groups comps by property_type bucket (Single Family / Townhome / Condo /
    Other) and computes absorption separately for each — blending, say,
    townhomes and single-family into one rate hides real differences in how
    fast each actually moves in the same market at the same time.
    """
    buckets = {}
    for c in comparable_listings:
        bucket = bucket_property_type(c.get("property_type"))
        buckets.setdefault(bucket, []).append(c)

    return {bucket: compute_absorption(listings, as_of=as_of) for bucket, listings in buckets.items()}


def data_scope_summary(comparable_listings: list) -> dict:
    """
    Purely data-derived disclosure of what scope produced the comp figures —
    modeled on the "Applied filters" section April liked in her ShowingTime
    report, but built only from what's verifiable in the data itself rather
    than guessing at Amy's actual search criteria (which we can't know, and
    might not exactly match the data if nothing sold right at a stated
    price ceiling, for example).
    """
    subdivisions = sorted({c["subdivision"] for c in comparable_listings if c.get("subdivision")})
    cities = sorted({c["city"] for c in comparable_listings if c.get("city")})
    postal_codes = sorted({c["postal_code"] for c in comparable_listings if c.get("postal_code")})

    if len(subdivisions) == 1:
        geography = f"Subdivision: {subdivisions[0]}"
    elif len(subdivisions) > 1:
        shown = ", ".join(subdivisions[:3]) + ("..." if len(subdivisions) > 3 else "")
        geography = f"{len(subdivisions)} subdivisions ({shown})"
    elif postal_codes:
        geography = f"ZIP {', '.join(postal_codes)}"
    elif cities:
        geography = ", ".join(cities)
    else:
        geography = None

    prices = [
        c.get("sold_price") if c.get("status") == "closed" else c.get("list_price")
        for c in comparable_listings
    ]
    prices = [p for p in prices if p]

    sqfts = [c["square_feet"] for c in comparable_listings if c.get("square_feet")]

    property_types = sorted({bucket_property_type(c.get("property_type")) for c in comparable_listings})

    return {
        "geography": geography,
        "price_range": (min(prices), max(prices)) if prices else None,
        "sqft_range": (min(sqfts), max(sqfts)) if sqfts else None,
        "property_types": property_types,
    }


def _median(values: list):
    values = sorted(values)
    n = len(values)
    if n == 0:
        return None
    mid = n // 2
    return values[mid] if n % 2 else round((values[mid - 1] + values[mid]) / 2, 1)


def median_comp_price_per_sqft(comparable_listings: list):
    """Uses sold price for closed comps (the real transaction price), list
    price otherwise — whichever reflects what a comp actually cost or costs."""
    values = []
    for c in comparable_listings:
        price = c.get("sold_price") if c.get("status") == "closed" else c.get("list_price")
        psf = price_per_sqft(price, c.get("square_feet"))
        if psf:
            values.append(psf)
    return _median(values)


def median_comp_days_on_market(comparable_listings: list):
    values = [c["days_on_market"] for c in comparable_listings if c.get("days_on_market") is not None]
    return _median(values)


def dom_benchmark(comparable_listings: list) -> dict:
    """
    Median DOM split by status, not blended — a pending comp's DOM reflects
    how long it actually took to land an accepted offer, a real benchmark for
    "should this have gone under contract by now." An active comp's DOM is
    just how long it's been sitting unsold so far, a different signal
    entirely. Closed comps are excluded — their DOM includes time that's no
    longer relevant to a listing currently trying to attract an offer.
    """
    active = [c for c in comparable_listings if c.get("status") == "active"]
    pending = [c for c in comparable_listings if c.get("status") == "pending"]
    return {
        "active_median_dom": median_comp_days_on_market(active),
        "pending_median_dom": median_comp_days_on_market(pending),
    }


def price_reductions(price_history: list) -> dict:
    """Counts and totals actual price *decreases* in chronological order —
    an increase (relisting higher) doesn't count as a reduction."""
    dated = [(try_parse_date(p.get("date")), p.get("price")) for p in price_history]
    dated = [(d, p) for d, p in dated if d is not None and p is not None]
    dated.sort(key=lambda dp: dp[0])

    count = 0
    total = 0
    for (_, prev_price), (_, price) in zip(dated, dated[1:]):
        if price < prev_price:
            count += 1
            total += prev_price - price

    return {
        "count": count,
        "total_amount": total,
        "chronological": [{"date": d.date().isoformat(), "price": p} for d, p in dated],
    }


MIN_KNOWN_FOR_RATE = 5
MIN_MONTHS_WITH_DATA = 4
MIN_PER_MONTH_BUCKET = 3
TREND_THRESHOLD_POINTS = 10


def _had_reduction(comp: dict):
    """True/False if we know both prices for this comp, else None (unknown,
    not "no reduction") — a comp missing original_list_price shouldn't
    silently count as "never reduced"."""
    list_price = comp.get("list_price")
    original = comp.get("original_list_price")
    if list_price is None or original is None:
        return None
    return list_price < original


def _reduction_rate(comps: list) -> dict:
    known = [r for r in (_had_reduction(c) for c in comps) if r is not None]
    reduced = sum(1 for r in known if r)
    return {
        "total": len(comps),
        "known": len(known),
        "reduced": reduced,
        "pct": round(100 * reduced / len(known)) if len(known) >= MIN_KNOWN_FOR_RATE else None,
    }


def comp_price_reduction_stats(comparable_listings: list, as_of=None) -> dict:
    """
    How many pending/closed comps show at least one price reduction (current
    list price below original list price) before reaching that status, plus
    whether closed comps' reduction rate is trending over the trailing 12
    months. Trend uses close_date — the only reliable per-comp date field;
    comps don't carry a list date the way the subject property does, so a
    trend for pending/active comps isn't computable from what we're given.
    """
    as_of = as_of or datetime.today()
    cutoff = as_of - timedelta(days=365)

    pending = [c for c in comparable_listings if c.get("status") == "pending"]
    closed = [c for c in comparable_listings if c.get("status") == "closed"]

    result = {
        "pending": _reduction_rate(pending),
        "closed": _reduction_rate(closed),
        "trend": {
            "enough_data": False,
            "months_with_data": 0,
            "earlier_pct": None,
            "recent_pct": None,
            "direction": None,
        },
    }

    # Bucket closed comps with a known close_date + known reduction status
    # by month, trailing 12 months only.
    monthly = {}
    for c in closed:
        reduced = _had_reduction(c)
        close_date = try_parse_date(c.get("close_date"))
        if reduced is None or close_date is None or close_date < cutoff:
            continue
        key = (close_date.year, close_date.month)
        bucket = monthly.setdefault(key, {"known": 0, "reduced": 0})
        bucket["known"] += 1
        bucket["reduced"] += 1 if reduced else 0

    usable_months = {k: v for k, v in monthly.items() if v["known"] >= MIN_PER_MONTH_BUCKET}
    result["trend"]["months_with_data"] = len(usable_months)

    if len(usable_months) < MIN_MONTHS_WITH_DATA:
        return result

    ordered_keys = sorted(usable_months.keys())
    midpoint = len(ordered_keys) // 2
    earlier_keys, recent_keys = ordered_keys[:midpoint], ordered_keys[midpoint:]
    if not earlier_keys or not recent_keys:
        return result

    def pct_for(keys):
        known = sum(usable_months[k]["known"] for k in keys)
        reduced = sum(usable_months[k]["reduced"] for k in keys)
        return round(100 * reduced / known) if known else None

    earlier_pct, recent_pct = pct_for(earlier_keys), pct_for(recent_keys)
    if earlier_pct is None or recent_pct is None:
        return result

    diff = recent_pct - earlier_pct
    if diff >= TREND_THRESHOLD_POINTS:
        direction = "rising"
    elif diff <= -TREND_THRESHOLD_POINTS:
        direction = "falling"
    else:
        direction = "flat"

    result["trend"].update({
        "enough_data": True,
        "earlier_pct": earlier_pct,
        "recent_pct": recent_pct,
        "direction": direction,
    })
    return result


def match_price_band(list_price, bands: list):
    """
    Given a list price and a list of {"band": "$310,000 - $319,999", ...},
    return the band string the price falls into, or None if it can't be
    determined (e.g. bands aren't in a recognizable "$X - $Y" format).
    """
    if not list_price or not bands:
        return None

    for entry in bands:
        band = entry.get("band", "")
        digits = [int("".join(ch for ch in part if ch.isdigit())) for part in band.split("-") if any(ch.isdigit() for ch in part)]
        if len(digits) == 2:
            low, high = sorted(digits)
            if low <= list_price <= high:
                return band
        elif len(digits) == 1 and list_price >= digits[0]:
            # bands like "$400,000" as an open-ended top bucket
            return band

    return None
