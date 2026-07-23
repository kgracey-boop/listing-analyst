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
    "ranch": "Single Family",
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
    Groups comps by property_type bucket (Single Family / Townhome / Condo)
    and computes absorption separately for each — blending, say, townhomes
    and single-family into one rate hides real differences in how fast each
    actually moves in the same market at the same time. Comps that don't
    match one of those three (a duplex, manufactured housing, anything with
    no property type at all) are just left out of this breakdown entirely —
    blending a duplex and a manufactured home into one "Other" bar would be
    just as meaningless as blending them into everything else.
    """
    buckets = {}
    for c in comparable_listings:
        bucket = bucket_property_type(c.get("property_type"))
        if bucket == "Other/Unknown":
            continue
        buckets.setdefault(bucket, []).append(c)

    return {bucket: compute_absorption(listings, as_of=as_of) for bucket, listings in buckets.items()}


def _normalize_subdivision(value):
    if not value:
        return None
    return value.strip().lower()


def subdivision_vs_zip_absorption(comparable_listings: list, subject_subdivision: str, subject_property_type: str, as_of=None):
    """
    Compares months-of-supply for the subject's own subdivision against the
    rest of the zip — both filtered to the subject's own property type
    bucket first, since comparing a house to condos that happen to share a
    zip code isn't a fair comparison. Returns None if the subject's
    subdivision isn't known (nothing to split the zip-wide pull on).
    """
    target = _normalize_subdivision(subject_subdivision)
    if not target:
        return None

    bucket = bucket_property_type(subject_property_type)
    same_type = [c for c in comparable_listings if bucket_property_type(c.get("property_type")) == bucket]

    subdivision_comps = [c for c in same_type if _normalize_subdivision(c.get("subdivision")) == target]
    rest_of_zip_comps = [c for c in same_type if _normalize_subdivision(c.get("subdivision")) != target]

    return {
        "subdivision": compute_absorption(subdivision_comps, as_of=as_of),
        "rest_of_zip": compute_absorption(rest_of_zip_comps, as_of=as_of),
    }


def filter_by_subdivision(comparable_listings: list, subject_subdivision: str) -> list:
    """Comps whose subdivision matches the subject's own — same
    case/whitespace-insensitive matching as subdivision_vs_zip_absorption().
    Returns every comp unfiltered if the subject's own subdivision isn't
    known, since there's nothing to match against."""
    target = _normalize_subdivision(subject_subdivision)
    if not target:
        return list(comparable_listings)
    return [c for c in comparable_listings if _normalize_subdivision(c.get("subdivision")) == target]


def comp_price(comp: dict):
    """The one price that matters for scoping a comp against the subject:
    sold price once closed (that's the real outcome), list price otherwise.
    None if neither is known."""
    return comp.get("sold_price") if comp.get("status") == "closed" else comp.get("list_price")


def default_price_band(list_price, spread: float = 0.3):
    """A starting price range around the subject's own list price -- e.g.
    $375,000 at the default 30% spread gives ~$262,000-$488,000. A CSV pull
    covering an entire MLS region (starter condos to multi-million-dollar
    estates) isn't a meaningful comp set for one specific listing no matter
    how big it is; this gives every report a sane default scope out of the
    box, adjustable in the UI rather than requiring a re-pull upstream.
    Rounded to the nearest $1,000 since exact-cent precision here is false
    confidence. Returns None if list_price isn't known -- nothing sensible
    to center a band on."""
    if not list_price:
        return None
    return (round(list_price * (1 - spread), -3), round(list_price * (1 + spread), -3))


def filter_by_price_band(comparable_listings: list, price_band) -> list:
    """Keeps only comps whose price (see comp_price()) falls within
    price_band = (low, high). price_band=None means no filtering. A comp
    with no price at all is dropped rather than assumed in-range, since
    there's no way to judge whether it belongs."""
    if price_band is None:
        return list(comparable_listings)
    low, high = price_band
    kept = []
    for c in comparable_listings:
        price = comp_price(c)
        if price is not None and low <= price <= high:
            kept.append(c)
    return kept


WEEKLY_CONTRACTS_WEEKS = 104  # roughly 2 years


def weekly_contracts(comparable_listings: list, subject_property_type: str, weeks: int = WEEKLY_CONTRACTS_WEEKS, as_of=None) -> list:
    """
    Count of comps — filtered to the subject's own property type bucket —
    that went under contract each week, over the trailing ~2 years. A
    market-pulse view of contract velocity, not a comparison metric like
    the absorption charts: townhomes and single-family buyers can react to
    rate moves on very different timelines, so blending them here would
    hide exactly the signal this is meant to show. Weeks with zero
    contracts are included as zero, not skipped, so a real dead spot in the
    market doesn't silently compress out of the timeline.
    """
    as_of = as_of or datetime.today()
    bucket = bucket_property_type(subject_property_type)
    same_type = [c for c in comparable_listings if bucket_property_type(c.get("property_type")) == bucket]

    cutoff = as_of - timedelta(weeks=weeks)

    def week_start(d):
        return d - timedelta(days=d.weekday())

    start_week, end_week = week_start(cutoff), week_start(as_of)

    counts = {}
    current = start_week
    while current <= end_week:
        counts[current.date().isoformat()] = 0
        current += timedelta(weeks=1)

    for c in same_type:
        contract_date = try_parse_date(c.get("contract_date"))
        if contract_date is None or contract_date < cutoff or contract_date > as_of:
            continue
        key = week_start(contract_date).date().isoformat()
        if key in counts:
            counts[key] += 1

    return [{"week_start": k, "count": v} for k, v in sorted(counts.items())]


def compute_new_construction_absorption(comparable_listings: list, as_of=None) -> dict:
    """
    Same months-of-supply formula as compute_absorption(), but scoped to New
    Construction comps and using Purchase Contract Date as the "sold" event
    instead of Close Date. A new-construction close date is stretched out by
    real build time (a home can sit under contract for months waiting on
    completion) — contract date is the actual buyer-commitment signal, and
    it's available on both pending and closed rows since either one already
    went under contract, regardless of whether it's closed yet.
    """
    as_of = as_of or datetime.today()
    cutoff = as_of - timedelta(days=TRAILING_DAYS)

    nc = [c for c in comparable_listings if c.get("new_construction") is True]
    active = [c for c in nc if c.get("status") == "active"]
    under_contract = [c for c in nc if c.get("status") in ("pending", "closed")]

    result = {
        "active_count": len(active),
        "under_contract_count_total": len(under_contract),
        "under_contract_count_trailing": 0,
        "divisor_months": None,
        "monthly_pace": None,
        "months_of_supply": None,
    }

    all_contract_dates = [d for d in (try_parse_date(c.get("contract_date")) for c in under_contract) if d]
    if not active or not all_contract_dates:
        return result

    contracts_in_window = [d for d in all_contract_dates if d >= cutoff]
    result["under_contract_count_trailing"] = len(contracts_in_window)
    if not contracts_in_window:
        return result

    # Same "use however much history exists" fallback as compute_absorption()
    # — a subdivision that's only recently started closing under-contract
    # deals shouldn't have its pace penalized by assuming a full year existed.
    earliest = min(all_contract_dates)
    available_months = max((as_of - earliest).days / 30.0, 1)
    divisor_months = min(STANDARD_DIVISOR_MONTHS, available_months)
    result["divisor_months"] = round(divisor_months, 1)

    monthly_pace = len(contracts_in_window) / divisor_months
    result["monthly_pace"] = round(monthly_pace, 1)
    result["months_of_supply"] = round(len(active) / monthly_pace, 1)

    return result


def median_list_to_contract_days(comparable_listings: list, new_construction: bool = None):
    """Median days from list date to contract date. new_construction=True/
    False filters to that cohort; None uses every comp with both dates
    regardless of construction status. Rows missing either date, or with a
    contract date before the list date (bad data), are skipped rather than
    guessed at."""
    rows = comparable_listings
    if new_construction is not None:
        rows = [c for c in rows if c.get("new_construction") is new_construction]

    days = []
    for c in rows:
        list_d = try_parse_date(c.get("list_date"))
        contract_d = try_parse_date(c.get("contract_date"))
        if list_d and contract_d and contract_d >= list_d:
            days.append((contract_d - list_d).days)
    return _median(days)


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
            "monthly_pcts": [],
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

    # Exposed for the price-drop trend chart — same months, gated on the
    # same MIN_MONTHS_WITH_DATA threshold as the earlier/recent split below,
    # so the chart never shows with less data than the trend label would.
    result["trend"]["monthly_pcts"] = [
        {
            "month": f"{y:04d}-{m:02d}",
            "pct": round(100 * usable_months[(y, m)]["reduced"] / usable_months[(y, m)]["known"]),
        }
        for (y, m) in ordered_keys
    ]

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


def filter_recent_closed(comparable_listings: list, months: int = None, as_of=None) -> list:
    """Keeps active/pending comps as-is; filters closed comps to those that
    closed within the trailing `months` window. months=None means no
    filtering (all closed comps kept). A closed comp with an unparseable/
    missing close_date is dropped rather than assumed recent — used to keep
    the price-vs-days-on-market chart focused on comps that are actually
    verifiably recent, not a multi-year CSV pull's full sold history."""
    if months is None:
        return list(comparable_listings)

    as_of = as_of or datetime.today()
    cutoff = as_of - timedelta(days=months * 30)

    kept = []
    for c in comparable_listings:
        if c.get("status") != "closed":
            kept.append(c)
            continue
        close_date = try_parse_date(c.get("close_date"))
        if close_date is not None and close_date >= cutoff:
            kept.append(c)
    return kept


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
