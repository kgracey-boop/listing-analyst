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
