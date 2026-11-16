# competitive-shelf-intelligence — Failure Log

What was attempted that didn't work, why it didn't work, and what was
tried next.

Lower bar than DECISIONS.md — capture failures even when they didn't
produce a durable rule.

---

## Format

### YYYY-MM-DD — [One-line failure description]

**Attempted:** [What was tried]

**Why it didn't work:** [Concrete reason]

**What we tried instead:** [The next attempt]

**Status:** Resolved / open / abandoned

**Tags:** [keywords for future text-search]

---

## Entries

### 2026-05-28 — Plain Playwright blocked by Walmart server-side bot detection

**Attempted:** Two approaches in session 1:
1. playwright-stealth v2 + custom "ShelfIntelligenceBot" user-agent
2. playwright-stealth v2 + native Chromium user-agent, stealth applied at
   both context and page level, locale + timezone set to US

**Why it didn't work:** Walmart redirects to `walmart.com/blocked` with HTTP
200 before any JavaScript runs. Detection occurs at the TLS fingerprint /
network layer — possibly based on data-center IP range, TLS cipher ordering,
or HTTP/2 fingerprint. playwright-stealth patches client-side JS signals only
and cannot affect network-layer fingerprinting.

**What we tried instead:** ScraperAPI rendering endpoint
(`api.scraperapi.com/?render=true`). Routes through real browsers on residential
IPs, transparent to our HTML parsing code.

**Status:** Resolved — WalmartScraper uses ScraperAPI when SCRAPERAPI_KEY is set.

**Tags:** walmart, playwright, bot-detection, scraperapi, anti-bot

---

### 2026-05-28 — `get_promo_summary` Promo Activity summary always empty (SQL alias bug)

**Attempted:** Dashboard Promo Activity tab renders summary panel.

**Why it didn't work:** `get_promo_summary` in `app/data.py:152` constructs `WHERE (v.has_promo_badge OR v.price_drop_promo)` but the FROM clause aliases the table as `ps` (`FROM price_snapshots ps`), not `v`. Postgres raises `ERROR: missing FROM-clause entry for table "v"`, which the bare `except Exception` at line 179 swallows silently. Every request returns an empty DataFrame and the summary panel shows nothing.

**What we tried instead:** Fix is pending (next session). Rename `v.` → `ps.` in the WHERE clause.

**Status:** Confirmed bug, fix queued (PLAN.md P1/F4).

**Tags:** dashboard, promo, sql, alias, silent-failure

---

### 2026-05-28 — Promo depth formula inverted; produces negative values for synthetic data

**Attempted:** Promo Activity tab promo depth percentage.

**Why it didn't work:** Formula in `app/data.py:164` is `(sale_price_cents - price_cents) / sale_price_cents`. For synthetic data where `sale_price_cents = price * 0.85` (the discounted price, less than `price_cents`), the numerator is negative, producing a negative depth percentage. For Amazon rows, the scraper sets `sale_price` equal to `current_price`, making the numerator zero and depth always 0%.

**What we tried instead:** Fix is pending. Correct formula is `(price_cents - sale_price_cents) / price_cents * 100`.

**Status:** Confirmed bug, fix queued (PLAN.md P1/F1).

**Tags:** dashboard, promo, formula, data-quality

---

### 2026-05-28 — scrape_run row stays permanently `'running'` when scraper crashes

**Attempted:** Reliable scrape run lifecycle tracking.

**Why it didn't work:** `scrape.py:91–94` calls `_start_scrape_run()`, `_run_scrape()`, `_finish_scrape_run()` in a flat sequence with no try/finally. Any unhandled exception (OOM, DB error, KeyboardInterrupt) bypasses `_finish_scrape_run()`. The `scrape_runs` row stays in `status='running'` permanently. Dashboard `get_last_scraped()` and `get_assortment_changes()` both filter on `status='complete'` and silently ignore stuck runs.

**What we tried instead:** Fix is pending. Wrap `_run_scrape` call in try/finally that marks the run `'failed'` on any exception before re-raising.

**Status:** Confirmed bug, fix queued (PLAN.md P1/REL-001).

**Tags:** scraper, reliability, scrape-run, lifecycle

---

### 2026-05-28 — camoufox (Firefox stealth) blocked by Walmart from Fly.io data center

**Attempted:** camoufox v0.4.11 with `os="windows"`, `block_webrtc=True`, `headless=True` launched from Fly.io machine (IAD region, data center IP).

**Why it didn't work:** Walmart bot detection operates at the IP layer — data center IP ranges are blocked before any HTTP or browser fingerprint is evaluated. camoufox patches browser-layer signals (JS navigator, WebGL, canvas) but cannot change the source IP. All scraped pages returned `walmart.com/blocked`.

**What we tried instead:** Google Shopping price fallback (transport 3). Also non-functional — see next entry.

**Status:** Partially resolved — camoufox works from residential IPs (laptops, home machines). For Fly.io, set `SCRAPERAPI_KEY` (residential proxy routing) or `PROXY_URL` (BrightData / Oxylabs residential proxy URL).

**Tags:** walmart, camoufox, firefox, bot-detection, fly-io, data-center-ip

---

### 2026-05-28 — Google Shopping returns JS-only shell to plain requests

**Attempted:** `requests.get("https://www.google.com/search?q=site:walmart.com+...&tbm=shop")` with realistic Chrome headers to extract Walmart prices from Google Shopping results.

**Why it didn't work:** Google returns a `<noscript>` redirect page (`/sorry/...`) when JavaScript is not executed. The full Shopping results require JS rendering. HTML response contained no product prices.

**What we tried instead:** Added as transport 3 in `WalmartScraper` for fallback visibility, but marked non-functional from server environments. For the demo, seeded synthetic competitor data instead.

**Status:** Abandoned for production. Would require Playwright or ScraperAPI rendering to work.

**Tags:** walmart, google-shopping, requests, javascript, bot-detection

---

### 2026-05-28 — Amazon scraping blocked from Fly.io data center immediately

**Attempted:** `python scrape.py --retailer amazon` on Fly.io machine (IAD data center IP).

**Why it didn't work:** Amazon returned CAPTCHA/access-denied on the first request to Competitor B's ASIN URL. Scraper correctly raised `BlockDetectedError` and halted the run (0 scraped, 1 failed). Same IP-layer block as Walmart — data center ranges are flagged before any browser fingerprint evaluation.

**What we tried instead:** No alternative transport for Amazon yet. Real Amazon scraping requires ScraperAPI (`SCRAPERAPI_KEY`) or a residential proxy.

**Status:** Open. Set `SCRAPERAPI_KEY` to resolve.

**Tags:** amazon, bot-detection, captcha, fly-io, data-center-ip

---

### 2026-05-28 — camoufox binary invisible to subprocesses on Windows Microsoft Store Python

**Attempted:** `python -m camoufox fetch` successfully downloaded the Firefox binary under Microsoft Store Python 3.13. `os.path.exists()` returned True. But when camoufox launched via `Camoufox(headless=True)`, Playwright's subprocess could not find the binary at the same path.

**Why it didn't work:** Microsoft Store Python uses UWP filesystem virtualization — the binary was written to a virtualized AppData path visible only to the parent Python process. Subprocesses (including Playwright's browser launcher) resolve to the real path, which has no file. `Test-Path` in PowerShell also returned False (sees the real path), confirming the virtual/real split.

**What we tried instead:** Accepted the fallback to Google Shopping on Windows. camoufox works correctly on Linux/Fly.io when installed via non-UWP Python.

**Status:** Windows-only limitation. Use system Python (not Microsoft Store) or WSL if camoufox is needed locally.

**Tags:** camoufox, windows, uwp, microsoft-store-python, filesystem-virtualization, playwright

---

### 2026-05-28 — Playwright version mismatch in Docker (base image v1.49 vs pip v1.60)

**Attempted:** Dockerfile used `mcr.microsoft.com/playwright/python:v1.49.0-noble` base image but `requirements.txt` allowed `playwright>=1.49,<2.0` which resolved to 1.60.0 at build time.

**Why it didn't work:** On first start, Playwright reported: `Executable doesn't exist at /ms-playwright/chromium_headless_shell-1223/... — current: v1.49.0-noble, required: v1.60.0-noble`. The pip package version and the base image version must match exactly.

**What we tried instead:** Updated Dockerfile to `FROM mcr.microsoft.com/playwright/python:v1.60.0-noble` and pinned `playwright==1.60.0` in requirements.txt. Deploy succeeded.

**Status:** Resolved. Always pin `playwright==X.Y.Z` to match the base image tag exactly.

**Tags:** playwright, docker, version-mismatch, dockerfile, fly-io

---

### 2026-05-28 — ce-sessions discovery script fails on Windows (`python3` not found + cp1252 encoding)

**Attempted:** Running `/ce-compound` with session history enabled — the ce-sessions skill invokes `python3 scripts/extract-metadata.py` and `python3 scripts/extract-skeleton.py`.

**Why it didn't work:** Windows does not alias `python3`; the command returned "No such file or directory." After switching to `python`, the skeleton extractor hit a `UnicodeEncodeError` because the session file contained characters outside the `cp1252` Windows code page (default encoding for Python on Windows).

**What we tried instead:** Prefixed the command with `PYTHONUTF8=1` to force UTF-8. Both scripts completed successfully after that.

**Status:** Resolved. On Windows, use `python` (not `python3`) and prefix with `PYTHONUTF8=1` when running ce-compound session scripts.

**Tags:** windows, encoding, cp1252, utf8, ce-sessions, ce-compound, python3

---

### 2026-06-23 — Reseed wrote 0 rows due to ON CONFLICT DO NOTHING on existing data

**Attempted:** Ran both loaders on Fly after changing promo depth from fixed 0.85 to random.uniform(0.80, 0.92). Expected new randomized values.

**Why it didn't work:** Existing snapshots (from previous seed) matched on `(listing_id, scraped_date)` UNIQUE constraint. ON CONFLICT DO NOTHING silently skipped all 1801 rows. The old fixed-15% data persisted unchanged.

**What we tried instead:** DELETE FROM price_snapshots first, then re-run loaders (competitors before Cinderhaven — Cinderhaven loader needs competitor data for median calculation).

**Status:** Resolved. When changing snapshot generation logic, clear old data before reseeding.

**Tags:** reseed, on-conflict, synthetic-data, promo-depth

---

### 2026-06-23 — Deploy must precede reseed when loader logic changes

**Attempted:** Reseeded Fly Postgres before deploying the new randomized promo depth code.

**Why it didn't work:** The running Fly machine still had the old code with `round(price * 0.85)`. SSH runs scripts from the deployed `/app` directory, not local. First reseed used old fixed-15% logic.

**What we tried instead:** Deploy first, then reseed. The deployed code at `/app` now has `random.uniform(0.80, 0.92)`.

**Status:** Resolved. Always deploy code changes before reseeding via SSH.

**Tags:** fly-io, deploy-order, reseed, ssh
