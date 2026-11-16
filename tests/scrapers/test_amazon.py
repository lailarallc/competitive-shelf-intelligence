"""Fixture-based tests for AmazonScraper. No live network calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.scrapers.amazon import AmazonScraper
from src.scrapers.base import ParseFailureError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "amazon"

_URL_TEMPLATE = "https://www.amazon.com/dp/{asin}"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


@pytest.fixture
def scraper():
    return AmazonScraper()


# ------------------------------------------------------------------
# Price extraction
# ------------------------------------------------------------------

def test_extracts_price_from_primary_selector(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.current_price == pytest.approx(8.97)


def test_extracts_price_from_fallback_selector_when_primary_absent(scraper):
    # product_on_sale.html has .a-price .a-offscreen but no #priceblock_ourprice.
    # The now/sale price ($17.88) comes from .a-price .a-offscreen and is stored
    # as sale_price; the struck-through was-price ($21.99) becomes current_price.
    html = _load("product_on_sale.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B08XXXXXXX2"), "B08XXXXXXX2")
    assert p.sale_price == pytest.approx(17.88)
    assert p.current_price == pytest.approx(21.99)


def test_extracts_price_from_third_fallback(scraper):
    # product_fallback_price.html has .a-price .a-offscreen only
    html = _load("product_fallback_price.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B09XXXXXXX3"), "B09XXXXXXX3")
    assert p.current_price == pytest.approx(9.47)


def test_extracts_price_from_pricetopay_selector(scraper):
    html = _load("product_pricetopay.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B09XXXXXXX4"), "B09XXXXXXX4")
    assert p.current_price == pytest.approx(14.97)


def test_raises_parse_failure_when_no_price_selector_matches(scraper):
    html = _load("product_missing_price.html")
    with pytest.raises(ParseFailureError, match="No price selector matched"):
        scraper.parse_html(html, _URL_TEMPLATE.format(asin="B00XXXXXXX5"), "B00XXXXXXX5")


# ------------------------------------------------------------------
# Sale / promo detection
# ------------------------------------------------------------------

def test_detects_sale_when_strikethrough_price_present(scraper):
    html = _load("product_on_sale.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B08XXXXXXX2"), "B08XXXXXXX2")
    assert p.has_promo_badge is True
    assert p.current_price == pytest.approx(21.99)  # regular / was
    assert p.sale_price == pytest.approx(17.88)     # promotional / now
    # Promo depth = (regular - sale) / regular must be positive and sensible
    depth = (p.current_price - p.sale_price) / p.current_price * 100
    assert depth == pytest.approx(18.69, abs=0.1)


def test_no_promo_when_no_strikethrough(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.has_promo_badge is False
    assert p.sale_price is None


# ------------------------------------------------------------------
# OOS detection
# ------------------------------------------------------------------

def test_flags_oos_when_availability_text_says_out_of_stock(scraper):
    html = _load("product_oos_availability.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXXA"), "B07XXXXXXXA")
    assert p.is_oos is True
    assert p.oos_signal == "oos_text"


def test_flags_oos_when_add_to_cart_button_absent(scraper):
    html = _load("product_oos_no_cart.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXXB"), "B07XXXXXXXB")
    assert p.is_oos is True
    assert p.oos_signal == "no_cart_button"


def test_flags_oos_when_out_of_stock_element_present(scraper):
    html = _load("product_oos_element.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXXC"), "B07XXXXXXXC")
    assert p.is_oos is True
    assert p.oos_signal == "oos_text"


def test_not_oos_when_in_stock(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.is_oos is False
    assert p.oos_signal is None


# ------------------------------------------------------------------
# Ratings
# ------------------------------------------------------------------

def test_extracts_star_rating_correctly(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.star_rating == pytest.approx(4.6)


def test_extracts_review_count_strips_non_numeric(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.review_count == 1247


# ------------------------------------------------------------------
# Pack size / weight (raw string stored; weight parsed by utils)
# ------------------------------------------------------------------

def test_pack_size_raw_extracted_from_title(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert "9.8 oz" in p.pack_size_raw


# ------------------------------------------------------------------
# UPC
# ------------------------------------------------------------------

def test_extracts_upc_from_product_details_table(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.upc == "040000000017"


def test_upc_is_none_when_absent(scraper):
    html = _load("product_on_sale.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B08XXXXXXX2"), "B08XXXXXXX2")
    assert p.upc is None


# ------------------------------------------------------------------
# ASIN / retailer_id
# ------------------------------------------------------------------

def test_extracts_asin_from_url(scraper):
    asin = scraper._extract_asin("https://www.amazon.com/dp/B07ABCDEFG/ref=sr_1_1")
    assert asin == "B07ABCDEFG"


def test_returns_none_asin_when_url_has_no_dp_segment(scraper):
    asin = scraper._extract_asin("https://www.amazon.com/s?k=hot+sauce")
    assert asin is None


# ------------------------------------------------------------------
# Product name
# ------------------------------------------------------------------

def test_extracts_product_name(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.product_name == "Competitor A Agave Hot Sauce 9.8 oz"


def test_retailer_is_amazon(scraper):
    html = _load("product_in_stock.html")
    p = scraper.parse_html(html, _URL_TEMPLATE.format(asin="B07XXXXXXX1"), "B07XXXXXXX1")
    assert p.retailer == "amazon"
