"""Tests for scrape.py CLI logic.

Business logic helpers are tested directly. CLI integration tests use
click.testing.CliRunner with mocked scrapers and DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from click.testing import CliRunner

from scrape import (
    _check_price_drop,
    _finish_scrape_run,
    _get_or_create_brand,
    _insert_snapshot,
    _load_config,
    _start_scrape_run,
    main,
)
from src.scrapers.base import BlockDetectedError, ParseFailureError, ScrapedProduct


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_cursor_conn(*side_effects):
    cur = MagicMock()
    cur.fetchone.side_effect = list(side_effects)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def _in_stock_product(retailer: str = "walmart", retailer_id: str = "12345") -> ScrapedProduct:
    return ScrapedProduct(
        retailer=retailer,
        retailer_id=retailer_id,
        product_name="Competitor A Agave 9.8 oz",
        current_price=8.97,
        pack_size_raw="Competitor A Agave 9.8 oz",
        upc="040000000017",
    )


# ------------------------------------------------------------------
# DB helper unit tests
# ------------------------------------------------------------------

def test_start_scrape_run_inserts_row_and_returns_id():
    conn, cur = _make_cursor_conn((42,))
    run_id = _start_scrape_run(conn, "walmart")
    assert run_id == 42
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO scrape_runs" in sql
    assert params == ("walmart",)


def test_finish_scrape_run_sets_complete_status():
    conn, cur = _make_cursor_conn()
    _finish_scrape_run(conn, run_id=1, product_count=5, failure_count=1)
    sql, params = cur.execute.call_args[0]
    assert "status = 'complete'" in sql
    assert params == (5, 1, 1)


def test_get_or_create_brand_returns_id():
    conn, cur = _make_cursor_conn((7,))
    brand_id = _get_or_create_brand(conn, "Competitor A")
    assert brand_id == 7
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO brands" in sql
    assert params == ("Competitor A",)


def test_check_price_drop_returns_true_when_price_decreased():
    conn, cur = _make_cursor_conn((1000,))  # prior price = $10.00
    result = _check_price_drop(conn, listing_id=1, current_price=8.97)
    assert result is True


def test_check_price_drop_returns_false_when_price_same_or_higher():
    conn, cur = _make_cursor_conn((897,))  # prior = $8.97
    result = _check_price_drop(conn, listing_id=1, current_price=8.97)
    assert result is False


def test_check_price_drop_returns_false_when_no_prior_snapshot():
    conn, cur = _make_cursor_conn(None)
    result = _check_price_drop(conn, listing_id=1, current_price=8.97)
    assert result is False


def test_insert_snapshot_uses_on_conflict_do_nothing():
    conn, cur = _make_cursor_conn()
    p = _in_stock_product()
    _insert_snapshot(conn, listing_id=1, run_id=5, scraped=p, price_drop_promo=False)
    sql, _ = cur.execute.call_args[0]
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql


def test_insert_snapshot_converts_price_to_cents():
    conn, cur = _make_cursor_conn()
    p = _in_stock_product()
    p.current_price = 8.97
    _insert_snapshot(conn, listing_id=1, run_id=5, scraped=p, price_drop_promo=False)
    _, params = cur.execute.call_args[0]
    # price_cents is params[3]
    assert params[3] == 897


# ------------------------------------------------------------------
# Config loader
# ------------------------------------------------------------------

def test_load_config_filters_by_retailer(tmp_path, monkeypatch):
    yaml_content = """
products:
  - name: "Product A"
    brand: "Brand A"
    retailer: walmart
    url: "https://walmart.com/ip/1"
    retailer_id: "111"
    upc: ""
  - name: "Product B"
    brand: "Brand B"
    retailer: amazon
    url: "https://amazon.com/dp/B00000001"
    retailer_id: "B00000001"
    upc: ""
"""
    config_file = tmp_path / "products.yaml"
    config_file.write_text(yaml_content)

    import scrape
    monkeypatch.setattr(scrape, "CONFIG_PATH", config_file)

    walmart_only = _load_config("walmart")
    assert len(walmart_only) == 1
    assert walmart_only[0]["retailer"] == "walmart"

    all_products = _load_config("all")
    assert len(all_products) == 2


# ------------------------------------------------------------------
# CLI integration tests (mocked scrapers + DB)
# ------------------------------------------------------------------

@patch("scrape.get_conn")
@patch("scrape.WalmartScraper")
@patch("scrape.AmazonScraper")
@patch("scrape._load_config")
def test_dry_run_inserts_nothing_to_db(mock_load, mock_amazon_cls, mock_walmart_cls, mock_get_conn):
    mock_load.return_value = [
        {"name": "P", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/1", "retailer_id": "1", "upc": ""},
    ]
    walmart_instance = MagicMock()
    walmart_instance.__enter__ = MagicMock(return_value=walmart_instance)
    walmart_instance.__exit__ = MagicMock(return_value=False)
    walmart_instance.fetch_product.return_value = _in_stock_product()
    mock_walmart_cls.return_value = walmart_instance

    runner = CliRunner()
    result = runner.invoke(main, ["--dry-run"])

    assert result.exit_code == 0
    mock_get_conn.assert_not_called()


@patch("scrape.get_conn")
@patch("scrape.WalmartScraper")
@patch("scrape.AmazonScraper")
@patch("scrape._load_config")
@patch("scrape.resolve_product", return_value=(1, 1))
@patch("scrape._get_or_create_brand", return_value=1)
@patch("scrape._check_price_drop", return_value=False)
def test_creates_scrape_run_record_at_start(
    mock_price_drop, mock_brand, mock_resolve, mock_load,
    mock_amazon_cls, mock_walmart_cls, mock_get_conn
):
    mock_load.return_value = [
        {"name": "P", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/1", "retailer_id": "1", "upc": ""},
    ]
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [(99,), None, None]  # run_id=99, snapshot insert, finish
    conn.cursor.return_value = cur
    mock_get_conn.return_value.__enter__ = MagicMock(return_value=conn)
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    walmart_instance = MagicMock()
    walmart_instance.__enter__ = MagicMock(return_value=walmart_instance)
    walmart_instance.__exit__ = MagicMock(return_value=False)
    walmart_instance.fetch_product.return_value = _in_stock_product()
    mock_walmart_cls.return_value = walmart_instance

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    # Confirm scrape_runs INSERT was called
    all_sqls = [c[0][0] for c in cur.execute.call_args_list if c[0]]
    assert any("INSERT INTO scrape_runs" in sql for sql in all_sqls)


@patch("scrape.get_conn")
@patch("scrape.WalmartScraper")
@patch("scrape.AmazonScraper")
@patch("scrape._load_config")
@patch("scrape.resolve_product", return_value=(1, 1))
@patch("scrape._get_or_create_brand", return_value=1)
@patch("scrape._check_price_drop", return_value=False)
def test_continues_after_single_product_parse_failure(
    mock_price_drop, mock_brand, mock_resolve, mock_load,
    mock_amazon_cls, mock_walmart_cls, mock_get_conn
):
    mock_load.return_value = [
        {"name": "P1", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/1", "retailer_id": "1", "upc": ""},
        {"name": "P2", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/2", "retailer_id": "2", "upc": ""},
    ]
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [(10,), None, None, None]
    conn.cursor.return_value = cur
    mock_get_conn.return_value.__enter__ = MagicMock(return_value=conn)
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    walmart_instance = MagicMock()
    walmart_instance.__enter__ = MagicMock(return_value=walmart_instance)
    walmart_instance.__exit__ = MagicMock(return_value=False)
    # First product fails, second succeeds
    walmart_instance.fetch_product.side_effect = [
        ParseFailureError("missing price"),
        _in_stock_product(retailer_id="2"),
    ]
    mock_walmart_cls.return_value = walmart_instance

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert "1 scraped" in result.output
    assert "1 failed" in result.output


@patch("scrape.get_conn")
@patch("scrape.WalmartScraper")
@patch("scrape.AmazonScraper")
@patch("scrape._load_config")
def test_stops_run_on_block_detected(
    mock_load, mock_amazon_cls, mock_walmart_cls, mock_get_conn
):
    mock_load.return_value = [
        {"name": "P1", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/1", "retailer_id": "1", "upc": ""},
        {"name": "P2", "brand": "B", "retailer": "walmart",
         "url": "https://walmart.com/ip/2", "retailer_id": "2", "upc": ""},
    ]
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [(10,), None]
    conn.cursor.return_value = cur
    mock_get_conn.return_value.__enter__ = MagicMock(return_value=conn)
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    walmart_instance = MagicMock()
    walmart_instance.__enter__ = MagicMock(return_value=walmart_instance)
    walmart_instance.__exit__ = MagicMock(return_value=False)
    walmart_instance.fetch_product.side_effect = BlockDetectedError("blocked")
    mock_walmart_cls.return_value = walmart_instance

    runner = CliRunner()
    result = runner.invoke(main, [])

    # Second product should NOT have been attempted
    assert walmart_instance.fetch_product.call_count == 1
