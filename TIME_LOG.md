# Time Log — Listing Activity Report App

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
