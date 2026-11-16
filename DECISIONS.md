# competitive-shelf-intelligence — Decisions Log

Permanent record of choices that should survive session turnover.
If a decision is reversed, strike it through and add the replacement
below — don't delete.

---

## Format

Each entry:
- **Date** — when decided
- **Decision** — one sentence, imperative voice
- **Why** — the reasoning, including what was tried and rejected
- **Scope** — what this applies to
- **Do not** — explicit anti-instructions, if any

---

## Architecture & Pipeline

### 2026-05-28 — Tier set to Heavy
- **Why:** Project has a recurring maintenance offering ($2K–$5K/month)
  and multi-retailer scraping pipeline that will be maintained >3 months.
- **Scope:** Global
- **Do not:** Downgrade to Medium without re-running gstack gates.

---

## Data & Schema

[Decisions about data sources, schemas, transformations]

---

## Scraping & Acquisition

### 2026-05-28 — Use ScraperAPI for Walmart; keep Playwright for Amazon
- **Why:** Plain Playwright (+ playwright-stealth v2) is blocked by Walmart's
  server-side fingerprinting on both data-center and default IPs. Two attempts
  failed in session 1 — status 200 redirect to `/blocked`. Walmart detects
  headless Chromium at the TLS/network layer before any JS stealth patches run.
  ScraperAPI routes through real browsers on residential IPs and is the lowest-
  friction fix that preserves our HTML parsing logic unchanged.
- **Scope:** WalmartScraper only. Amazon is less aggressive; Playwright stays.
- **Do not:** Remove the Playwright fallback from WalmartScraper — it keeps
  fixture-based tests fast without needing ScraperAPI credits.

---

## Visualization

[Chart conventions, palette decisions, interactivity choices]

---

## Output Formats

[Decisions about deliverable formats, structure, organization]

---

## Writing & Voice

[Voice, style, terminology decisions specific to this project]

### 2026-05-28 — Amazon scraper uses BeautifulSoup CSS fallback chain
- **Why:** Amazon has no stable JSON blob equivalent to Walmart's `__NEXT_DATA__`. Four price selectors tried in order (`#priceblock_ourprice` → `#priceblock_dealprice` → `.a-price .a-offscreen` → `.priceToPay .a-offscreen`) minimises single-selector fragility as Amazon rotates layouts by category and over time. BeautifulSoup with stdlib html.parser used (no lxml needed).
- **Scope:** `src/scrapers/amazon.py` only.
- **Do not:** Collapse the fallback chain to one selector — Amazon breaks individual selectors regularly.

### 2026-05-28 — Amazon OOS check order: availability span → #outOfStock → missing cart
- **Why:** `#outOfStock` element is a stronger semantic signal than cart-button absence (which can be a false positive on gift cards / digital items). Checking it before the cart-absence signal ensures `oos_signal = "oos_text"` in those cases, not `"no_cart_button"`.
- **Scope:** `AmazonScraper._detect_oos()`.

### 2026-05-28 — Entity resolution and scrape CLI tests use mock-based cursor, not live DB
- **Why:** No Postgres available in the dev/test environment. `unittest.mock` cursor with `fetchone.side_effect` provides deterministic coverage of all three entity-resolution tiers and all CLI DB paths without requiring a real connection. Integration tests against a real DB are deferred until Fly Postgres is provisioned.
- **Scope:** `tests/scrapers/test_entity_resolution.py`, `tests/test_scrape.py`.
- **Do not:** Add `psycopg2-binary` to test fixtures or try to spin up a real DB in CI — it adds fragile infrastructure for no coverage gain over well-structured mocks.

### 2026-05-28 — app/db.py duplicated from src/db.py
- **Why:** Follows `retail-velocity-decision-tool` pattern exactly — `app/` is a self-contained package at import time. Importing from `src/` in `app/run.py` at module level would create a cross-package coupling that breaks `gunicorn --module app.run:server` when the working directory isn't predictable.
- **Scope:** `app/db.py` only. Both files must be kept in sync if the pool logic ever changes.

### 2026-05-28 — Synthetic Cinderhaven history is deterministic: seeded by listing_id
- **Why:** `random.seed(listing_id)` before picking OOS/promo days means reruns always produce the same historical pattern. Idempotency via `ON CONFLICT DO NOTHING` is the DB-level guarantee; deterministic seeds are the application-level guarantee that the data looks the same after a schema wipe + reload.
- **Scope:** `scripts/load_synthetic.py` `_insert_history()`.

### 2026-05-28 — Dashboard uses dcc.Store("_refresh-trigger") as universal tab callback input
- **Why:** Dash requires all callbacks to have at least one Input. Using a single shared Store as the "page loaded" signal prevents duplicating `dcc.Interval` or `dcc.Location` wiring in every tab module, and keeps each tab module independent of layout IDs outside its own scope.
- **Scope:** All five tab `register_callbacks()` functions.

### 2026-05-28 — WalmartScraper transport priority: ScraperAPI → camoufox → Google Shopping → plain Playwright
- **Why:** ScraperAPI removed its free tier ($49/month minimum). camoufox (Firefox stealth) added as transport 2; Google Shopping requests fallback added as transport 3. Neither camoufox nor Google Shopping work from data center IPs (Fly.io, AWS, etc.) — both are still blocked at the IP layer. Plain Playwright remains as transport 4 for fixture tests only.
- **Scope:** `src/scrapers/walmart.py`
- **Do not:** Expect camoufox or Google Shopping to return real data from any hosted environment without a residential proxy. For a paying client, set `SCRAPERAPI_KEY` (transport 1 activates) or add a `PROXY_URL` residential proxy.

### 2026-05-28 — Demo uses synthetic competitor price history
- **Why:** Walmart and Amazon both block scrapes from Fly.io data center IPs at the network layer regardless of browser stealth. Rather than delay the demo, seeded 30-day price history for all 5 competitors at market-realistic prices (Competitor B $17.99/6oz, Competitor E $6.99/5oz, Competitor D $6.49/5oz, Competitor A $7.49/9.8oz, Competitor C $4.99/5oz) using `scripts/load_synthetic_competitors.py`.
- **Scope:** Demo database only. Real scraping replaces synthetic data when a client engages and a proxy key is obtained.

### 2026-05-28 — Lead-gen assets out of scope for this project
- **Why:** Explicitly removed from the optional follow-up arc. Kept as a separate concern that does not belong in this codebase.
- **Scope:** PLAN.md "Out" section.

---

### 2026-05-28 — Accept autocommit partial state as acceptable for v1
- **Why:** `get_conn()` uses `conn.autocommit = True`. Multi-step scrape writes (brand → product → listing → snapshot) each commit individually. A mid-run crash leaves earlier rows committed with no snapshot. All write operations use `ON CONFLICT DO NOTHING` / `ON CONFLICT DO UPDATE`, so retries are idempotent and the partial state resolves on the next run. Not worth adding explicit transaction management for v1.
- **Scope:** `src/db.py`, `scrape.py`. Revisit if the pipeline ever requires atomic multi-table writes.

### 2026-05-28 — Accept rate-limit-per-instance (not process-global) for v1
- **Why:** Rate limiting in `base.py` uses `self._last_request_time` (instance-level). Two concurrent scraper processes would each enforce their own minimum delay, doubling the effective request rate. Acceptable for v1 because there are no scheduled runs yet and manual runs are never concurrent. Revisit when cron scheduling is added.
- **Scope:** `src/scrapers/base.py`. Fix: use a shared file lock or named semaphore when scheduling is implemented.

### 2026-06-23 — Review Pulse uses hero/competitive grid pattern with shared modal callback
- **Why:** Cinderhaven (own brand) needs visual prominence; competitors need glanceable density. Hero card gets full width, 240px charts with legends. Competitors get 2-column grid with 160px compact charts. All cards share one pattern-matching callback (`{"type": "review-comp-card", "index": ALL}`) for the click-to-expand modal — no duplicate callback logic.
- **Scope:** `app/tabs/review_pulse.py`
- **Do not:** Add separate modal callbacks per card type. The shared pattern-matching approach scales to any number of brands.

### 2026-05-28 — Accept SSRF risk in config URL handling for v1 (internal tool)
- **Why:** URLs from `config/products.yaml` are passed to ScraperAPI and Playwright with no domain allowlist. Risk is low because `products.yaml` is a committed, reviewed file in a private repo with no external write access. A URL allowlist (restrict to `walmart.com`, `amazon.com`) is the right fix but deferred to P2+ given the internal-tool context.
- **Scope:** `scrape.py`, `src/scrapers/walmart.py`, `src/scrapers/base.py`.

### 2026-05-28 — Price Positioning tab uses horizontal bar chart, not scatter plot
- **Why:** Scatter plots require data literacy (interpreting X/Y position). Horizontal bars are immediately readable — longer bar = more expensive, no explanation needed. User preference confirmed explicitly.
- **Scope:** `app/tabs/price_positioning.py`
- **Do not:** Revert to scatter plot or dot plot without explicit user instruction.

## Reversed / Superseded

When a decision is overturned:
1. Strike through the original entry above (don't delete)
2. Add a new entry below with the replacement decision
3. Note the link in both directions
