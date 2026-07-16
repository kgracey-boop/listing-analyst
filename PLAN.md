# Listing Activity Report App — Plan

## Goal
Drop in messy listing PDFs, get back a polished, data-grounded client update.
Audit missing data → Analyze charts/tables → Narrate (agent picks a theme) → Publish (web dashboard + PDF).

## Real objective (as of the pitch to April)
This isn't just a personal tool — Kevin is building it to sell/hand off to other
agents, starting with a demo for April (get her sample reports for one property first).
That raises open questions to revisit before going multi-agent: who pays for Gemini
API usage per agent, is it one shared app or one copy per agent, and Streamlit
Community Cloud's free tier may not suit a paid multi-agent product.

## Tabled for now (eventual goal, not in scope yet)
**Automatic scheduled emails to sellers.** Kevin promised this to April as a future
capability, but it's explicitly deferred — it needs the app to run unattended,
send real emails, and risks sending AI-written commentary without human review,
which conflicts with the human-in-the-loop principle below. Revisit after the
demo lands and core phases are solid.

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
- **Format robustness.** Only tested against one report template so far. April's
  reports (probably a different format/source) will be the real test of whether
  the extraction prompt generalizes.
- **Business model.** Free for other agents, or paid? Decides who pays for
  Gemini API usage when other agents run reports — still unresolved from the
  original "real objective" note above.

## The 3 Common Stories (fallback preset buttons — see Phase 3 for the redesign)
1. **Priced too high** — Is there similar inventory available at a lower price?
2. **Market exhausted** — Has activity (showings/views) dropped off at this price?
3. **Waiting for the right buyer** — Are we even at median days on market yet, or already beyond it?
4. *(to add)* **Doing well** — strong activity, expect an offer soon / still in the new-listing honeymoon period
