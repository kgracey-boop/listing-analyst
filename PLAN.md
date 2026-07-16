# RootedReports — Plan

## In design — running/deduplicated comp set per property (2026-07-16)
Currently, comps only exist inside each saved report's own snapshot — no running
record across visits. Kevin wants to move to one persistent, deduplicated comp
set per property that gets *updated* (not just appended to) every time a new
report is saved. Designed but not yet built:

- **New store**: a third JSONB blob on the `properties` table (`known_comps`),
  matching how `profile`/`history` already work — no new relational table needed.
- **Merge semantics differ by field type**, unlike the same-session multi-source
  merge (which just fills gaps since sources describe the same moment):
  - Time-varying fields (status, price, DOM, close_date) → **newest data wins**.
    "Newest" should be judged by the actual date *in* the data (e.g. close date),
    not upload order — an old cut sheet uploaded after fresher CSV data
    shouldn't clobber it just by arriving second.
  - Stable fields (property_type, subdivision, city, address) → keep once known,
    never need relearning.
- **Key by address, not MLS#.** A relisted property gets a new MLS# but is the
  same physical home — using address as the primary identity means an exclusion
  or learned property type survives a relisting instead of silently resetting.
- **Manual exclusion (Kevin's idea, 2026-07-16):** agent can exclude a specific
  comp from the absorption/median/property-type calculations (e.g. "this one's
  too unique to compare"), with an optional free-text reason. The exclusion
  persists across future re-merges — it's a judgment about comparability, not
  a one-time session state.
  - Excluded comps still **display** in the comps table (grayed out or similar),
    just excluded from the math — hiding them would break the "always surface
    data-quality info" rule the rest of the app follows.
  - UI-wise this points to `st.data_editor` with a checkbox column instead of
    the current read-only `st.dataframe` comps tables.
  - Exclusion is scoped **per subject property**, not global — the same comp
    could be a fair comparison for one client's listing and not another's.
  - `data_confidence_warning`'s sample-size check needs to run on the
    post-exclusion count, or it'll understate how thin the real sample is.
- **Client-facing exports** shouldn't need to itemize which comps were excluded
  or why — just show the resulting clean numbers, maybe a general note like
  "some comps excluded as not directly comparable" if any disclosure is wanted.
- **Migration**: existing properties with history but no `known_comps` yet would
  need a one-time backfill (replay all past snapshots' comps into a fresh running
  set), similar in spirit to the earlier `migrate_to_db.py` one-off script.
- **Open follow-on idea, not decided**: since this creates a real running
  absorption-rate-over-time dataset, the existing momentum/trend section could
  eventually chart absorption rate/months-of-supply history alongside views —
  worth revisiting once the running set itself exists.

## Goal
Drop in messy listing PDFs, get back a polished, data-grounded client update.
Audit missing data → Analyze charts/tables → Narrate (agent picks a theme) → Publish (web dashboard + PDF).

## Design principle: hide technical errors, always surface data-quality caveats (2026-07-16)
Two different kinds of "didn't behave as expected," treated deliberately differently:
- **Technical/implementation failures** (a Gemini call errors, a network hiccup) —
  hidden from the agent per Kevin's "clean, curated experience" direction. Logged
  server-side (`print()`), surfaced only as a gentle "double-check these numbers"
  nudge. The *why* isn't useful to the agent, and raw errors erode trust in the product.
- **Data-quality uncertainty** (unrecognized status values, sources that disagree,
  a shorter history window than ideal, missing fields, too few comps to trust a
  calculation) — **always** surfaced. These directly affect whether the numbers
  about to reach a client can be trusted, so hiding them would undercut the
  don't-overstate-confidence principle the whole app is built on.
Concrete examples already following this rule: expired/withdrawn/hold/unrecognized
comp counts shown and excluded from calculations rather than silently dropped;
the "limited history available" note when there's less than 12 months of comp
data; the low-sample-size warning (`data_confidence_warning` in app.py) when a
CSV has too few total comps or too few trailing-12-month sales to trust the
absorption rate; a hard error (not just a quiet skip) if a CSV parses to zero
usable comps at all.

## Real objective (as of the pitch to April)
This isn't just a personal tool — Kevin is building it to sell/hand off to other
agents, starting with a demo for April (get her sample reports for one property first).
That raises open questions to revisit before going multi-agent: who pays for Gemini
API usage per agent, is it one shared app or one copy per agent, and Streamlit
Community Cloud's free tier may not suit a paid multi-agent product.

**Deadline (set 2026-07-16):** Kevin told April he'd have a demo AND a "proposal
for roll-out" to her by this weekend (~2026-07-18/19). Two deliverables, not one —
the rollout proposal is a written business document, separate from the app itself.

**Real production workflow, as described to April (2026-07-16):**
- Amy (April's assistant, licensed, full MLS access) runs reports out of
  **Paragon** (the specific MLS software) and exports to **CSV** for upload —
  confirms CSV is the real long-term path for MLS comp data, not PDF.
- Target: **15 minutes or less of Amy's time per property** to gather the data,
  with the app then auto-drafting the consolidated report in a few minutes. This
  is a real UX constraint on the upload flow, not just an accuracy target — it
  needs to stay fast and low-friction.
- April is paying Amy for her time — the labor-cost question is handled on her
  end. The Gemini API cost question (who pays per agent) is still open.

## April's real requirements (from her feedback, 2026-07-16)
First real input from an actual target user (not just Kevin's own guesses). She
sent 5 report types she currently uses on her own listings and what she values
in each — this should now drive the extraction schema and Phase 4 design more
than the earlier speculative plan.

**Overarching mandate:** summarize across all reports, highlight what matters
most, use graphics wherever possible, and simplify heavily — "providing all of
this overwhelms even the most information loving clients." This is the strongest
validation yet of the human-in-the-loop/simplify-for-client philosophy the app
was already built around — but it means Phase 4's client-facing export needs to
be much more visual than anything built so far (internally we only have plain
text + one bar chart; nothing polished/graphic for the actual seller-facing side).

**The 5 report types and what she likes about each:**
1. **Doorify Listing Activity Report** — "people who viewed this also viewed"
   competitor link. Sellers can click through to see their actual competition.
2. **MLS - Active, Pending & Closed (last 30 days)** — competing active listings
   (price, DOM, price/sqft), pending count (what's actually gone under contract),
   closed comps (original vs. actual sale price, price/sqft, DOM). She wants
   **absorption rate** calculated from this. Also wants a link to see the active
   competition.
3. **ShowingTime Listing Activity Report** — number of showings, buyer feedback,
   who is/isn't interested (implies feedback should be categorized, not just a
   flat list of comments).
4. **ShowingTime Pricing Benchmark Report** — combines DOM + showings; visual
   comparison of where the listing is priced vs. active/pending/closed; price
   reduction data; absorption info. **Caveat she flagged herself:** this report
   can't be filtered by date range, so she questions whether its DOM/absorption
   numbers reflect stale data — worth applying the same skepticism to any
   absorption/DOM math we compute ourselves (flag the reporting period if unclear,
   same as the existing missing-data notes).
5. **ShowingTime Target Market Analysis Report** — price band where most showings
   are concentrated. She wants the **subject listing's own price band highlighted**
   within that, not just shown as one more data point.

**Concrete gaps this reveals in the current data model/extraction prompt:**
- No price-per-square-foot field (list or sold) — needed for comps.
- No absorption rate calculation — needs active + pending + closed counts (or a
  stated monthly sales pace) to compute; not currently modeled at all.
- No structured comparable/competing-listings data with a clickable link —
  currently `comparable_sales` exists but has no link field and isn't surfaced
  as something to click through to.
- No price-band/target-market-analysis concept at all.
- Feedback is currently a flat list of strings — may need light categorization
  (interested vs. not, common objections) to match "who is/isn't interested."
- 5 distinct source formats (only 1 has ever actually been tested) — real test
  of whether one shared extraction prompt generalizes, or whether some fields
  need format-specific handling.

April said more reports are coming in a second email; these 5 are for one real
listing currently facing heavy competition in its subdivision — a good real
stress test once the files are in hand.

## Tabled for now (eventual goal, not in scope yet)
**Automatic scheduled emails to sellers.** Kevin promised this to April as a future
capability, but it's explicitly deferred — it needs the app to run unattended,
send real emails, and risks sending AI-written commentary without human review,
which conflicts with the human-in-the-loop principle below. Revisit after the
demo lands and core phases are solid.

**Hunch-based commentary ("what's your read on this listing?") — tabled 2026-07-16.**
Kevin's call, given the weekend deadline: focus on getting the data correct and
displayed cleanly first, add the AI-written commentary layer back in later. The
underlying `generate_commentary` function still exists in `gemini_io.py`, just
not called from the UI right now.

## App restructured into a 3-step flow (2026-07-16)
Kevin's direction: sequential Gemini calls per document were slow, and he wants
a clean, curated experience — no visible Gemini/technical error text to the user.
Property view is now three stages instead of one long scrolling page:
1. **MLS comp data (CSV)** — parsed instantly in plain code (`csv_parser.py`),
   no Gemini call at all. Flexible column-name matching so it tolerates
   different MLS export formats. Shows absorption stats + comp table
   immediately for the agent to sanity-check before continuing. Skippable.
2. **Other reports** — PDFs/screenshots that still need Gemini (Doorify,
   ShowingTime, etc.). Loading state shows file progress + a rotating Raleigh
   oak-tree/squirrel fact (Kevin's idea) instead of exposing "Gemini" by name.
   Extraction failures are logged server-side (`print()`) and surfaced to the
   agent only as a gentle "double-check these numbers" note — never a raw
   exception.
3. **Review** — merged data, editable fields, momentum, market comparison
   (absorption/price-sqft/price-band), save-to-history, PDF download.

CSV-parsed comps flow into the same `merge_extractions()` pipeline as
Gemini-extracted data — added as a pseudo-source tagged `"MLS CSV export"` —
so no separate merge logic was needed for the two input paths.

## Absorption rate — rebuilt to industry standard (2026-07-16)
Original approach normalized pace to whatever date span a single report
happened to cover — an improvement over trusting a report's "last 30 days"
label blindly, but still too short/noisy a sample vs. real appraisal practice.

**Real industry standard:** months of supply = active listings ÷ average
monthly sold pace, where the pace is a **trailing 12-month** average (NAR/
appraisal convention — smooths out real estate's seasonal lumpiness that a
30-day slice can't).

**Decided:** Kevin will now instruct Amy to pull a **2-year CSV** covering
active, pending, active under contract, closed/sold, expired, withdrawn, and
coming soon — not just the 30-day snapshot. Implementation in
`market_stats.compute_absorption()`:
- Sold pace = closings in the trailing 365 days ÷ 12 (or ÷ however many months
  of history actually exist, if less than a full year — e.g. a newer
  subdivision — rather than falsely assuming a full year of opportunity to sell)
- "Active Under Contract" → counted as pending (Kevin's explicit instruction);
  "Coming Soon" → counted as active
- Expired and withdrawn are tracked and shown for context but **excluded**
  from the calculation — neither current inventory nor a completed sale
- Buyer's/seller's market convention worth remembering for later commentary:
  <3 months = seller's market, 3-6 = balanced, >6 = buyer's market

**Segmented by property type (2026-07-16).** Kevin's real-data test confirmed
the concern: the same subdivision had 98 townhomes vs. 75 single-family homes,
and blending them gave a misleading average (5.5 months of supply blended, vs.
6.9 for townhomes / 3.6 for single family once split — nearly a 2x difference
hidden by the blend). `csv_parser.bucket_property_type()` normalizes MLS
"Property Sub Type" values into Single Family / Townhome / Condo / Other;
`market_stats.absorption_by_property_type()` computes the rate separately per
bucket. The subject property's own bucket (from its cut sheet) gets highlighted
in the breakdown. Didn't add a geographic-scope (zip code vs. subdivision)
feature — the existing low-sample-size warning already signals when Amy needs
to broaden the pull, so a tight/comparable default area is preferable to
always defaulting wider and losing comparability.

## Tech stack ($0)
- Brain: Gemini (via Google AI Studio)
- Skeleton: Python
- Face: Streamlit
- Home: Streamlit Community Cloud
- PDF Maker: FPDF2

## Phase 1: Extraction Test — DONE
Confirmed Gemini can read a real listing PDF and pull out address, price history,
showings, etc. without hallucinating, and it correctly flags missing data.

## Phase 2: The "Drafting Room" (App UI) — BUILT, mid-testing
- Split view: left = upload + editable fields, right = theme selector — done
- **History/trend tracking** — done. Every saved report stores that property's
  numbers with the date; the next report compares against the last save.
- **New: entry menu.** When the agent opens the app, first screen is a choice:
  work on an existing property, or add a new one. "Existing" lists properties
  already in the `history/` folder (already keyed by address — just needs a
  list view). "New" flow below.
- **New property flow, simplified (2026-07-13).** Original idea was to accept
  either a file upload or a link to the online listing (Zillow etc.) to
  auto-fill basic facts (address, price, beds/baths, photos). Kevin was
  skeptical the link-fetch would actually work — correctly: Zillow specifically
  fights automated fetching hard (bot detection, JS-rendered pages, CAPTCHAs),
  so a simple page fetch would likely just hit a wall, on top of the ToS gray
  area already flagged. Dropped in favor of: **agent types the address by hand,
  then uploads their MLS cut sheet** (the standard one-page MLS listing detail
  printout with price/beds/baths/photos/remarks). This reuses the same PDF-
  reading capability already proven in Phase 1 instead of new, fragile scraping
  — no ToS risk either, since it's the agent's own MLS export.
- **Not yet built: multi-source uploads.** Agents may run several different
  report types per property (MLS PDF, Zillow screenshot, Realtor.com screenshot).
  Plan: extract each file separately (one Gemini call per file, tagged by source),
  then merge in code — not one big combined call — so the agent-facing view can
  show conflicting numbers side by side (e.g. "Showings: 2 (MLS) / 5 (Zillow)")
  for the agent to resolve by editing, same as any other field. Numbers that are
  genuinely different metrics (Zillow views vs. Realtor.com views) should stay as
  separate line items rather than being summed or overwritten. The seller-facing
  export only ever shows the single resolved number, never the per-source detail.
- **Not yet built: momentum/trend graph.** Replace the flat "since last report"
  delta with a bar chart of views (or other metrics) gained *between* saved
  reports — not percentage change (misleading with small numbers). Three-stage
  reveal on the agent's screen: 1st report = baseline message only, no comparison;
  2nd report = single delta; 3rd+ report = full bar chart. In the seller-facing
  export, omit the whole momentum section entirely until there are 2-3 reports of
  history — a one-bar chart in a polished report looks unfinished, not intentional.
- **Tabled:** pulling data directly from the MLS via API instead of reading
  PDFs/screenshots. Not feasible right now — the Flexmls/MLS connection available
  in this Claude session is authenticated for Claude's own use, not something the
  standalone app can call. Would require registering as a vendor with the MLS
  board for real API credentials — a real process, not a quick add. Revisit later
  if it seems worth pursuing.

## Phase 3: Commentary Engine — not started
- Commentary is a draft — agent remains the editor
- **Redesigned (2026-07-13): agent's hunch is primary, not a preset menu.**
  Original idea was the AI hands the agent a menu of 3-5 themes to pick from.
  Kevin's pushback: that risks oversimplifying — the agent often has the sharpest
  insight in the room (something a buyer's agent said, a gut read from experience)
  and picking from someone else's canned options doesn't use that. New design:
  - **Primary input: a free-text field** where the agent types their own theory
    in plain language ("I think buyers are put off by the busy road," "I think
    we're losing to the new listing on Elm St").
  - The app's job is to check that hunch against the data honestly — confirm,
    contradict, or say it can't tell — e.g. "Consistent with the data: showings
    dropped right after the Elm St listing went active" or "Can't confirm this —
    only 2 written feedback responses exist, neither mentions the road." This
    matches the app's original audit/no-hallucination principle better than
    generating a canned narrative would.
  - **Preset story buttons remain as a fast fallback** for when the agent doesn't
    have a theory yet — including a "good news" option now (see below), not just
    underperformance framing.
- **New: adjustable tone/prompt.** Alongside the hunch (the *what*), give the
  agent control over the *how*: a few preset tone buttons (Warm & reassuring /
  Direct & data-driven / Brief & to the point) plus an optional free-text box for
  one-off notes like "this seller is an engineer, keep it data-heavy" or "be less
  fluffy." Since every draft is reviewed by the agent before a seller sees it,
  variable output quality from free text is an acceptable risk.
- **The 3 Common Stories, expanded.** Original 3 were all underperformance-framed
  (priced too high, market exhausted, waiting for buyer). Needs a "doing well"
  option added too (e.g. "strong activity, expect an offer soon" / "still in the
  new-listing honeymoon period") so a healthy listing isn't forced into a
  problem-diagnosis narrative. Exact wording still to be finalized.
- **Open question — commentary voice.** No real examples of Kevin's own writing
  style have been gathered yet. Need 2-3 real emails/texts he's sent a seller so
  Gemini can imitate his actual voice instead of generic AI tone.

## Phase 4: Export Engine — not started
- Web dashboard: mobile-friendly client link
- PDF: clean one-pager, print-ready
- **Open question — client link privacy.** The seller-facing link will show real
  financial/personal data about their home. Needs to be an unguessable URL (not
  indexed, not easily stumbled onto) by design, not bolted on after the fact.

## Other open questions (not yet assigned to a phase)
- **MLS data usage rules.** Some MLSs restrict how their data can be fed into
  third-party AI tools, especially once this isn't just Kevin's personal use but
  a product other agents run. Worth a check with his broker/MLS before going
  further than a personal demo.
- **Business model — DECIDED 2026-07-16: monthly subscription.** Still need to
  work out pricing and who specifically absorbs Gemini API cost per agent, but
  the model itself (subscription, not free/one-time) is settled. Rollout
  proposal document deliberately deprioritized until the demo itself is done.

## Format robustness — tested 2026-07-16 against April's real reports
Tested one shared/generic extraction prompt against all 5 of April's real report
types (Doorify, MLS active/pending/closed with 37 comps, 3 ShowingTime report
types). Result: generalized well, no format-specific prompting needed. Confirmed
Gemini cannot extract real PDF hyperlinks (not part of rendered visual content)
but reliably captures visible MLS# reference numbers as a substitute — enough
for an agent to look up manually, or to build our own search link from later.

**Decided 2026-07-16: data quality first, then visuals.** Kevin's call — wire in
the extended schema and get the underlying numbers/calculations right before
building any charts. Visuals will be custom-rendered from real computed data
(a Python charting library, not Gemini-described/hallucinated) once the data
layer is solid.

**New extraction/data-model fields needed (in progress):**
- `square_feet` on the subject property and on each comparable listing
- `comparable_listings`: address, status (active/pending/closed), list price,
  original list price, sold price, sqft, DOM, close date, MLS#/reference
- `price_band_analysis`: bands with showing counts, subject property's band
  computed by the app itself (source reports don't highlight it — confirmed
  by testing, this is a value-add the app provides, not an extraction gap)
- Absorption rate + months-of-supply computed in plain code from comp counts,
  never asked of Gemini (arithmetic should be deterministic, not LLM output)
- Price-per-square-foot computed in code from list/sold price ÷ sqft

## Future feature idea (brainstormed 2026-07-16, not yet building)
**Listing history / price-drop flags section.** A section in the report that
flags significant events over time — price reductions especially. Likely pulls
from two existing sources: the `price_history` field already in the extraction
schema (some reports state past price changes directly), and the app's own
saved-snapshot history (since price is tracked at every save already). Revisit
once the core data layer + visuals are done.

## The 3 Common Stories (fallback preset buttons — see Phase 3 for the redesign)
1. **Priced too high** — Is there similar inventory available at a lower price?
2. **Market exhausted** — Has activity (showings/views) dropped off at this price?
3. **Waiting for the right buyer** — Are we even at median days on market yet, or already beyond it?
4. *(to add)* **Doing well** — strong activity, expect an offer soon / still in the new-listing honeymoon period
