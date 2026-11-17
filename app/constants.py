"""Lailara Design System v2 — color and typography constants.

Adapted from retail-velocity-decision-tool/app/constants.py.
This project uses the same token names; values are identical.
"""

from __future__ import annotations

# ============================================================
# Canvas and London greyscale
# ============================================================
CANVAS      = "#f5f3ee"   # London-100 warmed — page background
INK         = "#0d0d0d"   # London-5 — chart titles, primary headings
TEXT        = "#333333"   # London-20 — body text
TEXT_SEC    = "#595959"   # London-35 — axis text, subtitles, labels
REFERENCE   = "#666666"   # London-40 — median / benchmark lines
GREY_LIGHT  = "#d9d9d9"   # London-85 — gridlines, borders
WHITE       = "#ffffff"

# ============================================================
# Brand red (text and 1px rules only — never background fill)
# ============================================================
RED         = "#cc100a"   # Red-42

# ============================================================
# Chicago — accent blue
# ============================================================
CHICAGO     = "#1f2e7a"   # Chicago-20 — primary button, chart anchor
CHICAGO_LT  = "#8e9ad0"   # Chicago-70 — chart light pair

# ============================================================
# Hong Kong sequential teal (magnitude-ranked data)
# ============================================================
TEAL        = "#158f75"   # HK-35 — Lailara default teal
HK_DARK     = "#0a5c4b"   # HK-15
HK_LIGHT    = "#6dcdb5"   # HK-70

# ============================================================
# Retailer-specific colors for this project
# ============================================================
COLOR_MASS_SITE = CHICAGO    # Chicago-20 navy
COLOR_MARKETPLACE = TEAL      # HK-35 teal
COLOR_OOS     = "#ee8880"   # Red-70 tint — OOS heatmap fill (red #cc100a is ink, never a fill)
COLOR_PROMO   = "#ee8a2a"   # SG-55 orange — promo events

# ============================================================
# Typography
# ============================================================
FONT_SERIF  = "'Playfair Display', Georgia, 'Times New Roman', serif"
FONT_SANS   = "'Source Sans 3', 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif"

# ============================================================
# Date range filter options (R16)
# ============================================================
DATE_RANGE_OPTIONS = [
    {"label": "Last 30 days", "value": 30},
    {"label": "Last 60 days", "value": 60},
    {"label": "Last 90 days", "value": 90},
    {"label": "All history",  "value": 0},
]
DATE_RANGE_DEFAULT = 30

# Categorical chart palette (paired color families)
OWN_BRAND = "Cinderhaven"

CHART_PALETTE = [
    "#1f2e7a",  # Chicago-20
    "#8e9ad0",  # Chicago-70
    "#0c6552",  # HK-20
    "#6dcdb5",  # HK-70
    "#7e1f34",  # Tokyo-20
    "#e68a9a",  # Tokyo-70
    "#7a3d10",  # SG-20
    "#f6b97c",  # SG-70
    "#8e0b07",  # Red-20
    "#ee8880",  # Red-70
]
