"""Tests for src/scrapers/base.py — rate limiting, robots.txt, block detection."""

import time
import urllib.robotparser
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.base import (
    BaseProductScraper,
    BlockDetectedError,
    ParseFailureError,
    RobotsDisallowedError,
    ScrapedProduct,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scraper():
    """A BaseProductScraper instance with Playwright NOT started (unit tests only)."""
    return BaseProductScraper(rate_limit_secs=2.0, respect_robots=True)


def _mock_response(status: int = 200, url: str = "https://example.com/product") -> MagicMock:
    r = MagicMock()
    r.status = status
    r.url = url
    return r


def _mock_page(content: str = "<html><body>Product page</body></html>") -> MagicMock:
    page = MagicMock()
    page.content.return_value = content
    return page


# ---------------------------------------------------------------------------
# ScrapedProduct dataclass
# ---------------------------------------------------------------------------


def test_scraped_product_defaults_oos_and_promo_to_false():
    p = ScrapedProduct(retailer="walmart", retailer_id="123", product_name="Hot Sauce")
    assert p.is_oos is False
    assert p.has_promo_badge is False
    assert p.price_drop_promo is False


def test_scraped_product_price_drop_promo_is_false_by_default():
    # price_drop_promo is set by the CLI, not the scraper
    p = ScrapedProduct(retailer="amazon", retailer_id="AABC123456", product_name="Sauce")
    assert p.price_drop_promo is False


# ---------------------------------------------------------------------------
# robots.txt enforcement
# ---------------------------------------------------------------------------


def test_raises_robots_disallowed_when_path_excluded(scraper):
    rp = MagicMock(spec=urllib.robotparser.RobotFileParser)
    rp.can_fetch.return_value = False

    with patch("urllib.robotparser.RobotFileParser") as MockRp:
        MockRp.return_value = rp
        rp.read.return_value = None

        with pytest.raises(RobotsDisallowedError):
            scraper.check_robots("https://www.walmart.com/ip/product/12345")

    rp.can_fetch.assert_called_once()


def test_allows_fetch_when_robots_permits_path(scraper):
    rp = MagicMock(spec=urllib.robotparser.RobotFileParser)
    rp.can_fetch.return_value = True

    with patch("urllib.robotparser.RobotFileParser") as MockRp:
        MockRp.return_value = rp
        rp.read.return_value = None

        # Should not raise
        scraper.check_robots("https://www.walmart.com/ip/product/12345")


def test_allows_fetch_when_robots_txt_fetch_fails(scraper):
    """On network error reading robots.txt, fail-open (allow the scrape)."""
    rp = MagicMock(spec=urllib.robotparser.RobotFileParser)
    rp.read.side_effect = OSError("Connection error")

    with patch("urllib.robotparser.RobotFileParser") as MockRp:
        MockRp.return_value = rp

        # Should not raise even though robots.txt couldn't be fetched
        scraper.check_robots("https://www.walmart.com/ip/product/12345")


def test_robots_result_is_cached_for_same_origin(scraper):
    """robots.txt is fetched once per origin, not once per URL."""
    rp = MagicMock(spec=urllib.robotparser.RobotFileParser)
    rp.can_fetch.return_value = True

    with patch("urllib.robotparser.RobotFileParser") as MockRp:
        MockRp.return_value = rp
        rp.read.return_value = None

        scraper.check_robots("https://www.walmart.com/ip/product/111")
        scraper.check_robots("https://www.walmart.com/ip/product/222")

    # RobotFileParser only instantiated once for walmart.com
    assert MockRp.call_count == 1


def test_check_robots_skipped_when_respect_robots_false():
    scraper = BaseProductScraper(respect_robots=False)
    with patch("urllib.robotparser.RobotFileParser") as MockRp:
        scraper.check_robots("https://www.walmart.com/ip/product/123")
    MockRp.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_minimum_delay_enforced_between_fetches(scraper):
    """time.sleep is called with at least rate_limit_secs when called immediately."""
    # Simulate last request happening just now
    scraper._last_request_time = time.monotonic()

    with patch("time.sleep") as mock_sleep:
        with patch("time.monotonic", side_effect=[scraper._last_request_time, scraper._last_request_time, time.monotonic()]):
            scraper._rate_limit()

    mock_sleep.assert_called_once()
    sleep_duration = mock_sleep.call_args[0][0]
    assert sleep_duration >= 2.0, f"Expected >= 2.0s sleep, got {sleep_duration}"


def test_no_sleep_when_enough_time_has_passed(scraper):
    """No sleep when enough time has elapsed since the last request."""
    # Last request was 10 seconds ago
    scraper._last_request_time = time.monotonic() - 10.0

    with patch("time.sleep") as mock_sleep:
        scraper._rate_limit()

    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Block detection
# ---------------------------------------------------------------------------


def test_returns_true_when_status_429(scraper):
    response = _mock_response(status=429)
    page = _mock_page()
    assert scraper._detect_block(response, page) is True


def test_returns_true_when_status_403(scraper):
    response = _mock_response(status=403)
    page = _mock_page()
    assert scraper._detect_block(response, page) is True


def test_returns_true_when_captcha_element_present(scraper):
    captcha_page = _mock_page('<html><body><div id="captcha">Solve this</div></body></html>')
    response = _mock_response(status=200)
    assert scraper._detect_block(response, captcha_page) is True


def test_returns_true_when_prove_you_are_human_text(scraper):
    captcha_page = _mock_page("<html><body>Please prove you are human</body></html>")
    response = _mock_response(status=200)
    assert scraper._detect_block(response, captcha_page) is True


def test_returns_false_for_normal_product_page(scraper):
    normal_page = _mock_page(
        "<html><body><h1>Competitor A Sriracha</h1><p>$8.99</p></body></html>"
    )
    response = _mock_response(status=200)
    assert scraper._detect_block(response, normal_page) is False


def test_returns_false_when_response_is_none(scraper):
    page = _mock_page()
    assert scraper._detect_block(None, page) is False
