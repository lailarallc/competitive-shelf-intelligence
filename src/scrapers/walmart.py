"""
Walmart product scraper.

Primary strategy: parse the __NEXT_DATA__ JSON embedded in every Walmart product page.
This JSON blob is far more stable than CSS selectors and contains all required fields.

Promo signals (R3):
  (a) has_promo_badge: priceInfo.isPriceReduced is True OR priceReducedDisplay is present
  (b) price_drop_promo: set by the CLI after comparing to the prior snapshot; not set here

OOS signals (R4):
  (a) oos_text: availabilityStatus is not IN_STOCK / AVAILABLE
  (b) no_cart_button: Add to Cart button absent from DOM (secondary check)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests as _requests

from src.scrapers.base import (
    BaseProductScraper,
    BlockDetectedError,  # noqa: F401 — re-exported for callers
    ParseFailureError,
    RobotsDisallowedError,  # noqa: F401 — re-exported for callers
    ScrapedProduct,
)

logger = logging.getLogger(__name__)

# Walmart item IDs are numeric; extract from URL as a fallback
_WALMART_ADD_TO_CART_SELECTOR = '[data-automation-id="add-to-cart-button"]'

# Known paths to the product data object within __NEXT_DATA__.
# Walmart has changed this structure; we try all known paths in order.
_PRODUCT_PATHS = [
    ["props", "pageProps", "initialData", "data", "product"],
    ["props", "pageProps", "initialData", "data", "idmlMap"],  # some categories
    ["props", "pageProps", "serverProps", "pageData", "product"],
]


def _camoufox_available() -> bool:
    """Return True if camoufox is installed and its Firefox binary has been fetched."""
    try:
        from camoufox.sync_api import Camoufox  # noqa: F401
        return True
    except ImportError:
        return False


class WalmartScraper(BaseProductScraper):
    """Scrapes a Walmart product page using __NEXT_DATA__ JSON parsing.

    Transport selection priority:
      1. SCRAPERAPI_KEY set  → HTTP via ScraperAPI (production, handles anti-bot)
      2. camoufox installed  → Firefox-based stealth browser (free, no key needed)
      3. Google Shopping     → price-only fallback via Google search (demo/dev)
      4. plain Playwright    → fixture tests only; blocked by Walmart in production
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._use_google_shopping = False

    def __enter__(self) -> "WalmartScraper":
        if os.getenv("SCRAPERAPI_KEY"):
            return self  # no browser needed
        if _camoufox_available():
            try:
                from camoufox.sync_api import Camoufox
                proxy_url = os.getenv("PROXY_URL")
                proxy = {"server": proxy_url} if proxy_url else None
                self._camoufox_cm = Camoufox(
                    headless=True,
                    os="windows",
                    block_webrtc=True,
                    proxy=proxy,
                )
                self._camoufox_browser = self._camoufox_cm.__enter__()
                logger.info("WalmartScraper: using camoufox (Firefox stealth)")
                return self
            except Exception as exc:
                logger.warning("camoufox launch failed (%s) — falling back to Google Shopping", exc)
                self._use_google_shopping = True
                return self
        # Neither ScraperAPI nor camoufox — use Google Shopping as the price-only demo fallback
        logger.info("WalmartScraper: no ScraperAPI key or camoufox — using Google Shopping fallback")
        self._use_google_shopping = True
        return self

    def __exit__(self, *args) -> None:
        if hasattr(self, "_camoufox_cm"):
            try:
                self._camoufox_cm.__exit__(*args)
            except Exception:
                pass
        elif not os.getenv("SCRAPERAPI_KEY") and not self._use_google_shopping:
            super().__exit__(*args)

    def fetch_product(self, url: str, retailer_id: str) -> ScrapedProduct:
        """Fetch and parse a Walmart product page.

        Raises:
            RobotsDisallowedError: robots.txt disallows the URL.
            BlockDetectedError: Walmart blocked the request — stop the run.
            ParseFailureError: Required fields missing — log and skip (R6).
        """
        self.check_robots(url)
        if os.getenv("SCRAPERAPI_KEY"):
            product = self._fetch_via_scraperapi(url, retailer_id)
        elif hasattr(self, "_camoufox_browser"):
            product = self._fetch_via_camoufox(url, retailer_id)
        elif self._use_google_shopping:
            from src.scrapers.google_shopping import fetch_walmart_price_via_google
            # Extract a human-readable name from the Walmart URL slug (/ip/Name/ID)
            parts = url.rstrip("/").split("/")
            slug_name = parts[-2] if len(parts) >= 3 and parts[-1].isdigit() else retailer_id
            name_hint = slug_name.replace("-", " ")
            product = fetch_walmart_price_via_google(
                name_hint, retailer_id, url, self.rate_limit_secs
            )
        else:
            page = self.fetch_page(url)
            try:
                product = self._parse_page(page, url, retailer_id)
            finally:
                page.close()
        logger.info(
            "Scraped Walmart listing %s: %s @ $%.2f",
            retailer_id,
            product.product_name,
            product.current_price or 0,
        )
        return product

    def _fetch_via_camoufox(self, url: str, retailer_id: str) -> ScrapedProduct:
        """Fetch Walmart page via camoufox Firefox stealth browser."""
        self._rate_limit()
        page = self._camoufox_browser.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if self._detect_block(response, page):
                raise BlockDetectedError(f"Anti-bot block detected at {url}")
            self._slow_scroll(page)
            return self._parse_page(page, url, retailer_id)
        finally:
            page.close()

    def _fetch_via_scraperapi(self, url: str, retailer_id: str) -> ScrapedProduct:
        """Fetch Walmart page HTML via ScraperAPI, then parse with parse_html().

        ScraperAPI renders the page in a real browser and handles anti-bot.
        We still enforce our rate limit so we don't hammer their endpoint.
        """
        self._rate_limit()
        api_key = os.getenv("SCRAPERAPI_KEY")
        try:
            resp = _requests.get(
                "https://api.scraperapi.com/",
                params={
                    "api_key": api_key,
                    "url": url,
                    "render": "true",
                    "country_code": "us",
                },
                timeout=90,
            )
            resp.raise_for_status()
        except _requests.RequestException as exc:
            # requests puts the full request URL, api_key included, into the
            # exception text; this message is logged and stored in
            # scrape_failures, so strip the key and drop the chained exception.
            detail = str(exc).replace(api_key, "***") if api_key else str(exc)
            raise ParseFailureError(
                f"ScraperAPI request failed for {url}: {detail}"
            ) from None
        return self.parse_html(resp.text, url, retailer_id)

    # ------------------------------------------------------------------
    # Parsing helpers (also called directly in tests via saved HTML)
    # ------------------------------------------------------------------

    def parse_html(self, html: str, url: str, retailer_id: str) -> ScrapedProduct:
        """Parse a saved HTML string — used in fixture-based tests.

        Does not use Playwright; parses the raw HTML directly.
        """
        from html.parser import HTMLParser

        class ScriptExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._in_next_data = False
                self.content = ""

            def handle_starttag(self, tag, attrs):
                if tag == "script":
                    attr_dict = dict(attrs)
                    if attr_dict.get("id") == "__NEXT_DATA__":
                        self._in_next_data = True

            def handle_data(self, data):
                if self._in_next_data:
                    self.content += data

            def handle_endtag(self, tag):
                if tag == "script" and self._in_next_data:
                    self._in_next_data = False

        extractor = ScriptExtractor()
        extractor.feed(html)
        if not extractor.content.strip():
            raise ParseFailureError(f"__NEXT_DATA__ not found in HTML for {url}")

        try:
            data = json.loads(extractor.content)
        except json.JSONDecodeError as exc:
            raise ParseFailureError(f"Invalid __NEXT_DATA__ JSON at {url}: {exc}")

        product_node = self._find_product_node(data, url)

        # Check add-to-cart button presence in raw HTML
        has_cart_button = _WALMART_ADD_TO_CART_SELECTOR.replace(
            '[data-automation-id="add-to-cart-button"]', 'add-to-cart-button'
        ) in html or 'add-to-cart-button' in html

        return self._extract_fields(product_node, url, retailer_id, has_cart_button)

    def _parse_page(self, page, url: str, retailer_id: str) -> ScrapedProduct:
        """Parse a live Playwright page."""
        next_data = self._extract_next_data_from_page(page, url)
        product_node = self._find_product_node(next_data, url)

        # Check for cart button in live page
        try:
            cart_btn = page.query_selector(_WALMART_ADD_TO_CART_SELECTOR)
            has_cart_button = cart_btn is not None
        except Exception:
            has_cart_button = True  # assume available if selector check fails

        return self._extract_fields(product_node, url, retailer_id, has_cart_button)

    def _extract_next_data_from_page(self, page, url: str) -> dict:
        """Extract and parse __NEXT_DATA__ from a live Playwright page."""
        try:
            content = page.evaluate(
                "() => document.querySelector('script#__NEXT_DATA__')?.textContent || ''"
            )
        except Exception as exc:
            raise ParseFailureError(f"Could not read __NEXT_DATA__ at {url}: {exc}")

        if not content:
            raise ParseFailureError(f"__NEXT_DATA__ script not found on page: {url}")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParseFailureError(f"Could not parse __NEXT_DATA__ JSON at {url}: {exc}")

    def _find_product_node(self, data: dict, url: str) -> dict:
        """Traverse __NEXT_DATA__ to locate the product object.

        Tries multiple known paths because Walmart's structure varies by category.
        A valid product node contains at minimum a 'name' (or 'productName') key.
        """
        for path in _PRODUCT_PATHS:
            node = data
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
                if node is None:
                    break
            if node and isinstance(node, dict) and (
                "name" in node or "productName" in node
            ):
                return node

        # Fallback: breadth-first search for a dict containing 'priceInfo'
        found = self._bfs_find_price_node(data)
        if found:
            return found

        raise ParseFailureError(
            f"Could not locate product data in __NEXT_DATA__ at {url}. "
            f"Top-level keys: {list(data.keys())}"
        )

    def _bfs_find_price_node(self, data: dict) -> Optional[dict]:
        """Last-resort: walk the JSON tree looking for a node with priceInfo."""
        queue = [data]
        depth = 0
        while queue and depth < 6:
            next_queue = []
            for node in queue:
                if isinstance(node, dict):
                    if "priceInfo" in node and ("name" in node or "productName" in node):
                        return node
                    next_queue.extend(node.values())
                elif isinstance(node, list):
                    next_queue.extend(node)
            queue = next_queue
            depth += 1
        return None

    def _extract_fields(
        self,
        product: dict,
        url: str,
        retailer_id: str,
        has_cart_button: bool,
    ) -> ScrapedProduct:
        """Extract all required fields from the product node (R1/R2).

        Raises ParseFailureError if name or price cannot be found (R6).
        """
        name = product.get("name") or product.get("productName")
        if not name:
            raise ParseFailureError(f"Product name missing in __NEXT_DATA__ at {url}")

        price_info = product.get("priceInfo") or {}
        current = price_info.get("currentPrice") or {}
        # Walmart uses 'price' (float) or 'linePrice' (string like "$8.97")
        current_price = current.get("price")
        if current_price is None:
            line = current.get("linePrice", "")
            if line:
                try:
                    current_price = float(line.replace("$", "").replace(",", "").strip())
                except ValueError:
                    pass
        if current_price is None:
            raise ParseFailureError(f"Price not found in __NEXT_DATA__ at {url}")

        # Normalize prices for the DB convention: the regular (higher) price
        # maps to price_cents and the promotional (lower) price to
        # sale_price_cents. Walmart's currentPrice is the now/sale price and
        # wasPrice is the original list price, so the higher value is wasPrice.
        # Storing wasPrice as the sale price made promo depth go negative
        # (e.g. $8.97 now / $11.98 was -> -33.6%); flip them here.
        was = price_info.get("wasPrice") or {}
        was_price = was.get("price")
        if was_price is not None and was_price > current_price:
            regular_price = was_price
            promo_price = current_price
        else:
            regular_price = current_price
            promo_price = None

        # Promo badge signal (R3-a)
        has_promo_badge = bool(price_info.get("isPriceReduced", False)) or bool(
            price_info.get("priceReducedDisplay")
        )
        sale_badge_text = price_info.get("priceReducedDisplay")

        # OOS detection (R4)
        availability = (product.get("availabilityStatus") or "").upper()
        is_oos_text = availability not in ("IN_STOCK", "AVAILABLE", "")
        is_oos_no_cart = not has_cart_button
        is_oos = is_oos_text or is_oos_no_cart
        if is_oos_text:
            oos_signal = "oos_text"
        elif is_oos_no_cart:
            oos_signal = "no_cart_button"
        else:
            oos_signal = None

        rating_node = product.get("rating") or {}
        star_rating = rating_node.get("averageRating")
        review_count = rating_node.get("numberOfReviews")

        upc = product.get("upc")

        return ScrapedProduct(
            retailer="walmart",
            retailer_id=retailer_id,
            product_name=str(name),
            current_price=float(regular_price),
            sale_price=float(promo_price) if promo_price is not None else None,
            has_promo_badge=has_promo_badge,
            sale_badge_text=str(sale_badge_text) if sale_badge_text else None,
            is_oos=is_oos,
            oos_signal=oos_signal,
            star_rating=float(star_rating) if star_rating is not None else None,
            review_count=int(review_count) if review_count is not None else None,
            pack_size_raw=str(name),  # weight parsed later from product name
            upc=str(upc) if upc else None,
        )
