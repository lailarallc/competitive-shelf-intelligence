"""Tests for src/scrapers/walmart.py — fixture-based, no live network calls."""

from pathlib import Path

import pytest

from src.scrapers.base import ParseFailureError
from src.scrapers.walmart import WalmartScraper

FIXTURES = Path(__file__).parent.parent / "fixtures" / "walmart"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


@pytest.fixture
def scraper():
    return WalmartScraper(rate_limit_secs=0, respect_robots=False)


# ---------------------------------------------------------------------------
# Price extraction
# ---------------------------------------------------------------------------


def test_extracts_price_from_next_data_json(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.current_price == pytest.approx(8.97)


def test_extracts_product_name(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert "Yellowbird" in product.product_name
    assert "Sriracha" in product.product_name


def test_extracts_upc_from_next_data(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.upc == "853826007254"


def test_extracts_star_rating_and_review_count(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.star_rating == pytest.approx(4.6)
    assert product.review_count == 342


def test_sets_retailer_fields_correctly(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/99999", "99999")
    assert product.retailer == "walmart"
    assert product.retailer_id == "99999"


# ---------------------------------------------------------------------------
# Promo detection (R3)
# ---------------------------------------------------------------------------


def test_no_promo_when_is_price_reduced_false(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.has_promo_badge is False
    assert product.sale_price is None
    assert product.sale_badge_text is None


def test_detects_promo_when_is_price_reduced_true(scraper):
    html = _load("product_on_sale.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/222", "222")
    assert product.has_promo_badge is True


def test_normalizes_regular_and_sale_price_when_on_sale(scraper):
    """Regular (higher) price -> current_price (price_cents);
    promotional (lower) price -> sale_price (sale_price_cents).

    Storing the higher was-price as sale_price made promo depth negative;
    this asserts the normalized convention so depth stays positive.
    """
    html = _load("product_on_sale.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/222", "222")
    assert product.current_price == pytest.approx(21.99)  # regular / was
    assert product.sale_price == pytest.approx(17.88)     # promotional / now
    # Promo depth = (regular - sale) / regular must be positive and sensible
    depth = (product.current_price - product.sale_price) / product.current_price * 100
    assert depth == pytest.approx(18.69, abs=0.1)


def test_extracts_sale_badge_text(scraper):
    html = _load("product_on_sale.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/222", "222")
    assert product.sale_badge_text == "Save $4.11"


# ---------------------------------------------------------------------------
# OOS detection (R4)
# ---------------------------------------------------------------------------


def test_flags_oos_when_availability_status_out_of_stock(scraper):
    html = _load("product_out_of_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/333", "333")
    assert product.is_oos is True
    assert product.oos_signal == "oos_text"


def test_not_oos_when_in_stock_with_cart_button(scraper):
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.is_oos is False
    assert product.oos_signal is None


def test_flags_oos_when_add_to_cart_button_absent(scraper):
    """Signal b: availabilityStatus=IN_STOCK but no cart button in DOM (R4)."""
    html = _load("product_no_cart_button.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/444", "444")
    assert product.is_oos is True
    assert product.oos_signal == "no_cart_button"


# ---------------------------------------------------------------------------
# Parse failure (R6 / AE5)
# ---------------------------------------------------------------------------


def test_raises_parse_failure_when_next_data_missing(scraper):
    html = _load("product_missing_next_data.html")
    with pytest.raises(ParseFailureError):
        scraper.parse_html(html, "https://www.walmart.com/ip/test/999", "999")


def test_raises_parse_failure_when_price_field_absent(scraper):
    """No price in __NEXT_DATA__ → ParseFailureError (R6)."""
    html = """<html><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"initialData":{"data":{"product":{
      "name": "Test Product",
      "priceInfo": {},
      "availabilityStatus": "IN_STOCK"
    }}}}}}
    </script></html>"""
    with pytest.raises(ParseFailureError, match="Price not found"):
        scraper.parse_html(html, "https://www.walmart.com/ip/test/998", "998")


def test_raises_parse_failure_when_product_name_absent(scraper):
    html = """<html><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"initialData":{"data":{"product":{
      "priceInfo": {"currentPrice": {"price": 8.99}},
      "availabilityStatus": "IN_STOCK"
    }}}}}}
    </script></html>"""
    with pytest.raises(ParseFailureError):
        scraper.parse_html(html, "https://www.walmart.com/ip/test/997", "997")


# ---------------------------------------------------------------------------
# price_drop_promo is set by CLI, not scraper
# ---------------------------------------------------------------------------


def test_price_drop_promo_is_always_false_from_scraper(scraper):
    """price_drop_promo is set by the CLI after comparing to prior snapshot."""
    html = _load("product_in_stock.html")
    product = scraper.parse_html(html, "https://www.walmart.com/ip/test/111", "111")
    assert product.price_drop_promo is False


# ---------------------------------------------------------------------------
# ScraperAPI errors must not leak the API key
# ---------------------------------------------------------------------------


def test_scraperapi_error_message_does_not_contain_api_key(scraper, monkeypatch):
    """The failure text is logged and written to scrape_failures."""
    import requests

    fake_key = "testkey1234567890abcdef"
    monkeypatch.setenv("SCRAPERAPI_KEY", fake_key)
    monkeypatch.setattr(scraper, "_rate_limit", lambda: None)

    def fake_get(*args, **kwargs):
        raise requests.HTTPError(
            f"500 Server Error for url: https://api.scraperapi.com/?api_key={fake_key}&url=x"
        )

    monkeypatch.setattr("src.scrapers.walmart._requests.get", fake_get)

    with pytest.raises(ParseFailureError) as excinfo:
        scraper._fetch_via_scraperapi("https://www.walmart.com/ip/test/1", "1")

    assert fake_key not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
