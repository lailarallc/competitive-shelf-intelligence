"""Shared utilities for the shelf intelligence project."""

from __future__ import annotations

import re
from typing import Optional


# Conversion factors to ounces
_UNIT_TO_OZ = {
    "oz": 1.0,
    "fl oz": 1.0,  # fluid ounce ≈ weight ounce for sauce density
    "lb": 16.0,
    "lbs": 16.0,
    "g": 0.035274,
    "gram": 0.035274,
    "grams": 0.035274,
    "kg": 35.274,
    "ml": 0.033814,
    "l": 33.814,
    "liter": 33.814,
    "liters": 33.814,
}

# Pattern: number (int or decimal) followed by optional space and unit
_WEIGHT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|oz|lbs?|grams?|g|kg|ml|liters?|l)\b",
    re.IGNORECASE,
)


def parse_weight_oz(raw: Optional[str]) -> Optional[float]:
    """Extract pack weight in ounces from a raw product string.

    Returns None when no recognizable weight pattern is found.

    Examples:
        "16 oz" → 16.0
        "1 lb" → 16.0
        "500g" → 17.64
        "Competitor A Sriracha 9.8 oz" → 9.8
        "No weight info" → None
    """
    if not raw:
        return None
    match = _WEIGHT_PATTERN.search(raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower().strip().replace(".", "").replace(" ", "")
    # Normalize 'floz' → 'fl oz' lookup
    if unit.startswith("fl"):
        unit = "fl oz"
    multiplier = _UNIT_TO_OZ.get(unit)
    if multiplier is None:
        return None
    return round(value * multiplier, 4)
