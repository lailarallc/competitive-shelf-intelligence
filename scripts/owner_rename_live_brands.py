"""OWNER-RUN ONLY. Rename the live database's real competitor brands to Competitor A-F; delete what was really scraped.

No session runs this script: it writes the production database behind https://competitive.lailarallc.com. The owner
runs it from their own terminal with their own credentials.

What it does, in one transaction:
  - Finds every brand whose name the brand-name gate denies (scripts/check_brand_names.py) and maps it to the
    fictional letter the seeding script gives it. A denied brand with no letter stops the run before any write.
  - Splits each such brand's price snapshots by origin. A synthetic row is one the seeding scripts wrote: stamped at
    midnight UTC, with no sale-badge text and no HTML hash. Anything else came from a real scrape (scrape.py stamps
    now()). Real-scrape rows are deleted, since the demo says its data is synthetic; synthetic rows are kept.
  - Renames the brand, its products (to the seeding script's fictional product name) and its listings (to the
    seeding script's invented IDs and synthetic: URLs). A listing or product left with no rows is deleted.
  - Deletes scrape failures that hold those listings' real URLs, and clears a product-map note that names a brand.
  - Checks, before it commits, that no denied name is left in any text column it can reach. If one is, it rolls back.

    fly proxy 15432:5432 -a competitive-shelf-pg          # in another terminal
    (set DATABASE_URL to the proxied database, as you normally do)
    python scripts/owner_rename_live_brands.py            # dry run: rows by brand and origin, and the plan
    python scripts/owner_rename_live_brands.py --apply    # backup to backups/, the plan, a typed confirm, the write

The backup is a CSV per table under backups/csi-<UTC time>/, row counts checked against the tables before any write.
To restore one: psql's \\copy <table> FROM '<file>' CSV HEADER, after truncating it.
"""
from __future__ import annotations

import ast
import csv
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_brand_names import DENIED, _h, _norm, denied  # noqa: E402

LOADER = ROOT / "scripts" / "load_synthetic_competitors.py"
#: The seeding script's fictional letter for each real brand it once used, keyed by the hash of the normalized name.
LETTERS = {
    "1f76b0e5058f716c3026eeb07599915e84f2c6de83fee6d1754d55f008689cc0": "A",
    "2c7b1d1257a0455b86098429887cb443fb2ad7c11eb0cbfd9465a9975218298a": "B",
    "07b53bfa71fe2eb03d8ca62be5ec1757758615b1f897ef54449b8669291a5693": "C",
    "b10d5ca2d777fed111caa0d12cd9c4573a9a9ec7f370941b4d69bdf233531ee2": "D",
    "6d629b2d75351871327e773597bfe8a836ec80966565960f657018ee21a1b150": "E",
    "6ec19edc62367fc3b82ca555c346a55c29eb7aca11df4d9541fd2f836fb2fb06": "E",
    "4a59f44e6e8fdef0b7af84978d22754ca7182e28d769452a198dcd1b505dd361": "F",
}
TABLES = ("brands", "products", "retailer_listings", "price_snapshots", "scrape_runs", "scrape_failures",
          "canonical_product_map")
ORIGIN = ("CASE WHEN ps.raw_html_hash IS NULL AND ps.sale_badge_text IS NULL AND "
          "ps.scraped_at = date_trunc('day', ps.scraped_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
          "THEN 'synthetic' ELSE 'scraped' END")
SHORT = {"walmart": "WM", "amazon": "AZ"}


def roster(path: Path = LOADER) -> dict[str, str]:
    """Letter -> the seeding script's fictional product name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "_COMPETITORS" for t in node.targets):
            out = {}
            for d in node.value.elts:
                e = {ast.literal_eval(k): ast.literal_eval(v) for k, v in zip(d.keys, d.values)}
                out[e["brand"].removeprefix("Competitor ")] = e["name"]
            return out
    raise SystemExit(f"{path}: no _COMPETITORS list")


def letter_for(name: str, letters: dict[str, str]) -> str | None:
    words = _norm(name)
    runs = words + [" ".join(words[i:i + n]) for n in (2, 3) for i in range(len(words) - n + 1)]
    hits = {letters[_h(r)] for r in runs if _h(r) in letters}
    return hits.pop() if len(hits) == 1 else None


def plan(cur, letters: dict[str, str], deny: frozenset[str], names: dict[str, str]) -> dict:
    """Read only. Everything the write will do, and the report by brand and origin."""
    cur.execute("SELECT id, canonical_name FROM brands ORDER BY id")
    brands = cur.fetchall()
    real = [(bid, name, letter_for(name, letters)) for bid, name in brands if denied(name, deny)]
    stops = [f"brand {name!r} is denied but has no fictional letter" for _, name, letter in real if not letter]
    taken = {name for _, name in brands}
    stops += [f"brand 'Competitor {letter}' already exists; this script does not merge brands"
              for _, _, letter in real if letter and f"Competitor {letter}" in taken]
    if len({letter for _, _, letter in real}) != len(real):
        stops.append("two real brands map to one letter")
    ids = [bid for bid, _, _ in real] or [-1]
    cur.execute(f"""
        SELECT b.id, rl.retailer, {ORIGIN} AS origin, count(*), min(ps.scraped_date), max(ps.scraped_date)
        FROM price_snapshots ps JOIN retailer_listings rl ON rl.id = ps.listing_id
        JOIN products p ON p.id = rl.product_id JOIN brands b ON b.id = p.brand_id
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""")
    report = cur.fetchall()
    cur.execute(f"""
        SELECT p.brand_id, p.id, rl.id, rl.retailer,
               count(ps.id) FILTER (WHERE {ORIGIN} = 'synthetic'), count(ps.id) FILTER (WHERE {ORIGIN} = 'scraped')
        FROM products p LEFT JOIN retailer_listings rl ON rl.product_id = p.id
        LEFT JOIN price_snapshots ps ON ps.listing_id = rl.id
        WHERE p.brand_id = ANY(%s) GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3""", (ids,))
    rows = cur.fetchall()
    letter_of = {bid: letter for bid, _, letter in real}
    keep_listing, drop_listing, product_syn = {}, [], {}
    for bid, pid, lid, retailer, syn, _scr in rows:
        product_syn.setdefault(pid, [bid, 0])[1] += syn
        if lid is None:
            continue
        if syn:
            keep_listing.setdefault((bid, retailer), []).append((syn, lid, pid))
        else:
            drop_listing.append(lid)
    kept_products = {pid for v in keep_listing.values() for _, _, pid in v}
    drop_product = [pid for pid in product_syn if pid not in kept_products]
    product_names, by_brand = {}, {}
    for pid in kept_products:
        bid, syn = product_syn[pid]
        by_brand.setdefault(bid, []).append((-syn, pid))
    for bid, ps in by_brand.items():
        base = names.get(letter_of[bid], f"Competitor {letter_of[bid]} product")
        for n, (_, pid) in enumerate(sorted(ps)):
            product_names[pid] = base if n == 0 else f"{base} (variant {n + 1})"
    listing_ids = {}
    for (bid, retailer), ls in keep_listing.items():
        for n, (_, lid, _) in enumerate(sorted(ls, key=lambda x: (-x[0], x[1]))):
            rid = f"CSI-{SHORT.get(retailer, retailer.upper())}-{letter_of[bid]}" + ("" if n == 0 else f"-{n + 1}")
            listing_ids[lid] = (rid, f"synthetic:{retailer}/{rid}")
    cur.execute(f"""
        SELECT count(*) FROM price_snapshots ps JOIN retailer_listings rl ON rl.id = ps.listing_id
        JOIN products p ON p.id = rl.product_id WHERE p.brand_id = ANY(%s) AND {ORIGIN} = 'scraped'""", (ids,))
    scraped = cur.fetchone()[0]
    return {"brands": brands, "real": real, "stops": stops, "report": report, "scraped": scraped,
            "drop_listing": drop_listing, "drop_product": drop_product, "product_names": product_names,
            "listing_ids": listing_ids, "brand_ids": ids}


def print_plan(p: dict) -> None:
    name = {bid: n for bid, n in p["brands"]}
    new = {bid: f"Competitor {letter}" for bid, _, letter in p["real"] if letter}
    print("Snapshots by brand, retailer and origin (every brand in the database):")
    print(f"  {'brand':<34} {'becomes':<14} {'retailer':<10} {'origin':<10} {'rows':>6}  first       last")
    for bid, retailer, origin, n, first, last in p["report"]:
        print(f"  {name[bid][:34]:<34} {new.get(bid, '(unchanged)'):<14} {retailer:<10} {origin:<10} {n:>6}  "
              f"{first}  {last}")
    print(f"\nReal brands found: {len(p['real'])}")
    for bid, n, letter in p["real"]:
        print(f"  {n!r} -> {'Competitor ' + letter if letter else 'NO LETTER'}")
    print(f"Really-scraped snapshots to delete: {p['scraped']}")
    print(f"Products to rename: {len(p['product_names'])}; to delete (no synthetic rows left): {len(p['drop_product'])}")
    print(f"Listings to rename: {len(p['listing_ids'])}; to delete (no synthetic rows left): {len(p['drop_listing'])}")
    for s in p["stops"]:
        print(f"STOP: {s}")


def backup(cur, out: Path) -> dict[str, int]:
    out.mkdir(parents=True)
    counts = {}
    for t in TABLES:
        buf = io.StringIO()
        cur.copy_expert(f"COPY {t} TO STDOUT WITH CSV HEADER", buf)
        (out / f"{t}.csv").write_text(buf.getvalue(), encoding="utf-8")
        with open(out / f"{t}.csv", encoding="utf-8", newline="") as f:
            written = sum(1 for _ in csv.reader(f)) - 1
        cur.execute(f"SELECT count(*) FROM {t}")
        live = cur.fetchone()[0]
        if written != live:
            raise SystemExit(f"backup of {t}: {written} rows written, {live} in the table; nothing changed")
        counts[t] = live
    return counts


def apply(cur, p: dict) -> None:
    ids = p["brand_ids"]
    real_listings = """SELECT rl.id FROM retailer_listings rl JOIN products pr ON pr.id = rl.product_id
                       WHERE pr.brand_id = ANY(%s)"""
    cur.execute(f"""DELETE FROM price_snapshots ps USING retailer_listings rl, products pr
                    WHERE rl.id = ps.listing_id AND pr.id = rl.product_id AND pr.brand_id = ANY(%s)
                    AND {ORIGIN} = 'scraped'""", (ids,))
    cur.execute(f"DELETE FROM scrape_failures WHERE listing_id IN ({real_listings})", (ids,))
    drop_l, drop_p = p["drop_listing"] or [-1], p["drop_product"] or [-1]
    cur.execute("UPDATE canonical_product_map SET walmart_listing_id = NULL WHERE walmart_listing_id = ANY(%s)", (drop_l,))
    cur.execute("UPDATE canonical_product_map SET amazon_listing_id = NULL WHERE amazon_listing_id = ANY(%s)", (drop_l,))
    cur.execute("DELETE FROM canonical_product_map WHERE canonical_product_id = ANY(%s)", (drop_p,))
    cur.execute("DELETE FROM price_snapshots WHERE listing_id = ANY(%s)", (drop_l,))
    cur.execute("DELETE FROM retailer_listings WHERE id = ANY(%s)", (drop_l,))
    cur.execute("DELETE FROM retailer_listings WHERE product_id = ANY(%s)", (drop_p,))
    cur.execute("DELETE FROM products WHERE id = ANY(%s)", (drop_p,))
    for lid, (rid, url) in p["listing_ids"].items():
        cur.execute("UPDATE retailer_listings SET retailer_id = %s, product_url = %s WHERE id = %s", (rid, url, lid))
    for pid, pname in p["product_names"].items():
        cur.execute("UPDATE products SET canonical_name = %s, pack_size_raw = %s, upc = NULL WHERE id = %s",
                    (pname, pname, pid))
    for bid, _, letter in p["real"]:
        cur.execute("UPDATE brands SET canonical_name = %s WHERE id = %s", (f"Competitor {letter}", bid))


def leftovers(cur, deny: frozenset[str]) -> list[str]:
    """Every text value the database holds about a brand, product or listing that a denied name is still in."""
    bad = []
    for sql in ("SELECT 'brands', canonical_name FROM brands",
                "SELECT 'products', canonical_name || ' ' || coalesce(pack_size_raw, '') FROM products",
                "SELECT 'retailer_listings', retailer_id || ' ' || product_url FROM retailer_listings",
                "SELECT 'scrape_failures', url || ' ' || error_message FROM scrape_failures",
                "SELECT 'canonical_product_map', coalesce(note, '') FROM canonical_product_map",
                "SELECT DISTINCT 'price_snapshots', sale_badge_text FROM price_snapshots WHERE sale_badge_text IS NOT NULL"):
        cur.execute(sql)
        bad += [f"{t}: {v!r}" for t, v in cur.fetchall() if denied(v, deny)]
    return bad


def run(conn, do_apply: bool, letters: dict[str, str] = LETTERS, deny: frozenset[str] = DENIED,
        names: dict[str, str] | None = None, backups: Path = ROOT / "backups", ask=input) -> int:
    names = roster() if names is None else names
    with conn.cursor() as cur:
        p = plan(cur, letters, deny, names)
        print_plan(p)
        if p["stops"]:
            conn.rollback()
            return 2
        if not p["real"]:
            print("\nNo real brand in the database. Nothing to do.")
            conn.rollback()
            return 0
        if not do_apply:
            print("\nDry run: nothing written. Re-run with --apply to back up and write.")
            conn.rollback()
            return 0
        out = backups / f"csi-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        counts = backup(cur, out)
        print(f"\nBackup: {out} ({', '.join(f'{t} {n}' for t, n in counts.items())})")
        phrase = f"rename {len(p['real'])} brands"
        if ask(f"Type '{phrase}' to write, anything else to stop: ").strip() != phrase:
            print("Stopped: nothing written.")
            conn.rollback()
            return 1
        apply(cur, p)
        left = leftovers(cur, deny)
        if left:
            conn.rollback()
            print("Rolled back: a denied name is still in the database:", *left, sep="\n  ")
            return 1
        conn.commit()
        print("Written. Re-run without --apply: it should find no real brand.")
    return 0


def main(argv: list[str]) -> int:
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    conn = psycopg2.connect(url)
    try:
        if "--apply" not in argv:
            conn.set_session(readonly=True)
        return run(conn, "--apply" in argv)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
