"""No source brand or retailer name reaches the page.

The database (and any future scrape) holds source names. The dashboard may
only draw invented brand names and retailer role labels.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app import anonymize

ROOT = Path(__file__).resolve().parent.parent

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from check_brand_names import denied  # noqa: E402

DB_BRANDS = [f"Competitor {c}" for c in "ABCDEF"]
SOURCE_NAMES = re.compile(r"walmart|amazon|competitor [a-f]\b", re.I)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "brand_name": DB_BRANDS + ["Cinderhaven", "Brand Nobody Mapped"],
        "product_name": [
            "Competitor A Agave Sriracha Hot Sauce 9.8 oz",
            "Competitor B Black Truffle Hot Sauce 6 oz",
            "Competitor C Habanero Hot Sauce 5 oz",
            "Competitor D Extra Hot Sauce 5 oz",
            "Competitor E Habanero Pepper Sauce 5 oz",
            "Competitor F Habanero Hot Sauce 8 oz",
            "Cinderhaven Original Hot Sauce 8 oz",
            "Brand Nobody Mapped Fancy Sauce 7 oz",
        ],
        "retailer": ["walmart", "amazon"] * 4,
        "price_per_oz": [1.0] * 8,
    })


def test_every_database_brand_has_an_invented_name():
    assert all(not anonymize.brand_alias(b).startswith("Competitor ") for b in DB_BRANDS)


def test_no_source_name_survives_when_frame_is_anonymized():
    out = anonymize.anonymize_frame(_frame())
    text = " ".join(out.astype(str).to_numpy().ravel())
    assert not SOURCE_NAMES.search(text), text
    assert not denied(text), text


def test_own_brand_is_unchanged_when_frame_is_anonymized():
    out = anonymize.anonymize_frame(_frame())
    row = out[out["brand_name"] == "Cinderhaven"].iloc[0]
    assert row["product_name"] == "Cinderhaven Original Hot Sauce 8 oz"


def test_unmapped_brand_gets_a_stable_placeholder_never_its_own_name():
    first = anonymize.brand_alias("Brand Nobody Mapped")
    assert first.startswith("Competitor ")
    assert "Nobody" not in first
    assert anonymize.brand_alias("brand nobody mapped ") == first
    assert "Nobody" not in anonymize.product_alias("Brand Nobody Mapped", "Brand Nobody Mapped Fancy Sauce 7 oz")


def test_pack_size_is_kept_when_product_is_renamed():
    assert anonymize.product_alias("Competitor B", "Competitor B Black Truffle Hot Sauce 6 oz") == "Marrowgate Black Garlic Hot Sauce 6 oz"


def test_retailer_sites_become_role_labels():
    assert anonymize.retailer_label("walmart") == "Mass retailer site"
    assert anonymize.retailer_label("Amazon") == "Online marketplace"
    assert anonymize.retailer_label("some-new-site") == "Retailer site"


def test_every_query_that_returns_names_is_wrapped():
    src = (ROOT / "app" / "data.py").read_text(encoding="utf-8")
    for block in re.split(r"\n(?=@cache\.memoize)", src)[1:]:
        if re.search(r"AS brand_name|v\.brand_name|rl\.retailer|v\.retailer", block) and "pd.read_sql" in block:
            assert block.split("\n")[1] == "@_public_names", block.split("\n")[2]


def test_no_source_name_is_hard_coded_in_the_dashboard():
    for path in (ROOT / "app").rglob("*.py"):
        if path.name == "anonymize.py":
            continue
        assert not SOURCE_NAMES.search(path.read_text(encoding="utf-8")), path


def test_aliases_are_distinct_and_not_source_names():
    aliases = list(anonymize.BRAND_ALIASES.values())
    assert len(set(aliases)) == len(aliases)
    assert not any(SOURCE_NAMES.search(a) for a in aliases)
