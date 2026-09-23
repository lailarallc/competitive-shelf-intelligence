# competitive-shelf-intelligence — Current Work Plan

The current arc of work. Updated when the arc changes, not every
session. For session-by-session state, see HANDOFF.md.

---

## Goal — 2026-05-28

Build a web scraping framework and Dash dashboard that monitors
competitor pricing, promo activity, availability, and reviews for real
artisan sauce/condiment brands on Amazon and Walmart — with standalone
Postgres storage and always-on deployment on Fly.io.

## Why this arc, why now

First arc: get the core working end-to-end (scraper → Postgres → dashboard
→ Fly.io). Scheduling, additional retailers, and case study content are
all deferred until the technical core is proven.

## Business question this arc answers

What are competitors doing on shelf right now — and how does a specialty
food brand's price, promo, and availability stack up against them?

## Scope

**In:**
- Python scrapers for Amazon.com and Walmart.com (both from day one)
- Real artisan sauce/condiment brands as the competitive set (scoped during build)
- Standalone Postgres for scraped data storage
- Dash dashboard: price positioning, promo activity, OOS/availability, reviews
  (Dash chosen: already deployed on Fly.io in retail-velocity-decision-tool, uses Plotly natively)
- Fly.io deployment (always-on)
- Synthetic Cinderhaven brand data as a plausible portfolio participant
- Public GitHub repo

**Out:**
- Lead-gen assets (landing pages, social posts, email sequences) — out of scope
- Cinderhaven Data Platform integration — standalone Postgres only
- Automated scraping schedule — manual runs for v1
- 90-day competitive audit as a content piece — evaluated later after data accumulates
- Instacart, Target.com — v2
- Pre-engineered findings — real data tells the real story

## Definition of done for this arc

- [x] Walmart.com proof-of-concept: retrieve product name + price for one product without being blocked
- [x] Postgres schema designed: tables, columns, scrape-run tracking, deduplication strategy
- [x] Entity resolution strategy decided: how products are matched across Amazon and Walmart
- [x] Amazon scraper runs manually and populates Postgres without errors
- [x] Walmart.com scraper runs manually and populates Postgres without errors
- [x] Competitor set defined — 5 brands × 2 retailers filled in (Yellowbird, Truff, Melinda's, Dave's Gourmet, Marie Sharp's)
- [x] Dash dashboard shows: price positioning map, promo activity, OOS/availability, review pulse
- [x] "Last scraped" timestamp visible on dashboard
- [x] Scraper error handling: bad/missing data logged as warning, not silently inserted
- [x] Cinderhaven synthetic data loads into dashboard alongside real competitor data
- [x] Dashboard deployed and live on Fly.io (Dockerfile + fly.toml complete; actual flyctl deploy pending)
- [x] README documents how to run a scrape manually and view the dashboard

## Next arc — code review fixes (2026-05-28)

Code review complete. Three confirmed P1 bugs to fix, five P2 issues, plus maintainability polish.

### P1 — Fix immediately (wrong behavior today)

- [x] **F4** `app/data.py:152` — alias was already `ps.` in committed code; no change needed.
- [x] **F1** `app/data.py:164` — promo depth formula fixed: `(price_cents − sale_price_cents) / price_cents`.
- [x] **REL-001** `scrape.py:91–94` — wrapped `_run_scrape` in try/except; crashes now mark run `'failed'` and re-raise.

### P2 — Fix in same session

- [x] **F5** `walmart.py:342` — removed `availability != ''` guard; missing `availabilityStatus` + no cart now correctly signals OOS.
- [x] **REL-004** `app/data.py` — added `logger.exception()` to all 8 silent `except Exception` blocks.
- [x] **REL-005** `base.py:185` — replaced `rp.read()` with `urllib.request.urlopen(..., timeout=10)` + `rp.parse()`.
- [x] **SEC-002** `entity_resolution.py:120` — replaced f-string column interpolation with `psycopg2.sql.Identifier`.
- [x] **SEC-007** `app/run.py:47` — `debug` now gated on `FLASK_DEBUG` env var.

### P3 — Polish pass

- [x] M01: Removed shadowed `CHART_PALETTE` from `review_pulse.py`; imports from `app.constants`.
- [x] M02: Removed dead imports from `scrape.py` (`hashlib`, `datetime`, `timezone`).
- [x] M05: Replaced all hardcoded Playfair Display strings with `FONT_SERIF` constant (6 files).
- [x] M06: Added `OWN_BRAND = "Cinderhaven"` to `app/constants.py`; used in `data.py`, `price_positioning.py`, `oos_tracker.py`.
- [x] M09: Removed unused `listing_id` param from `fetch_product` in both scrapers and all callers.

---

## Arc history

### 2026-05-28 — Project initialized
- Outcome: Repo scaffolded, state files created, GitHub remote live
- Tag: v0.1-foundation

---

## Arc — Visual overhaul + data fix (2026-06-23)

- [x] Extend synthetic data to 90 days
- [x] Add scrape runs for Assortment Monitor demo
- [x] Fix promo/OOS flags in both loaders
- [x] Fix RadioItems int coercion
- [x] Apply Lailara Design System v2 (tab nav, cards, toggles, AG Grid, empty states)
- [x] Reseed Fly Postgres
- [x] Deploy
- [x] Fix Price Positioning multi-product aggregation bug
- [x] Fix OOS Tracker oos_signal column bug
- [x] Fix Assortment Monitor Status column truncation
- [x] Rewrite Review Pulse to 2-column card grid with compact charts

---

## Improvement history

### 2026-05-28 — Improvement pass
- **Trigger:** User-initiated after project shipped
- **What was reviewed:** Security, code quality, dead code, dependencies, documentation, git hygiene
- **What was fixed:** Hardcoded credentials in 3 debug scripts; f-string SQL in 5 query functions; days param validation in 3 callbacks; security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy); Flask secret key; generic /health error; PROXY_URL validation; LIMIT on unbounded queries; non-root Dockerfile user; deleted google_shopping.py and 2 POC scripts
- **Deferred:** requirements.txt hash-pinning (needs pip-tools + pip-compile run); FLASK_SECRET_KEY Fly secret (manual step, noted above)
- **Next review:** 2026-06-28

### 2026-06-01 — Dependency audit (pip-audit 2.10.0)
- **Result:** No known vulnerabilities found across all packages in requirements.txt
- **Next audit:** 2026-08-01

### 2026-09-23 — Audit (health check only)
- **Findings:** 2 critical, 5 important, 2 nice-to-have
- **Top concerns:** The Walmart scraper imports src/scrapers/google_shopping.py, which was deleted, so any scrape without SCRAPERAPI_KEY and a working camoufox crashes with ModuleNotFoundError. ScraperAPI request errors embed the full request URL (including the api_key query param) in the exception text, which is logged and written to scrape_failures.error_message. Dashboard query functions raise ValueError on an empty or unreachable DB instead of rendering empty states, and HANDOFF.md has no entry since 2026-06-23 despite the August client-mode/CI work.
- **Action taken:** Audit only — no fixes this session
- **Next review:** 2026-12-22
