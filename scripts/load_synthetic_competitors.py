"""
Load synthetic competitor price history for six fictional brands, Competitor A to Competitor F.

The brands, product names, listing IDs and URLs are invented; competitors are always anonymized in Lailara output
(naming rule). Base prices are modelled on public shelf prices for the category. Nothing here was scraped.
Idempotent: safe to re-run; uses ON CONFLICT DO NOTHING for snapshots.

Usage:
    python scripts/load_synthetic_competitors.py
    python scripts/load_synthetic_competitors.py --days 60
    python scripts/load_synthetic_competitors.py --dry-run
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta

import click
from dotenv import load_dotenv

load_dotenv()

from src.db import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Fictional competitors. Base prices modelled on public category shelf prices, May 2026 (Amazon/Walmart parity).
# Listing IDs and URLs are invented and resolve nowhere: the synthetic: scheme marks them.
_COMPETITORS = [
    {
        "brand": "Competitor A",
        "name": "Competitor A Agave Sriracha Hot Sauce 9.8 oz",
        "weight_oz": 9.8,
        "walmart_id": "CSI-WM-A",
        "walmart_url": "synthetic:walmart/CSI-WM-A",
        "amazon_id": "CSI-AZ-A",
        "amazon_url": "synthetic:amazon/CSI-AZ-A",
        "base_price_cents": 749,
        "upc": "",
        "skip_today": False,
    },
    {
        "brand": "Competitor B",
        "name": "Competitor B Black Truffle Hot Sauce 6 oz",
        "weight_oz": 6.0,
        "walmart_id": "CSI-WM-B",
        "walmart_url": "synthetic:walmart/CSI-WM-B",
        "amazon_id": "CSI-AZ-B",
        "amazon_url": "synthetic:amazon/CSI-AZ-B",
        "base_price_cents": 1799,
        "upc": "",
        "skip_today": False,
    },
    {
        "brand": "Competitor C",
        "name": "Competitor C Habanero Hot Sauce 5 oz",
        "weight_oz": 5.0,
        "walmart_id": "CSI-WM-C",
        "walmart_url": "synthetic:walmart/CSI-WM-C",
        "amazon_id": "CSI-AZ-C",
        "amazon_url": "synthetic:amazon/CSI-AZ-C",
        "base_price_cents": 499,
        "upc": "",
        "skip_today": False,
    },
    {
        "brand": "Competitor D",
        "name": "Competitor D Extra Hot Sauce 5 oz",
        "weight_oz": 5.0,
        "walmart_id": "CSI-WM-D",
        "walmart_url": "synthetic:walmart/CSI-WM-D",
        "amazon_id": "CSI-AZ-D",
        "amazon_url": "synthetic:amazon/CSI-AZ-D",
        "base_price_cents": 649,
        "upc": "",
        "skip_today": False,
    },
    {
        "brand": "Competitor E",
        "name": "Competitor E Habanero Pepper Sauce 5 oz",
        "weight_oz": 5.0,
        "walmart_id": "CSI-WM-E",
        "walmart_url": "synthetic:walmart/CSI-WM-E",
        "amazon_id": "CSI-AZ-E",
        "amazon_url": "synthetic:amazon/CSI-AZ-E",
        "base_price_cents": 699,
        "upc": "",
        "skip_today": False,
    },
    {
        "brand": "Competitor F",
        "name": "Competitor F Habanero Hot Sauce 8 oz",
        "weight_oz": 8.0,
        "walmart_id": "CSI-WM-F",
        "walmart_url": "synthetic:walmart/CSI-WM-F",
        "amazon_id": "CSI-AZ-F",
        "amazon_url": "synthetic:amazon/CSI-AZ-F",
        "base_price_cents": 899,
        "upc": "",
        "skip_today": False,
    },
]

_DELIST_WALMART_ID = "CSI-WM-E"  # Competitor E's Walmart listing


@click.command()
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--days", default=90, show_default=True)
def main(dry_run: bool, days: int) -> None:
    """Seed synthetic competitor price history."""
    if dry_run:
        click.echo("DRY RUN — no writes")
        for c in _COMPETITORS:
            click.echo(
                f"  {c['brand']}: {c['name']} "
                f"${c['base_price_cents']/100:.2f} × {days}d × 2 retailers"
            )
        return

    total_snapshots = 0
    with get_conn() as conn:
        for comp in _COMPETITORS:
            brand_id = _upsert_brand(conn, comp["brand"])
            product_id = _upsert_product(conn, brand_id, comp)
            for retailer, rid, url in [
                ("walmart", comp["walmart_id"], comp["walmart_url"]),
                ("amazon",  comp["amazon_id"],  comp["amazon_url"]),
            ]:
                listing_id = _upsert_listing(conn, product_id, retailer, rid, url)
                n = _insert_history(
                    conn,
                    listing_id,
                    comp["base_price_cents"],
                    days,
                    skip_today=(comp["skip_today"] and retailer == "amazon"),
                )
                total_snapshots += n
                logger.info(
                    "%-20s %-8s  $%.2f  %d days",
                    comp["brand"], retailer, comp["base_price_cents"] / 100, days,
                )

        _setup_assortment_demo(conn)

    click.echo(f"Done. {total_snapshots} snapshots written.")


def _upsert_brand(conn, name: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO brands (canonical_name) VALUES (%s) "
        "ON CONFLICT (canonical_name) DO UPDATE SET canonical_name = EXCLUDED.canonical_name "
        "RETURNING id",
        (name,),
    )
    return cur.fetchone()[0]


def _upsert_product(conn, brand_id: int, comp: dict) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (brand_id, canonical_name, pack_size_raw, pack_weight_oz, upc) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (brand_id, canonical_name) "
        "DO UPDATE SET pack_weight_oz = EXCLUDED.pack_weight_oz "
        "RETURNING id",
        (brand_id, comp["name"], comp["name"], comp["weight_oz"], comp["upc"] or None),
    )
    return cur.fetchone()[0]


def _upsert_listing(conn, product_id: int, retailer: str, rid: str, url: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO retailer_listings (product_id, retailer, retailer_id, product_url) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (retailer, retailer_id) DO UPDATE SET last_seen_at = now() "
        "RETURNING id",
        (product_id, retailer, rid, url),
    )
    return cur.fetchone()[0]


def _insert_history(
    conn, listing_id: int, base_price_cents: int, days: int, skip_today: bool
) -> int:
    today = date.today()
    random.seed(listing_id + days)

    oos_count = max(2, round(days * 3 / 90))
    promo_count = max(2, round(days * 4 / 90))

    all_days = [today - timedelta(days=i) for i in range(days)]
    if skip_today:
        all_days = [d for d in all_days if d != today]

    oos_days = set(random.sample(all_days, min(oos_count, len(all_days))))
    non_oos = [d for d in all_days if d not in oos_days]
    promo_days = set(random.sample(non_oos, min(promo_count, len(non_oos))))
    promo_list = sorted(promo_days)
    badge_promos = set(promo_list[: len(promo_list) * 3 // 5])
    price_drop_promos = promo_days - badge_promos

    cur = conn.cursor()
    inserted = 0
    for day in reversed(all_days):
        is_oos = day in oos_days
        is_promo = day in promo_days
        has_badge = day in badge_promos
        is_price_drop = day in price_drop_promos
        jitter = random.uniform(0.97, 1.03)
        price = round(base_price_cents * jitter)
        sale_price = round(price * random.uniform(0.80, 0.92)) if is_promo else None

        cur.execute(
            """
            INSERT INTO price_snapshots (
                listing_id, scraped_at, scraped_date,
                price_cents, sale_price_cents,
                has_promo_badge, price_drop_promo,
                is_oos, oos_signal,
                star_rating, review_count
            ) VALUES (
                %s, %s AT TIME ZONE 'UTC', %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (listing_id, scraped_date) DO NOTHING
            """,
            (
                listing_id,
                datetime.combine(day, datetime.min.time()),
                day,
                price, sale_price,
                has_badge, is_price_drop,
                is_oos, "oos_text" if is_oos else None,
                round(random.uniform(4.0, 4.9), 1),
                random.randint(30, 2000),
            ),
        )
        if cur.rowcount:
            inserted += 1
    return inserted


def _setup_assortment_demo(conn) -> None:
    """Create 2 scrape_runs so Assortment Monitor has data to compare."""
    today = date.today()
    prior_date = today - timedelta(days=7)
    cur = conn.cursor()

    cur.execute("UPDATE price_snapshots SET scrape_run_id = NULL WHERE scrape_run_id IS NOT NULL")
    cur.execute("DELETE FROM scrape_failures")
    cur.execute("DELETE FROM scrape_runs")

    cur.execute(
        "INSERT INTO scrape_runs (retailer, started_at, completed_at, status, product_count) "
        "VALUES ('all', %s, %s, 'complete', 20) RETURNING id",
        (datetime.combine(prior_date, datetime.min.time()),
         datetime.combine(prior_date, datetime.min.time())),
    )
    prior_run_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO scrape_runs (retailer, started_at, completed_at, status, product_count) "
        "VALUES ('all', %s, %s, 'complete', 20) RETURNING id",
        (datetime.combine(today, datetime.min.time()),
         datetime.combine(today, datetime.min.time())),
    )
    latest_run_id = cur.fetchone()[0]

    cur.execute(
        "SELECT id FROM retailer_listings WHERE retailer = 'walmart' AND retailer_id = %s",
        (_DELIST_WALMART_ID,),
    )
    row = cur.fetchone()
    delist_listing_id = row[0] if row else None

    cur.execute(
        "UPDATE price_snapshots SET scrape_run_id = %s WHERE scraped_date = %s",
        (prior_run_id, prior_date),
    )

    if delist_listing_id:
        cur.execute(
            "UPDATE price_snapshots SET scrape_run_id = %s "
            "WHERE scraped_date = %s AND listing_id != %s",
            (latest_run_id, today, delist_listing_id),
        )
    else:
        cur.execute(
            "UPDATE price_snapshots SET scrape_run_id = %s WHERE scraped_date = %s",
            (latest_run_id, today),
        )

    ne = next(c for c in _COMPETITORS if c["brand"] == "Competitor F")
    brand_id = _upsert_brand(conn, ne["brand"])
    product_id = _upsert_product(conn, brand_id, ne)
    listing_id = _upsert_listing(conn, product_id, "walmart", ne["walmart_id"], ne["walmart_url"])
    cur.execute(
        """
        INSERT INTO price_snapshots (
            listing_id, scrape_run_id, scraped_at, scraped_date,
            price_cents, sale_price_cents,
            has_promo_badge, price_drop_promo,
            is_oos, oos_signal, star_rating, review_count
        ) VALUES (
            %s, %s, %s AT TIME ZONE 'UTC', %s,
            %s, NULL, FALSE, FALSE, FALSE, NULL, 4.5, 120
        )
        ON CONFLICT (listing_id, scraped_date) DO UPDATE
            SET scrape_run_id = EXCLUDED.scrape_run_id
        """,
        (listing_id, latest_run_id,
         datetime.combine(today, datetime.min.time()), today,
         ne["base_price_cents"]),
    )
    logger.info("Assortment demo: prior_run=%d, latest_run=%d", prior_run_id, latest_run_id)
    if delist_listing_id:
        logger.info("Possible delist: listing_id=%d (Competitor E Walmart)", delist_listing_id)
    logger.info("New entry: %s", ne["name"])


if __name__ == "__main__":
    main()
