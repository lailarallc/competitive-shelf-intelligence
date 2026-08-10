"""Demo golden lock — competitive-shelf-intelligence.

This tool reads a live database, so there is no committed demo data file to
byte-lock. Instead the golden locks the two things the 07-31 audit + Prompt 4
cared about:

1. **Honest provenance.** The demo data is synthetic (modeled on public product
   pages), NOT live-scraped competitor data. A prominent banner says so on every
   view, and it must keep saying so — synthetic-presented-as-scraped can't survive
   into a client-facing deliverable. (Shawn's call: keep the synthetic demo behind
   the honest banner; the scrapers are real and the framing doesn't gut the story.)
2. **No wall-clock on the analysis path.** The date-window anchor is the newest
   scraped_date, never today.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "app" / "components.py"
LAYOUT = ROOT / "app" / "layout.py"


def test_honest_provenance_banner_text():
    src = COMPONENTS.read_text(encoding="utf-8")
    # The banner must plainly label the data synthetic and NOT live-scraped.
    assert "synthetic" in src.lower()
    assert "not live scraped" in src.lower()
    assert "demo_data_banner" in src


def test_banner_is_shown_in_layout():
    layout = LAYOUT.read_text(encoding="utf-8")
    assert "demo_data_banner" in layout   # rendered above the tabs, always visible


def test_date_window_anchor_is_never_wall_clock(monkeypatch):
    from app import data
    # explicit anchor -> exact cutoff
    assert data._date_cutoff(30, anchor=date(2025, 1, 31)) == date(2025, 1, 1)
    # no explicit anchor: uses the newest scraped_date, never today. With no data
    # it RAISES rather than fabricating a today-based window.
    monkeypatch.setattr(data, "_max_scraped_date", lambda: None)
    with pytest.raises(ValueError):
        data._date_cutoff(30)
    # with data, the anchor is the data's own max date.
    monkeypatch.setattr(data, "_max_scraped_date", lambda: date(2025, 6, 30))
    assert data._date_cutoff(30) == date(2025, 5, 31)


def test_no_wall_clock_in_source():
    src = (ROOT / "app" / "data.py").read_text(encoding="utf-8")
    assert "date.today()" not in src
