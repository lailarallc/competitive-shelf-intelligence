"""Name check against the live page: no real competitor brand in anything the page shows or is sent.

Loads the page in headless Chromium, clicks every tab (the nav-* buttons), and runs the brand-name gate's denied()
over two things: the page's full text (SVG chart text included) after each tab, and the body of every Dash
response (layout and callbacks), which carries every brand the charts and tables could show. A page that shows no
Cinderhaven at all fails too: a check of an empty or broken page proves nothing.

    python scripts/check_live_page.py [URL]       # default https://competitive.lailarallc.com; prints PASS or FAIL
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_brand_names import DENIED, denied, deny_set  # noqa: E402

URL = "https://competitive.lailarallc.com"


def page_texts(url: str, timeout_ms: int = 90_000) -> tuple[list[str], list[str]]:
    """(page text after each tab, Dash response bodies)."""
    from playwright.sync_api import sync_playwright

    bodies: list[str] = []

    def keep(resp):
        if "_dash-" in resp.url:
            try:
                bodies.append(resp.text())
            except Exception:  # a response with no body (a redirect)
                pass

    texts = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.on("response", keep)
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            texts.append(page.evaluate("document.body.textContent"))
            for button in page.locator("button[id^='nav-']").all():
                button.click()
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
                page.wait_for_timeout(1500)
                texts.append(page.evaluate("document.body.textContent"))
        finally:
            browser.close()
    return texts, bodies


def check(url: str = URL, deny: frozenset[str] = DENIED) -> list[str]:
    texts, bodies = page_texts(url)
    bad = []
    for i, t in enumerate(texts):
        if denied(t, deny):
            bad.append(f"the page text after tab {i} names a real brand")
    for i, b in enumerate(bodies):
        if denied(b, deny):
            bad.append(f"Dash response {i} names a real brand")
    if not any("Cinderhaven" in t for t in texts + bodies):
        bad.append("the page shows no Cinderhaven data: a check of an empty page proves nothing")
    if len(texts) < 2:
        bad.append("no tab buttons found: the page did not render its navigation")
    return bad


def main(argv: list[str]) -> int:
    url = argv[0] if argv else URL
    try:
        bad = check(url, deny_set())
    except Exception as e:  # a page that will not load is a FAIL, not a crash
        bad = [f"the page could not be checked: {type(e).__name__}: {e}"]
    for b in bad:
        print(f"  {b}")
    print(f"Live page name check ({url}): {'PASS' if not bad else 'FAIL'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
