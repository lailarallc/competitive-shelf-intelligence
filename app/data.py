"""SQL query layer for the dashboard.

All public functions return DataFrames. Results are cached with
@cache.memoize so repeated tab switches don't re-query Postgres.

Cache is initialized in run.py via init_cache(server).
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from flask_caching import Cache
from app.constants import OWN_BRAND

cache = Cache()
logger = logging.getLogger(__name__)


def init_cache(server) -> None:
    cache_dir = os.environ.get("CACHE_DIR", "/cache")
    try:
        cache.init_app(server, config={
            "CACHE_TYPE": "FileSystemCache",
            "CACHE_DIR": cache_dir,
            "CACHE_DEFAULT_TIMEOUT": 3600,
        })
    except Exception:
        # Fall back to in-memory cache (local dev without /cache volume)
        cache.init_app(server, config={
            "CACHE_TYPE": "SimpleCache",
            "CACHE_DEFAULT_TIMEOUT": 3600,
        })


@cache.memoize(timeout=3600)
def _max_scraped_date() -> Optional[date]:
    """The most recent scraped_date present in the data.

    Date filters anchor to this, not to the wall clock. Anchoring to today
    means every window silently empties as the dataset ages: the scrape data
    ends 2026-06-23, so on 2026-07-29 a 30-day window excluded 100% of rows
    and the Promotions, Out-of-Stock and Review Trends tabs all rendered
    empty states on first load with no error.
    """
    from app.db import get_conn
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(scraped_date) FROM price_snapshots")
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        logger.exception("_max_scraped_date failed")
        return None


def _date_cutoff(days: int, anchor: Optional[date] = None) -> Optional[date]:
    """Return the earliest scraped_date to include, or None for all history.

    `anchor` is the end of the window. It defaults to the newest scraped_date
    in the data, falling back to today only when the table is empty or
    unreachable. Pass it explicitly to make the calculation testable without
    a database.
    """
    if days <= 0:
        return None
    if anchor is None:
        # Window end defaults to the newest scraped_date — never the wall clock.
        # (A live clock would silently slide every window forward each day the app
        # runs, and past-window data would vanish.) An empty dataset raises rather
        # than fabricating a today-based window.
        anchor = _max_scraped_date()
        if anchor is None:
            raise ValueError(
                "_date_cutoff: no scraped_date in the data and no explicit anchor; "
                "the window anchor is never the wall clock."
            )
    return anchor - timedelta(days=days)


# ------------------------------------------------------------------
# Shared: last scraped indicator (R15)
# ------------------------------------------------------------------

@cache.memoize(timeout=300)
def get_last_scraped() -> dict:
    """Return the most recent completed scrape run info."""
    from app.db import get_conn
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT retailer, completed_at
                FROM scrape_runs
                WHERE status = 'complete'
                ORDER BY completed_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return {"retailer": None, "completed_at": None}
            return {"retailer": row[0], "completed_at": row[1]}
    except Exception:
        logger.exception("get_last_scraped failed")
        return {"retailer": None, "completed_at": None}


# ------------------------------------------------------------------
# Price Positioning tab (R17)
# ------------------------------------------------------------------

@cache.memoize(timeout=3600)
def get_latest_price_per_oz() -> pd.DataFrame:
    """Most recent price_per_oz per listing (all retailers)."""
    from app.db import get_conn
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                SELECT
                    b.canonical_name                        AS brand_name,
                    p.canonical_name                        AS product_name,
                    v.retailer,
                    v.price_cents / 100.0                   AS current_price,
                    v.price_cents::float / p.pack_weight_oz / 100.0 AS price_per_oz,
                    v.scraped_date,
                    v.is_oos
                FROM v_latest_snapshot_per_product v
                JOIN products p ON p.id = v.product_id
                JOIN brands b ON b.id = p.brand_id
                WHERE p.pack_weight_oz IS NOT NULL
                  AND p.pack_weight_oz > 0
                ORDER BY b.canonical_name, v.retailer
                """,
                conn,
            )
    except Exception:
        logger.exception("get_latest_price_per_oz failed")
        return pd.DataFrame()


# ------------------------------------------------------------------
# Promo Activity tab (R18–R19)
# ------------------------------------------------------------------

@cache.memoize(timeout=3600)
def get_promo_events(days: int = 30) -> pd.DataFrame:
    """All promo events (badge or price-drop) within the date window."""
    from app.db import get_conn
    cutoff = _date_cutoff(days)
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                SELECT
                    v.brand_name,
                    v.product_name,
                    v.retailer,
                    v.scraped_date,
                    v.has_promo_badge,
                    v.price_drop_promo,
                    v.price_cents / 100.0              AS current_price,
                    v.sale_price_cents / 100.0         AS sale_price
                FROM v_promo_events v
                WHERE (v.has_promo_badge OR v.price_drop_promo)
                  AND (%s::date IS NULL OR v.scraped_date >= %s)
                ORDER BY v.brand_name, v.scraped_date
                LIMIT 10000
                """,
                conn,
                params=[cutoff, cutoff],
            )
    except Exception:
        logger.exception("get_promo_events failed")
        return pd.DataFrame()


@cache.memoize(timeout=3600)
def get_promo_summary(days: int = 30) -> pd.DataFrame:
    """Aggregate promo event count and avg depth per brand/retailer."""
    from app.db import get_conn
    cutoff = _date_cutoff(days)
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                SELECT
                    b.canonical_name                AS brand_name,
                    rl.retailer,
                    COUNT(*)                        AS promo_events,
                    AVG(
                        CASE
                        WHEN ps.sale_price_cents IS NOT NULL AND ps.sale_price_cents > 0
                        THEN (ps.price_cents - ps.sale_price_cents)::float / ps.price_cents * 100.0
                        END
                    )                               AS avg_promo_depth_pct
                FROM price_snapshots ps
                JOIN retailer_listings rl ON rl.id = ps.listing_id
                JOIN products p ON p.id = rl.product_id
                JOIN brands b ON b.id = p.brand_id
                WHERE (ps.has_promo_badge OR ps.price_drop_promo)
                  AND (%s::date IS NULL OR ps.scraped_date >= %s)
                GROUP BY b.canonical_name, rl.retailer
                ORDER BY promo_events DESC
                """,
                conn,
                params=[cutoff, cutoff],
            )
    except Exception:
        logger.exception("get_promo_summary failed")
        return pd.DataFrame()


# ------------------------------------------------------------------
# OOS Tracker tab (R20–R21)
# ------------------------------------------------------------------

@cache.memoize(timeout=3600)
def get_oos_events(days: int = 30) -> pd.DataFrame:
    """All OOS events within the date window."""
    from app.db import get_conn
    cutoff = _date_cutoff(days)
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                SELECT
                    v.brand_name,
                    v.product_name,
                    v.retailer,
                    v.scraped_date
                FROM v_oos_events v
                WHERE v.is_oos = TRUE
                  AND (%s::date IS NULL OR v.scraped_date >= %s)
                ORDER BY v.brand_name, v.scraped_date
                LIMIT 10000
                """,
                conn,
                params=[cutoff, cutoff],
            )
    except Exception:
        logger.exception("get_oos_events failed")
        return pd.DataFrame()


@cache.memoize(timeout=3600)
def get_cinderhaven_oos_exposure(days: int = 30) -> dict:
    """Own-brand OOS exposure, prorated by SKU share.

    A single-SKU stockout costs only that SKU's share of daily brand revenue,
    not a full day of whole-brand revenue. Returns:
      - oos_days: distinct calendar days with at least one own-brand listing OOS.
      - sku_day_fraction: summed over the window, (own-brand listings OOS that
        day / total own-brand listings). Multiply daily brand revenue by this to
        estimate lost revenue instead of charging a whole day per single-SKU OOS.
    """
    from app.db import get_conn
    cutoff = _date_cutoff(days)
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                WITH own AS (
                    SELECT ps.scraped_date, ps.listing_id, ps.is_oos
                    FROM price_snapshots ps
                    JOIN retailer_listings rl ON rl.id = ps.listing_id
                    JOIN products p ON p.id = rl.product_id
                    JOIN brands b ON b.id = p.brand_id
                    WHERE b.canonical_name = %s
                      AND (%s::date IS NULL OR ps.scraped_date >= %s)
                )
                SELECT
                    COUNT(DISTINCT CASE WHEN is_oos THEN scraped_date END) AS oos_days,
                    COALESCE(
                        SUM(CASE WHEN is_oos THEN 1.0 ELSE 0 END)
                        / NULLIF(COUNT(DISTINCT listing_id), 0),
                        0
                    ) AS sku_day_fraction
                FROM own
                """,
                [OWN_BRAND, cutoff, cutoff],
            )
            row = cur.fetchone()
            if not row:
                return {"oos_days": 0, "sku_day_fraction": 0.0}
            return {"oos_days": int(row[0] or 0), "sku_day_fraction": float(row[1] or 0.0)}
    except Exception:
        logger.exception("get_cinderhaven_oos_exposure failed")
        return {"oos_days": 0, "sku_day_fraction": 0.0}


# ------------------------------------------------------------------
# Assortment Monitor tab (R22)
# ------------------------------------------------------------------

@cache.memoize(timeout=3600)
def get_assortment_changes() -> pd.DataFrame:
    """Products new or absent comparing latest vs prior scrape run."""
    from app.db import get_conn
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                WITH runs AS (
                    SELECT id, started_at,
                           ROW_NUMBER() OVER (ORDER BY started_at DESC) AS rn
                    FROM scrape_runs
                    WHERE status = 'complete'
                ),
                latest_run  AS (SELECT id FROM runs WHERE rn = 1),
                prior_run   AS (SELECT id FROM runs WHERE rn = 2),
                latest_listings AS (
                    SELECT DISTINCT ps.listing_id
                    FROM price_snapshots ps
                    WHERE ps.scrape_run_id = (SELECT id FROM latest_run)
                ),
                prior_listings AS (
                    SELECT DISTINCT ps.listing_id
                    FROM price_snapshots ps
                    WHERE ps.scrape_run_id = (SELECT id FROM prior_run)
                )
                SELECT
                    b.canonical_name    AS brand_name,
                    p.canonical_name    AS product_name,
                    rl.retailer,
                    rl.first_seen_at,
                    rl.last_seen_at,
                    CASE
                        WHEN ll.listing_id IS NOT NULL AND pl.listing_id IS NULL
                            THEN 'New Entry'
                        WHEN ll.listing_id IS NULL AND pl.listing_id IS NOT NULL
                            THEN 'Possible Delist'
                    END AS status
                FROM retailer_listings rl
                JOIN products p ON p.id = rl.product_id
                JOIN brands b ON b.id = p.brand_id
                LEFT JOIN latest_listings ll ON ll.listing_id = rl.id
                LEFT JOIN prior_listings  pl ON pl.listing_id = rl.id
                WHERE (ll.listing_id IS NULL) != (pl.listing_id IS NULL)
                ORDER BY status, b.canonical_name
                """,
                conn,
            )
    except Exception:
        logger.exception("get_assortment_changes failed")
        return pd.DataFrame()


# ------------------------------------------------------------------
# Review Pulse tab (R23)
# ------------------------------------------------------------------

@cache.memoize(timeout=3600)
def get_review_trends(days: int = 30) -> pd.DataFrame:
    """Star rating and review count per brand per date."""
    from app.db import get_conn
    cutoff = _date_cutoff(days)
    try:
        with get_conn() as conn:
            return pd.read_sql(
                """
                SELECT
                    b.canonical_name    AS brand_name,
                    rl.retailer,
                    ps.scraped_date,
                    AVG(ps.star_rating) AS avg_star_rating,
                    MAX(ps.review_count) AS max_review_count
                FROM price_snapshots ps
                JOIN retailer_listings rl ON rl.id = ps.listing_id
                JOIN products p ON p.id = rl.product_id
                JOIN brands b ON b.id = p.brand_id
                WHERE ps.star_rating IS NOT NULL
                  AND (%s::date IS NULL OR ps.scraped_date >= %s)
                GROUP BY b.canonical_name, rl.retailer, ps.scraped_date
                ORDER BY b.canonical_name, ps.scraped_date
                LIMIT 10000
                """,
                conn,
                params=[cutoff, cutoff],
            )
    except Exception:
        logger.exception("get_review_trends failed")
        return pd.DataFrame()
