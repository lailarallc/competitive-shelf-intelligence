"""Tests for entity_resolution.resolve_product.

All tests mock the psycopg2 connection/cursor — no live database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from src.scrapers.base import ScrapedProduct
from src.scrapers.entity_resolution import resolve_product


# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------

def _make_scraped(
    *,
    retailer: str = "walmart",
    retailer_id: str = "12345678",
    product_name: str = "Competitor A Agave 9.8 oz",
    pack_size_raw: str = "Competitor A Agave 9.8 oz",
    upc: str | None = "040000000017",
) -> ScrapedProduct:
    return ScrapedProduct(
        retailer=retailer,
        retailer_id=retailer_id,
        product_name=product_name,
        current_price=8.97,
        pack_size_raw=pack_size_raw,
        upc=upc,
    )


def _make_conn(*cursor_side_effects):
    """Build a mock connection whose cursor().fetchone() returns each value in turn."""
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(cursor_side_effects)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


# ------------------------------------------------------------------
# Tier 1: UPC exact match
# ------------------------------------------------------------------

def test_resolves_product_by_upc_when_upc_matches_existing():
    scraped = _make_scraped(upc="040000000017")
    # cursor returns: products lookup → (42,), listing upsert → (99,)
    conn, cur = _make_conn((42,), (99,))

    product_id, listing_id = resolve_product(scraped, brand_id=1, product_url="https://walmart.com/ip/1", conn=conn)

    assert product_id == 42
    assert listing_id == 99


def test_creates_new_listing_for_new_retailer_when_product_exists():
    # Same product on Amazon that already exists via Walmart UPC
    scraped = _make_scraped(retailer="amazon", retailer_id="B07ABCDEF0", upc="040000000017")
    conn, cur = _make_conn((42,), (77,))

    product_id, listing_id = resolve_product(scraped, brand_id=1, product_url="https://amazon.com/dp/B07ABCDEF0", conn=conn)

    assert product_id == 42
    assert listing_id == 77


def test_handles_null_upc_gracefully():
    # No UPC → skip Tier 1, fall through to Tier 2/3
    scraped = _make_scraped(upc=None)
    # Tier 2: no existing listing (fetchone → None), canonical map miss (fetchone → None)
    # Tier 3: product insert → (10,), listing insert → (20,)
    conn, cur = _make_conn(None, None, (10,), (20,))

    product_id, listing_id = resolve_product(scraped, brand_id=1, product_url="https://walmart.com/ip/1", conn=conn)

    assert product_id == 10
    assert listing_id == 20


# ------------------------------------------------------------------
# Tier 2: manual canonical map
# ------------------------------------------------------------------

def test_applies_manual_canonical_map_when_upc_absent():
    # No UPC; an existing retailer_listings row maps to canonical product 55
    scraped = _make_scraped(upc=None)
    # Tier 2: existing listing found → (55, 88)
    conn, cur = _make_conn((55, 88))

    product_id, listing_id = resolve_product(scraped, brand_id=1, product_url="https://walmart.com/ip/1", conn=conn)

    assert product_id == 55
    assert listing_id == 88


def test_tier2_uses_canonical_product_map_join_when_no_direct_listing():
    # No UPC, no existing listing row, but canonical_product_map has an entry
    scraped = _make_scraped(upc=None)
    # Tier 2, query 1: no direct listing (None)
    # Tier 2, query 2: canonical_product_map join → canonical_product_id = 33
    # listing upsert: → (44,)
    conn, cur = _make_conn(None, (33,), (44,))

    product_id, listing_id = resolve_product(scraped, brand_id=1, product_url="https://walmart.com/ip/1", conn=conn)

    assert product_id == 33
    assert listing_id == 44


# ------------------------------------------------------------------
# Tier 3: create new product
# ------------------------------------------------------------------

def test_creates_new_product_when_no_match_found():
    scraped = _make_scraped(upc=None)
    # Tier 2: no direct listing (None), no canonical map (None)
    # Tier 3: product upsert → (11,), listing upsert → (22,)
    conn, cur = _make_conn(None, None, (11,), (22,))

    product_id, listing_id = resolve_product(scraped, brand_id=2, product_url="https://walmart.com/ip/99", conn=conn)

    assert product_id == 11
    assert listing_id == 22


def test_new_product_insert_uses_scraped_name_and_upc():
    scraped = _make_scraped(product_name="Competitor B Original 6 oz", upc=None, pack_size_raw="Competitor B Original 6 oz")
    conn, cur = _make_conn(None, None, (5,), (6,))

    resolve_product(scraped, brand_id=3, product_url="https://walmart.com/ip/5", conn=conn)

    # The third execute call is the product INSERT
    insert_call_args = cur.execute.call_args_list[2]
    sql, params = insert_call_args[0]
    assert "INSERT INTO products" in sql
    assert params[1] == "Competitor B Original 6 oz"  # canonical_name


# ------------------------------------------------------------------
# Cross-retailer linking via UPC
# ------------------------------------------------------------------

def test_links_amazon_and_walmart_listing_to_same_canonical_product_via_upc():
    # Walmart scraped first; product_id = 7. Now Amazon scrape with same UPC.
    amazon_scraped = _make_scraped(retailer="amazon", retailer_id="B0COMPB001", upc="850012345678")
    conn, cur = _make_conn((7,), (30,))  # UPC hit → product 7, new amazon listing → 30

    product_id, listing_id = resolve_product(amazon_scraped, brand_id=1, product_url="https://amazon.com/dp/B0COMPB001", conn=conn)

    assert product_id == 7  # same canonical product as the Walmart listing
    assert listing_id == 30
