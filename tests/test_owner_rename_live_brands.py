"""The owner-run live rename, tested against a throwaway Postgres (never the live database).

Runs only when CSI_TEST_DATABASE_URL names a scratch database: each test drops and rebuilds its public schema.
The real brands are stood in for by invented ones, hashed the same way, so this public file names none.

    docker run -d --rm --name csi-test-pg -e POSTGRES_PASSWORD=<pick one> -p 55499:5432 postgres:16-alpine
    then set CSI_TEST_DATABASE_URL to that container's URL (user postgres, port 55499) and run this file.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

import scripts.owner_rename_live_brands as orl
from scripts.check_brand_names import DENIED, _h

URL = os.environ.get("CSI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CSI_TEST_DATABASE_URL not set")
SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
LETTERS = {_h("zeta sauce co"): "A", _h("quill"): "B"}
DENY = frozenset(LETTERS) | {_h("orphan brand")}
NAMES = {"A": "Competitor A Agave Sriracha Hot Sauce 9.8 oz", "B": "Competitor B Black Truffle Hot Sauce 6 oz"}


@pytest.fixture
def conn():
    import psycopg2

    c = psycopg2.connect(URL)
    with c.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
        cur.execute("""
            INSERT INTO brands (id, canonical_name) VALUES (1, 'Zeta Sauce Co'), (2, 'Quill'), (3, 'Cinderhaven');
            INSERT INTO products (id, brand_id, canonical_name, pack_size_raw, pack_weight_oz, upc) VALUES
              (10, 1, 'Zeta Sauce Co Blue Agave 9.8 oz', 'Zeta Sauce Co Blue Agave 9.8 oz', 9.8, '123'),
              (11, 1, 'Zeta Sauce Co Serrano 9.8 oz', 'Zeta Sauce Co Serrano 9.8 oz', 9.8, NULL),
              (20, 2, 'QUILL Black Truffle 6 oz', 'QUILL Black Truffle 6 oz', 6, NULL),
              (30, 3, 'Cinderhaven Original 8 oz', 'Cinderhaven Original 8 oz', 8, NULL);
            INSERT INTO retailer_listings (id, product_id, retailer, retailer_id, product_url) VALUES
              (100, 10, 'walmart', '794', 'https://www.walmart.com/ip/Zeta-Sauce-Co-Agave/794'),
              (101, 10, 'amazon', 'B01X', 'https://www.amazon.com/Zeta-Sauce-Co/dp/B01X'),
              (110, 11, 'amazon', 'B02X', 'https://www.amazon.com/Zeta-Sauce-Co-Serrano/dp/B02X'),
              (200, 20, 'walmart', '620', 'https://www.walmart.com/ip/QUILL/620'),
              (300, 30, 'synthetic', 'CIN-1', 'synthetic://cinderhaven/1');
            INSERT INTO scrape_runs (id, retailer, status) VALUES (1, 'amazon', 'complete');
            INSERT INTO scrape_failures (scrape_run_id, listing_id, retailer, url, error_message)
              VALUES (1, 110, 'amazon', 'https://www.amazon.com/Zeta-Sauce-Co-Serrano/dp/B02X', 'captcha');
        """)
        for lid in (100, 101, 200, 300):  # synthetic: midnight UTC, no badge text, no hash
            cur.execute("""INSERT INTO price_snapshots (listing_id, scraped_at, scraped_date, price_cents)
                           SELECT %s, d::timestamp AT TIME ZONE 'UTC', d, 749
                           FROM generate_series(date '2026-06-01', date '2026-06-10', '1 day') d""", (lid,))
        cur.execute("""INSERT INTO price_snapshots (listing_id, scrape_run_id, scraped_at, scraped_date, price_cents)
                       VALUES (101, 1, timestamptz '2026-05-28 14:03:22+00', date '2026-05-28', 897),
                              (110, 1, timestamptz '2026-05-28 14:05:10+00', date '2026-05-28', 899)""")
    c.commit()
    yield c
    c.close()


def counts(conn):
    with conn.cursor() as cur:
        out = {}
        for t in orl.TABLES:
            cur.execute(f"SELECT count(*) FROM {t}")
            out[t] = cur.fetchone()[0]
    conn.rollback()
    return out


def go(conn, tmp_path, do_apply, answer="rename 2 brands", **kw):
    args = {"letters": LETTERS, "deny": DENY, "names": NAMES, "backups": tmp_path, "ask": lambda _: answer, **kw}
    return orl.run(conn, do_apply, **args)


def test_the_test_letters_and_the_shipped_ones_are_denied():
    assert set(orl.LETTERS) <= DENIED
    assert set(orl.roster()) == {"A", "B", "C", "D", "E", "F"}


def test_the_dry_run_reports_origin_and_writes_nothing(conn, tmp_path, capsys):
    before = counts(conn)
    assert go(conn, tmp_path, False) == 0
    out = capsys.readouterr().out
    assert counts(conn) == before and not list(tmp_path.iterdir())
    assert "Really-scraped snapshots to delete: 2" in out
    assert "Products to rename: 2; to delete (no synthetic rows left): 1" in out
    assert "Listings to rename: 3; to delete (no synthetic rows left): 1" in out
    assert "scraped" in out and "Cinderhaven" in out


def test_a_wrong_answer_writes_nothing_after_a_full_backup(conn, tmp_path):
    before = counts(conn)
    assert go(conn, tmp_path, True, answer="yes") == 1
    assert counts(conn) == before
    (bk,) = tmp_path.iterdir()
    for t, n in before.items():
        with open(bk / f"{t}.csv", encoding="utf-8", newline="") as f:
            assert sum(1 for _ in csv.reader(f)) - 1 == n


def test_apply_renames_the_synthetic_rows_and_deletes_the_scraped(conn, tmp_path):
    assert go(conn, tmp_path, True) == 0
    with conn.cursor() as cur:
        cur.execute("SELECT id, canonical_name FROM brands ORDER BY id")
        assert cur.fetchall() == [(1, "Competitor A"), (2, "Competitor B"), (3, "Cinderhaven")]
        cur.execute("SELECT id, canonical_name, upc FROM products ORDER BY id")
        assert cur.fetchall() == [(10, NAMES["A"], None), (20, NAMES["B"], None), (30, "Cinderhaven Original 8 oz", None)]
        cur.execute("SELECT id, retailer_id, product_url FROM retailer_listings ORDER BY id")
        assert cur.fetchall() == [(100, "CSI-WM-A", "synthetic:walmart/CSI-WM-A"),
                                  (101, "CSI-AZ-A", "synthetic:amazon/CSI-AZ-A"),
                                  (200, "CSI-WM-B", "synthetic:walmart/CSI-WM-B"),
                                  (300, "CIN-1", "synthetic://cinderhaven/1")]
        cur.execute("SELECT listing_id, count(*) FROM price_snapshots GROUP BY 1 ORDER BY 1")
        assert cur.fetchall() == [(100, 10), (101, 10), (200, 10), (300, 10)]
        cur.execute("SELECT count(*) FROM scrape_failures")
        assert cur.fetchone()[0] == 0
        assert orl.leftovers(cur, DENY) == []
    conn.rollback()
    assert go(conn, tmp_path, False) == 0  # a second run finds no real brand


def test_a_denied_brand_with_no_letter_stops_before_any_write(conn, tmp_path, capsys):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO brands (id, canonical_name) VALUES (4, 'Orphan Brand')")
    conn.commit()
    before = counts(conn)
    assert go(conn, tmp_path, True) == 2
    assert counts(conn) == before and not list(tmp_path.iterdir())
    assert "has no fictional letter" in capsys.readouterr().out


def test_a_name_left_anywhere_rolls_the_write_back(conn, tmp_path, capsys):
    with conn.cursor() as cur:
        cur.execute("UPDATE price_snapshots SET sale_badge_text = 'Zeta Sauce Co deal' "
                    "WHERE listing_id = 300 AND scraped_date = date '2026-06-01'")
    conn.commit()
    before = counts(conn)
    assert go(conn, tmp_path, True) == 1
    assert counts(conn) == before
    with conn.cursor() as cur:
        cur.execute("SELECT canonical_name FROM brands WHERE id = 1")
        assert cur.fetchone()[0] == "Zeta Sauce Co"
    conn.rollback()
    assert "Rolled back" in capsys.readouterr().out
