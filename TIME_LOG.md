# Time Log — RootedReports

Rough estimates, logged per session at Kevin's request. Not precise timesheets —
just enough to track roughly how much time has gone into this project, with a
short summary of what actually got done.

## 2026-07-16 — ~4 hours

- Migrated storage from local JSON files to a Supabase Postgres database
- Tested the extraction schema against April's 5 real report types (Doorify,
  MLS active/pending/closed, 3 ShowingTime reports) — one shared prompt worked
  well across all of them
- Built the CSV comp pipeline (deterministic parsing, no Gemini call needed)
- Rebuilt absorption rate to the real industry standard — trailing 12 months,
  segmented by property type (found townhomes moving much slower than
  single-family in the same subdivision)
- Added price history/reductions tracking, comp benchmarking (median
  price/sqft, days-on-market vs. pending), and a data-scope disclosure section
- Built a running, deduplicated comp set per property with manual exclusion
  support (persists across future visits)
- Source-linking to the agent's own site by MLS#, cross-source backfill for
  missing fields
- Fixed several bugs (a merge bug losing data on duplicate MLS#s, a silently
  dropped "Hold" status, a couple of dollar-sign rendering glitches, a
  stuck-on-Step-2 navigation bug)
- Deployed to Streamlit Cloud, troubleshot a stale-deploy issue

## 2026-07-17 — ~4 hours

- Also-viewed/also-saved comp tracking, a solds date-filter on the scattergram,
  and a permanent feedback follow-up flag (running store, survives re-extraction)
- Randomized the squirrel-facts rotation (was always showing the same first
  couple of facts on quick extractions)
- Added a market-rate $/sqft reference line to the scattergram and subdivision
  field extraction from MLS cut sheets
- Long design pass converting number-heavy sections into charts: cut a
  redundant price-band text list, added a closed-median DOM reference line,
  turned the price-drop rate into an actual trend chart, and turned the
  property-type absorption breakdown into a real bar chart
- Parsed New Construction YN, Listing Contract Date, and Purchase Contract
  Date from the CSV (previously only Close Date was read) and built a
  contract-date-based months-of-supply calc for New Construction, since its
  close date is stretched out by real build time
- Built a subdivision-vs-rest-of-zip absorption comparison, and a weekly
  contract-volume chart filtered to the subject's own property type
- Verified everything against a real, large zip-wide CSV pull (2,221 rows,
  163 subdivisions, 501 genuine New Construction rows) — confirmed a real
  50-day vs. 27-day list-to-contract gap between New Construction and resale

## 2026-07-17 (continued) — ~2 hours

- Found and fixed a real bug behind blank/missing-chart pages in the PDF:
  no chart set an explicit width, so Vega-Lite's default sizing rendered
  some charts far too narrow/tall outside Streamlit's container-stretch
  behavior — one was taller than the page itself
- Rewrote the PDF export from fpdf2 to real HTML/CSS via WeasyPrint for a
  much more polished look (same brand fonts/palette, charts as inline SVG
  instead of rasterized images) — discussed the tradeoffs (reliability of a
  server-generated PDF vs. browser print-to-PDF) before committing to it
- Deploy troubleshooting: Streamlit Cloud's Debian image needed a different
  apt package name for gdk-pixbuf than what shipped in packages.txt
- Security discussion — identified the biggest real gap (no data isolation
  between agents sharing one passcode/database) ahead of onboarding April
- Added a Terms of Use page (own module, linked from the footer only),
  drafted as a real commercial software license — ownership, restricted
  license grant, explicit right to license/sell to other agents, MLS
  compliance responsibility, third-party processing disclosure
- Made "Prepared by," brokerage, and contact info user-editable fields
  (Step 1) instead of hardcoded to Kevin/Coldwell Banker Advantage — flows
  through to both the on-screen header and the PDF; fixed an unescaped-HTML
  gap in the same code while touching it
- Added a real progress bar to the multi-file loading screen (was text-only)
- Incorporated the new Rooted Reports logo — removed the white background,
  swapped in a white color variant specifically for the navy header/PDF
  hero (much higher contrast than the brown original there), kept the
  brown version for the browser favicon

## 2026-07-16 (evening session) — ~3 hours

- Built sample charts (price-band highlight, price-vs-days-on-market by
  status) to match what April specifically praised in her own report feedback
- Rebuilt the PDF export from a near-blank stub into a real report:
  formatted key numbers, price history, market comparison stats, both
  charts embedded as images, clickable "View" links on active comps
  (restoring the competitor click-through April praised), and a buyer
  feedback table
- Switched feedback from summarized themes to deduplicated, dated, verbatim
  quotes end-to-end (extraction prompt, merge, editor, PDF)
- Fixed the extraction prompt conflating a Target Market Analysis report's
  price-band showing counts with the subject's own showings total
- Added a "Jump to report" menu shortcut for properties with a saved report
- Renamed the app to RootedReports and rebranded it with graceyrealestate.com's
  actual palette (navy/gold) and fonts (Belleza/Work Sans)
- Added price-reduction stats: % of pending/closed comps that dropped price,
  plus a 12-month trend check with an explicit "not enough data yet" gate
- Added 50 more squirrel/oak facts for the loading screen
- Fixed several real bugs along the way (PDF table styling inheriting a
  navy fill, a button-wrapping layout bug from the new uppercase styling,
  a washed-out chart color, a stale-import crash after a dev server reload)
