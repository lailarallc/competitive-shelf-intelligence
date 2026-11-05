# competitive-shelf-intelligence — Handoff Log

Session-by-session state. Updated by /log mid-session and /wrap at
session end.

For durable choices, see DECISIONS.md.
For the current work arc, see PLAN.md.
For things that didn't work, see FAILURES.md.

---

## 2026-05-28 — Project initialized

**Started from:** New project setup.

**Did:** Created repo, set up CLAUDE.md/DECISIONS.md/HANDOFF.md/PLAN.md/
FAILURES.md, configured slash commands. Tier: Heavy. Stack: TBD.

**State:** Foundation in place. Ready to run /clarify to scope the work,
then /office-hours, /plan-ceo-review, /plan-eng-review before building.

**Next:** Run /clarify to reach 95% confidence on scope and deliverables.

---

## 2026-05-28 — Full implementation shipped (IU-1 through IU-10)

**Started from:** Foundation in place. All 10 implementation units executed.

**Did:**
- IU-1: Postgres schema (`db/schema.sql`) — brands, products, retailer_listings, scrape_runs, price_snapshots (UNIQUE listing_id+scraped_date), canonical_product_map, scrape_failures, plus 4 SQL views (v_price_per_oz, v_promo_events, v_oos_events, v_latest_snapshot_per_product)
- IU-2: DB connection pool (`src/db.py`, `app/db.py`) — PID-aware ThreadedConnectionPool, DEC2FLOAT typecast, get_conn() context manager; app/db.py duplicated intentionally for gunicorn import safety
- IU-3: Walmart scraper (`src/scrapers/walmart.py`) — ScraperAPI transport for production (bot detection), `__NEXT_DATA__` JSON parsing, Playwright fallback for fixture-based tests
- IU-4: Amazon scraper (`src/scrapers/amazon.py`) — BeautifulSoup CSS fallback chain (4 selectors), OOS detection ordered: availability span → #outOfStock → missing cart, sale/promo detection via .a-text-strike
- IU-5: Entity resolution (`src/scrapers/entity_resolution.py`) — 3-tier: UPC exact match → canonical_product_map → new product insert; all ON CONFLICT safe
- IU-6: Scrape CLI (`scrape.py`) — Click CLI with --retailer, --delay, --dry-run; skips REPLACE_WITH_* URLs with warning; logs failures to scrape_failures table
- IU-7: Synthetic data loader (`scripts/load_synthetic.py`) — 5 Cinderhaven SKUs, median-priced against real competitors, deterministic history via random.seed(listing_id)
- IU-8: Dashboard data layer (`app/data.py`, `app/constants.py`) — Flask-Caching with FileSystemCache → SimpleCache fallback, 7 query functions over the 4 SQL views
- IU-9: Dashboard UI (`app/layout.py`, `app/tabs/`, `app/charts.py`, `app/components.py`, `app/callbacks.py`, `app/run.py`) — 5 tabs: price positioning, promo activity, OOS tracker, assortment monitor, review pulse; /health endpoint; Lailara Design System v2 throughout
- IU-10: Deployment (`Dockerfile`, `fly.toml`) — Playwright base image, tini init, gunicorn 1 worker; Fly.io config with always-on min_machines=1, 2GB RAM, /health check, cache volume mount

**Tests:** 100/100 passing. All fixture-based — no live network, no live DB.

**Notable fixes during build:**
- OOS signal order in amazon.py: `#outOfStock` must be checked before missing cart button (cart can be absent for non-physical items); fixed fixture `product_oos_element.html` to include cart button
- `CHART_PALETTE` was referenced in `review_pulse.py` but not exported from `app/constants.py` — added it
- `add_vline_at_date()` helper replaces `fig.add_vline()` to avoid pandas 3.x + plotly 6.x TypeError

**Git state:** Clean on main. All IU commits in. DECISIONS.md and PLAN.md updated with 6 new decision entries and updated checkboxes.

**What is NOT done (next session starts here):**
1. **Fill competitor URLs** — `config/products.yaml` has `REPLACE_WITH_*` for all 10 products. Research real Walmart/Amazon URLs for each brand. Once filled, un-check this item in PLAN.md.
2. **Provision Fly Postgres** — `flyctl postgres create --name competitive-shelf-pg --region iad` → attach → `psql $DATABASE_URL -f db/schema.sql`
3. **Set Fly secrets** — `flyctl secrets set SCRAPERAPI_KEY=your_key`
4. **Run first scrape** — `python scrape.py` (or `--retailer walmart` to test one first)
5. **Load synthetic data** — `python scripts/load_synthetic.py` (run after first real scrape so median is computed from real data)
6. **Deploy** — `flyctl deploy`

**Next:** Research and fill competitor product URLs in `config/products.yaml`. That is the only manual step blocking a first real scrape.

---

## 2026-05-28 — Demo deployed and live at https://competitive-shelf-intelligence.fly.dev

**Started from:** All IUs shipped, URLs filled, Fly Postgres provisioned.

**Did:**
- Provisioned Fly Postgres (`competitive-shelf-pg`), applied schema via psycopg2 proxy (no local psql)
- Filled all competitor URLs in `config/products.yaml` (Yellowbird, Truff, Melinda's, Dave's Gourmet, Marie Sharp's)
- Discovered Walmart and Amazon both block scrapes from Fly data center IPs regardless of browser type; camoufox (Firefox stealth) also blocked at the IP layer
- Implemented camoufox + Google Shopping fallback in `src/scrapers/walmart.py`; camoufox works on Linux but fails on Windows (Microsoft Store Python UWP sandboxing); Google Shopping returns JS-only shell to plain requests → both fallbacks non-functional from data center
- Scraped 1 real Yellowbird Amazon row locally (before Amazon CAPTCHA started blocking)
- Loaded 300-row Cinderhaven synthetic history (5 SKUs × 2 retailers × 30 days) via `scripts/load_synthetic.py`
- Added `scripts/load_synthetic_competitors.py` — seeds 30-day price history for all 5 competitors at market-realistic prices (Truff $17.99, Marie Sharp's $6.99, Dave's $6.49, Yellowbird $7.49, Melinda's $4.99)
- Fixed `app/data.py` `get_latest_price_per_oz()` — was querying `v_latest_snapshot_per_product` for `brand_name`/`price_per_oz` columns that don't exist on that view; query now JOINs products+brands and computes price_per_oz inline
- Fixed `app/components.py` `strftime("%-d")` → `ts.day` (Windows cross-platform)
- Fixed `scrape.py` pack_weight_oz UPDATE-before-INSERT ordering bug
- Fixed Dockerfile: removed ENTRYPOINT tini (not in playwright image), updated base from v1.49.0 to v1.60.0, pinned playwright==1.60.0 to match
- Deployed version 4 successfully; dashboard health check passing

**DB state (Fly Postgres):**
- 600 total snapshots: 300 Cinderhaven + 60 per competitor × 5 brands
- 6 brands, 20 SKU/retailer combinations, 30-day history each
- price range: Cinderhaven/Yellowbird $0.76/oz → Truff $3.04/oz

**Dashboard live at:** https://competitive-shelf-intelligence.fly.dev
- Price Positioning tab: horizontal dot chart, all 6 brands, Walmart vs Amazon
- Promo, OOS, Assortment, Review tabs: query views that work against synthetic data

**For a paying client (production-ready scraping):**
- Walmart: residential proxy service ($30-50/month) — ScraperAPI was $49/month (no free tier) <!-- label-ok: scraping-service cost for Walmart.com, not a Cinderhaven figure -->
- Amazon: residential proxy + ScraperAPI renders anti-bot headers correctly
- ScraperAPI key → set `SCRAPERAPI_KEY` in `flyctl secrets` and `src/scrapers/walmart.py` Transport 1 activates

**Next:**
- Demo is ready to show. No further work required unless a client engagement starts.
- When a client engages: obtain ScraperAPI or Bright Data residential proxy, set SCRAPERAPI_KEY secret, run `python scrape.py` on cron via `flyctl schedule` or Fly Machines scheduled tasks.

---

## 2026-05-28 — Code review complete; P1/P2 bugs queued

**Started from:** Demo live. Full 5-reviewer code review run (correctness, maintainability, testing, security, reliability).

**Did:**
- Ran 5 parallel compound-engineering review agents
- Synthesized findings into P1/P2/P3/P4 tiers
- Logged confirmed bugs to FAILURES.md, accepted-risk decisions to DECISIONS.md
- Updated PLAN.md with the next arc (fix P1+P2 bugs)

**Review summary:**

P1 — wrong behavior today (all three confirmed at 100% confidence):
- **F4** `app/data.py:152` — `get_promo_summary` SQL alias bug; Promo summary tab always empty
- **F1** `app/data.py:164` — promo depth formula inverted; negative % for synthetic data, 0% for Amazon
- **REL-001** `scrape.py:91` — no try/finally on scrape_run lifecycle; crashed run stays `'running'` forever

P2 — real bugs, lower urgency:
- **F5** `walmart.py:342` — OOS miss when `availabilityStatus` absent + no cart button
- **REL-004** `app/data.py` — all exceptions swallowed silently, no logging
- **REL-005** `base.py:185` — `check_robots()` hangs with no timeout
- **SEC-002** `entity_resolution.py:120` — f-string column name in SQL JOIN; use `psycopg2.sql.Identifier`
- **SEC-007** `app/run.py:47` — `debug=True` hardcoded; gate on `FLASK_DEBUG`

P3 — polish (separate session): CHART_PALETTE shadow, dead imports, FONT_SERIF inconsistency, OWN_BRAND constant, dead listing_id param.

Accepted risks: autocommit partial state, rate-limit per-instance, SSRF via config URLs (all documented in DECISIONS.md).

**Git state:** Clean on main. PLAN.md, FAILURES.md, DECISIONS.md updated.

**Next session starts here:** Fix P1 bugs first (`app/data.py`, `scrape.py`), then P2. All three P1 bugs are mechanical and can be done in one commit. Run tests after each fix.

---

## 2026-06-23 — Visual overhaul + data fix + final tab fixes

**Started from:** Demo live but stale (30-day data loaded 2026-05-28, now outside filter window). Dashboard unstyled vs Lailara Design System.

**Did (across two continued sessions):**

Part 1 — Data fix:
- Extended synthetic data default from 30 to 90 days in both loaders
- Added `_setup_assortment_demo()` in competitor loader — creates 2 scrape runs, Marie Sharp's delist, Secret Aardvark new entry
- Fixed promo flags: split into badge_promos (~60%) and price_drop_promos (~40%) — were all False before
- Fixed OOS flags: increased OOS count formula
- Fixed RadioItems int coercion bug (string "90" not in frozenset of ints)
- Fixed `_setup_assortment_demo()` FK violation — must delete scrape_failures before scrape_runs
- Cleared and reseeded Fly Postgres: 1,801 snapshots, 80 promos, 70 OOS events, 2 scrape runs

Part 2 — Visual overhaul (Lailara Design System v2):
- Browser tab title: "Competitive Shelf Intelligence | Lailara LLC"
- 1200px max-width container + "LAILARA LLC" eyebrow
- Custom tab nav (html.Button + dcc.Store) replacing dcc.Tabs, Chicago-20 underline
- White card wrappers for all chart areas
- Styled toggle buttons replacing RadioItems (dcc.Store pattern)
- AG Grid replacing DataTable in promo summary + assortment monitor
- ag-grid-overrides.css with Lailara tokens
- Polished empty states (dashed border + em-dash icon)
- OOS callout: white card with Red-42 left border
- Transparent chart backgrounds (blend with white cards)

Part 3 — Bug fixes found during verification:
- Price Positioning empty chart: multi-product brands (Cinderhaven 5 SKUs) caused `sub.loc[brand, col]` to return Series; fixed with `groupby(["brand_name","retailer"]).mean()`
- OOS Tracker always empty: query referenced nonexistent `v.oos_signal` column; silent except returned empty DataFrame
- Assortment Monitor "Possible Delist" truncated: rebalanced AG Grid column flex values, added minWidth 140 to Status
- Review Pulse layout overflow: rewrote to 2-column grid of brand cards with stacked compact charts (160px height, tight margins, horizontal legends)
- Review Pulse y-axis: dynamic floor (half-star below lowest data) + 0.5-star gridlines

**Tests:** 100/100 passing throughout.

**Git state:** Clean on main. 20 commits pushed to origin. Deployed as version 11 on Fly.io.

**DB state (Fly Postgres):**
- 1,801 total snapshots (Mar 26 – Jun 23, 2026)
- 7 brands (6 original + Secret Aardvark), 21 listings
- 80 promo events (badge + price-drop), 70 OOS events
- 2 scrape runs for Assortment Monitor demo

**Dashboard live at:** https://competitive.lailarallc.com
- All 5 tabs rendering with data
- Price Positioning verified visually (7 brands, Cinderhaven outlined)
- OOS, Assortment, Review Pulse verified via data queries (Chrome read-only prevented tab clicking)

**Next:** Visually verify OOS Tracker, Assortment Monitor, and Review Pulse tabs in browser (couldn't click tabs due to Chrome read-only tier). All data queries confirmed working.

---

## 2026-06-23 — Review Pulse redesign + final polish pass

**Started from:** Dashboard live at competitive.lailarallc.com. Review Pulse tab had equal-treatment 2-column grid.

**Did:**
- Rewrote Review Pulse: hero card for Cinderhaven (navy left border, "YOUR BRAND" label, two 240px charts) + 2-column competitive grid (160px compact charts, no legends)
- Built click-to-expand modal: clicking any brand card (hero or competitor) opens XL modal with 320px + 280px charts
- Removed black outline from Cinderhaven bars in Price Positioning
- Randomized promo depth from fixed 15% to 8-20% in both loaders
- Added hover modebar on compact charts
- Reseeded Fly Postgres (cleared + reloaded 1801 snapshots with randomized depths)
- Deployed 4 times

**State:** All 5 tabs rendering. 100/100 tests. 1801 snapshots in Fly Postgres. Git clean on main.

**Next:** Visually verify all tabs in browser — click Review Pulse cards to confirm modal, check Promo Activity for varied depth percentages, confirm Price Positioning outlines removed. Improvement review due 2026-06-28.

---

## 2026-06-23 — Fix Secret Aardvark single-data-point charts

**Started from:** Secret Aardvark had only 1 day of history (Assortment Monitor demo only), causing garbage Plotly axis labels.

**Did:** Moved Secret Aardvark from standalone `_NEW_ENTRY` dict into `_COMPETITORS` list for full 90-day × 2-retailer history. Updated `_setup_assortment_demo()` reference. Deployed, cleared, reseeded (1980 snapshots). Category median shifted $1.31 → $1.21 with Secret Aardvark in the pool.

**State:** All 7 brands have full 90-day history. 1980 snapshots. All tabs rendering. 100/100 tests. Deployed and pushed.

**Next:** Visually verify all tabs — Secret Aardvark charts in Review Pulse (normal date axes), Assortment Monitor still showing "New Entry." Improvement review due 2026-06-28.

---

## 2026-05-28 — All P1/P2/P3 fixes shipped; compound doc written; bar chart live

**Started from:** Code review complete. Three P1 bugs, five P2, five P3 polish items queued.

**Did:**
- Fixed all 13 P1/P2/P3 items across 15 files (committed `0993fbe`)
- Fixed `entry`-unbound bug in `scrape.py` `BlockDetectedError` handler (caught by post-compound reviewer)
- Ran `/ce-compound` → `docs/solutions/logic-errors/price-convention-mismatch-oos-guard-clause-2026-05-28.md`
- Replaced Price Positioning scatter plot with horizontal grouped bar chart (brands as rows, sorted by price, Cinderhaven outlined)

**State:** All PLAN.md arcs done. Dashboard live at https://competitive-shelf-intelligence.fly.dev. No broken code.

**Next:** Demo is ready. No further work unless a client engages. When that happens: obtain ScraperAPI key, `flyctl secrets set SCRAPERAPI_KEY=...`, run `python scrape.py`, set up cron.

---
