"""Tests for src/utils.py — pack weight parsing."""

import pytest

from src.utils import parse_weight_oz


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("16 oz", 16.0),
        ("9.8 oz", 9.8),
        ("12oz", 12.0),
        ("1 lb", 16.0),
        ("1.5 lbs", 24.0),
        ("500g", pytest.approx(17.637, abs=0.01)),
        ("500 g", pytest.approx(17.637, abs=0.01)),
        ("1 kg", pytest.approx(35.274, abs=0.01)),
        ("12 fl oz", 12.0),
        ("12 fl. oz", 12.0),
        ("250 ml", pytest.approx(8.454, abs=0.01)),
        ("1 liter", pytest.approx(33.814, abs=0.01)),
    ],
)
def test_parses_common_weight_units(raw, expected):
    assert parse_weight_oz(raw) == expected


def test_extracts_weight_from_product_title():
    title = "Competitor A Agave Sriracha Hot Sauce 9.8 oz"
    assert parse_weight_oz(title) == 9.8


def test_returns_none_when_no_weight_found():
    assert parse_weight_oz("No weight information here") is None


def test_returns_none_for_empty_string():
    assert parse_weight_oz("") is None


def test_returns_none_for_none_input():
    assert parse_weight_oz(None) is None


def test_case_insensitive():
    assert parse_weight_oz("16 OZ") == 16.0
    assert parse_weight_oz("1 LB") == 16.0
