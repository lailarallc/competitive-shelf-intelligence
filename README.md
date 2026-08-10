# Competitive Shelf Intelligence

Competitive pricing, promo, and out-of-stock monitoring for specialty food brands — the visibility of syndicated data (IRI/Nielsen) at a fraction of the cost.

**Live:** https://competitive.lailarallc.com

## What it does

Scrapes Walmart and Amazon product pages to track price per oz, promotional activity, out-of-stock events, assortment changes, and review trends across the artisan sauce/condiment category, then serves the results in a Dash dashboard. A synthetic Cinderhaven brand (the fictional client used across the Lailara portfolio) is positioned at the real category median price so competitive gaps read at a glance.

**Scope note:** the tool monitors competitive shelf positioning using Amazon and Walmart as the competitive surface. It is not a full-catalog analysis of all Cinderhaven channels; audits should not flag the single-channel focus as data drift. Canonical Cinderhaven dataset: 50 SKUs across 5 product lines and 6 contracted retailers.

## Why it matters

Syndicated data runs tens of thousands of dollars a year and reports with weeks of lag — out of reach and out of date for most specialty brands. Daily shelf monitoring answers the questions those brands actually have: Is a competitor undercutting us on price per oz? Who is running promos this week? How much revenue are we losing to out-of-stocks? Which SKUs quietly disappeared from the shelf? Each is a pricing, promo, or supply decision worth real money.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure environment
cp .env.example .env
# Fill in DATABASE_URL and SCRAPERAPI_KEY in .env

# 3. Create the database schema
psql $DATABASE_URL -f db/schema.sql

# 4. Add competitor product URLs
# Edit config/products.yaml — replace REPLACE_WITH_* placeholders
# with real Walmart and Amazon product URLs

# 5. Run a scrape
python scrape.py                   # all retailers
python scrape.py --retailer walmart
python scrape.py --dry-run         # verify without DB writes

# 6. Load synthetic Cinderhaven data (run once after first real scrape)
python scripts/load_synthetic.py

# 7. Start the dashboard
python app/run.py                  # dev server on localhost:8050
```

Tests (fixture-based — no live network calls, no database required):

```bash
python -m pytest
```

## Adding competitors

Edit `config/products.yaml`. Each entry needs:

```yaml
- name: "Brand Name Hot Sauce 12 oz"
  brand: "Brand Name"
  retailer: walmart           # or amazon
  url: "https://www.walmart.com/ip/..."
  retailer_id: "XXXXXXXX"    # Walmart item ID or Amazon ASIN
  upc: "012345678901"        # optional — helps cross-retailer linking
```

Walmart item IDs appear in the URL after `/ip/Product-Name/`.
Amazon ASINs are the 10-character code in `/dp/XXXXXXXXXX`.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres connection string |
| `SCRAPERAPI_KEY` | Yes (production) | ScraperAPI key for Walmart scraping |
| `PROXY_URL` | No | Residential proxy URL for Amazon scraping |
| `CINDERHAVEN_DAILY_REVENUE` | No | Avg daily revenue ($) — enables lost-revenue callout in OOS tab |

Sign up for ScraperAPI at scraperapi.com — 5,000 free trial credits.

## Deployment (Fly.io)

```bash
# One-time setup
flyctl postgres create --name competitive-shelf-pg --region iad
flyctl postgres attach competitive-shelf-pg --app competitive-shelf-intelligence
psql $DATABASE_URL -f db/schema.sql
flyctl secrets set SCRAPERAPI_KEY=your_key_here

# Deploy
flyctl deploy
```

The scraper is a CLI process, not part of the gunicorn app. Run it via `flyctl ssh console`:

```bash
python scrape.py --retailer all
```

Schedule with a cron job or Fly scheduled machines once you're happy with the data quality.

## Tech stack

Python · Playwright · BeautifulSoup · Postgres · Dash · Plotly · Fly.io

## Project structure

```
scrape.py                  CLI scraper
config/products.yaml       Competitor product list (edit to add competitors)
db/schema.sql              Postgres DDL — apply once
scripts/load_synthetic.py  Seed Cinderhaven synthetic data
src/
  scrapers/
    base.py                Rate limiting, robots.txt, block detection
    walmart.py             Walmart scraper (ScraperAPI + __NEXT_DATA__ JSON)
    amazon.py              Amazon scraper (CSS fallback chain)
    entity_resolution.py   UPC -> canonical product mapping
  db.py                    DB connection pool
  utils.py                 parse_weight_oz()
app/
  run.py                   Dash entry point (gunicorn: app.run:server)
  tabs/                    One module per dashboard tab
```

## Client engagement use

The demo renders a synthetic dataset (modeled on public product pages, **not**
live-scraped competitor data — an honest banner says so on every view). To analyze
a **client's own shelf/pricing observations** in place — validated, never
committed, never deployed — use client mode (see [INPUT-SPEC.md](INPUT-SPEC.md)):

```bash
pip install -e ../engagement-template/lib      # the shared lailara_engagement scaffold
python client_mode.py --config engagement.yml --input client-data/shelf.csv \
    --out client-output [--final]
```

It computes own-brand vs competitor price per ounce by retailer and the OOS rate.
**Honest provenance is mandatory:** client mode refuses to run without an explicit,
client-attested `provenance` note (how/when the data was collected), which is
printed on the deliverable — this tool never presents data as scraped that wasn't.
Output to `client-output/` (gitignored): a branded, provenance-footed,
DRAFT-watermarked `competitive-shelf-summary.html` + `summary.json`, or a Data
Readiness Report if a required column or the provenance note is missing. The demo
app is never edited (golden-locked).

## License

MIT — see [LICENSE](LICENSE).

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.
