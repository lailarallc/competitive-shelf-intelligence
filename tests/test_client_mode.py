"""Client-mode tests for competitive-shelf-intelligence.

Adversarial fixtures per checklist §6: clean run (price positioning + OOS),
mandatory honest provenance (missing -> blocked), missing required column
(blocked), empty file, and the --final watermark. Fictional-placeholder identity.

Skipped if lailara_engagement isn't installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("lailara_engagement")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import client_mode  # noqa: E402

from lailara_engagement.errors import ReadError  # noqa: E402

_CONFIG = """
client: {name: Meridian Farms}
engagement: {id: MER-2026-08}
as_of_date: "2026-01-31"
demo: true
provenance: "In-store price audits conducted by the client, Jan 2026 — client-collected."
basis: {own_brand: Meridian}
columns:
  retailer: retailer
  brand: brand
  product: product
  price: price
  pack_weight_oz: pack_weight_oz
  observed_date: observed_date
  in_stock: in_stock
"""

_NO_PROVENANCE = """
client: {name: Meridian Farms}
engagement: {id: MER-2026-08}
as_of_date: "2026-01-31"
demo: true
basis: {own_brand: Meridian}
columns: {retailer: retailer, brand: brand, product: product, price: price, pack_weight_oz: pack_weight_oz, observed_date: observed_date}
"""

_CLEAN = (
    "retailer,brand,product,price,pack_weight_oz,observed_date,in_stock\n"
    "Walmart,Meridian,Marinara,5.98,24,2026-01-15,true\n"
    "Walmart,Competitor Co,Marinara,8.48,24,2026-01-15,true\n"
    "Walmart,Meridian,Pesto,6.48,8,2026-01-15,false\n"
)


def _cfg(tmp_path, text=_CONFIG):
    p = tmp_path / "engagement.yml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_clean_run_price_positioning_and_oos(tmp_path):
    src = _write(tmp_path, "s.csv", _CLEAN)
    result = client_mode.run(_cfg(tmp_path), src, str(tmp_path / "out"))
    assert result["status"] == "ok"
    assert result["observations"] == 3
    s = json.load(open(result["summary_json"], encoding="utf-8"))
    wm = next(r for r in s["by_retailer"] if r["retailer"] == "Walmart")
    # own = mean($5.98/24, $6.48/8) ; competitor = $8.48/24
    assert wm["own_price_per_oz"] == pytest.approx((5.98/24 + 6.48/8) / 2, abs=1e-3)
    assert wm["competitor_price_per_oz"] == pytest.approx(8.48/24, abs=1e-3)
    assert s["oos_rate"] == pytest.approx(1/3, abs=1e-3)     # 1 of 3 out of stock
    html = open(result["report"], encoding="utf-8").read()
    assert "Meridian Farms" in html and "DRAFT" in html
    assert "client-collected" in html.lower()               # provenance shown


def test_observation_window_tracks_observed_dates_not_a_hardcode(tmp_path):
    """The rendered observation window must be the ACTUAL observed-date span and
    move with the data. The suite asserted price/OOS numbers and the observation
    count, never the window text — a hardcoded span matching the demo would pass,
    the failure mode behind trade-spend quoting 26 weeks as 'trailing 52 weeks'.

    Both halves: assert each distinct span renders, AND assert the other span (a
    stand-in for a hardcode) is absent."""
    hdr = "retailer,brand,product,price,pack_weight_oz,observed_date,in_stock\n"
    src_a = _write(tmp_path, "a.csv", hdr +
                   "Walmart,Meridian,Marinara,5.98,24,2026-01-10,true\n"
                   "Walmart,Competitor Co,Marinara,8.48,24,2026-01-20,true\n")
    res_a = client_mode.run(_cfg(tmp_path), src_a, str(tmp_path / "out_a"))
    html_a = open(res_a["report"], encoding="utf-8").read()
    assert "2026-01-10 to 2026-01-20" in html_a
    assert "2025-03-05" not in html_a

    src_b = _write(tmp_path, "b.csv", hdr +
                   "Walmart,Meridian,Marinara,5.98,24,2025-03-05,true\n")
    res_b = client_mode.run(_cfg(tmp_path), src_b, str(tmp_path / "out_b"))
    html_b = open(res_b["report"], encoding="utf-8").read()
    assert "2025-03-05 to 2025-03-05" in html_b
    assert "2026-01-10 to 2026-01-20" not in html_b        # not fixed to span A

    for html in (html_a, html_b):
        low = html.lower()
        assert "trailing" not in low and "52-week" not in low and "365d" not in low


def test_missing_provenance_blocks(tmp_path):
    # Honest provenance is mandatory — no synthetic-presented-as-scraped.
    src = _write(tmp_path, "s.csv", _CLEAN)
    result = client_mode.run(_cfg(tmp_path, _NO_PROVENANCE), src, str(tmp_path / "out"))
    assert result["status"] == "blocked"
    assert "provenance" in open(result["readiness_report"], encoding="utf-8").read().lower()


def test_missing_required_column_blocks(tmp_path):
    src = _write(tmp_path, "bad.csv",
                 "retailer,brand,product,price,observed_date\nWalmart,Meridian,X,5.98,2026-01-15\n")
    result = client_mode.run(_cfg(tmp_path), src, str(tmp_path / "out"))
    assert result["status"] == "blocked"
    assert "pack_weight_oz" in open(result["readiness_report"], encoding="utf-8").read().lower()


def test_empty_file_raises(tmp_path):
    src = _write(tmp_path, "e.csv", "")
    with pytest.raises(ReadError):
        client_mode.run(_cfg(tmp_path), src, str(tmp_path / "out"))


def test_final_drops_watermark(tmp_path):
    src = _write(tmp_path, "s.csv", _CLEAN)
    result = client_mode.run(_cfg(tmp_path), src, str(tmp_path / "out"), final=True)
    assert "ll-draft" not in open(result["report"], encoding="utf-8").read()
