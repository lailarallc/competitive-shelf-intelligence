"""Public display names for brands, products and retailer sites.

Every name the dashboard draws passes through this module. Competitor brands
and products are shown under invented names, and the two retailer sites are
shown as role labels. The swap happens where the data is loaded, so it holds
for whatever is in the database: the synthetic demo rows today, or scraped
rows if live scraping is ever switched on.

A brand that has no entry in BRAND_ALIASES is never shown under its own name.
It gets a stable "Competitor XXXX" label instead, so a newly tracked brand
cannot reach the page by accident.

The invented names were screened by web search on 2026-11-16 (see
docs/name-screen.md). That is a screen, not a trademark clearance.
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd

from app.constants import OWN_BRAND

# database name (lower case) -> invented display name. The database holds Competitor A to F since the live rename
# (2026-11-17, scripts/owner_rename_live.ps1); this public repo names no real brand (scripts/check_brand_names.py).
BRAND_ALIASES = {
    "competitor a": "Sunvane",
    "competitor b": "Marrowgate",
    "competitor c": "Brindlecap",
    "competitor d": "Quillfire",
    "competitor e": "Pellam Ridge",
    "competitor f": "Tindermoth",
}

# database brand (lower case) -> generic product descriptor
PRODUCT_STYLES = {
    "competitor a": "Sriracha-Style Hot Sauce",
    "competitor b": "Black Garlic Hot Sauce",
    "competitor c": "Habanero Hot Sauce",
    "competitor d": "Extra Hot Sauce",
    "competitor e": "Habanero Pepper Sauce",
    "competitor f": "Habanero Hot Sauce",
}

RETAILER_LABELS = {
    "amazon": "Online marketplace",
    "walmart": "Mass retailer site",
    "all": "Online marketplace + Mass retailer site",
    "synthetic": "Synthetic",
}

MARKETPLACE = RETAILER_LABELS["amazon"]
MASS_SITE = RETAILER_LABELS["walmart"]

_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|oz|ml|g)\b", re.I)


def _key(name: object) -> str:
    return str(name).strip().lower().replace("’", "'")


def is_own_brand(name: object) -> bool:
    return OWN_BRAND.lower() in _key(name)


def brand_alias(name: object) -> str:
    """Display name for a brand. The own brand passes through unchanged."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    if is_own_brand(name):
        return str(name)
    key = _key(name)
    if key in BRAND_ALIASES:
        return BRAND_ALIASES[key]
    return "Competitor " + hashlib.sha1(key.encode("utf-8")).hexdigest()[:4].upper()


def product_alias(brand: object, product: object) -> str:
    """Display name for a product: invented brand, generic style, pack size."""
    if product is None or (isinstance(product, float) and pd.isna(product)):
        return ""
    if is_own_brand(brand) or is_own_brand(product):
        return str(product)
    style = PRODUCT_STYLES.get(_key(brand), "Sauce")
    size = _SIZE.search(str(product))
    parts = [brand_alias(brand), style]
    if size:
        parts.append(f"{size.group(1)} {size.group(2).lower()}")
    return " ".join(parts)


def retailer_label(code: object) -> str:
    """Role label for a retailer site. Unknown sites become 'Retailer site'."""
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    return RETAILER_LABELS.get(_key(code), "Retailer site")


def anonymize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Swap every brand, product and retailer name in a query result."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if "product_name" in out.columns and "brand_name" in out.columns:
        out["product_name"] = [
            product_alias(b, p) for b, p in zip(out["brand_name"], out["product_name"])
        ]
    if "brand_name" in out.columns:
        out["brand_name"] = out["brand_name"].map(brand_alias)
    if "retailer" in out.columns:
        out["retailer"] = out["retailer"].map(retailer_label)
    return out
