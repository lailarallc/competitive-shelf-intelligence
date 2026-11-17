"""The owner's one-line live rename (scripts/owner_rename_live.ps1), run end to end against a throwaway database and
this repo's own app served locally. Never production: -NoProxy points it at the test database.

The seeding scripts fill the database; two of the fictional brands are then renamed to invented stand-ins, which
CSI_TEST_PROBE=1 adds to the denylist, so the database looks as the live one does (real names on synthetic rows)
and no file here prints a real name. Needs CSI_TEST_DATABASE_URL (see test_owner_rename_live_brands.py), Windows
PowerShell and Playwright's Chromium. About a minute. The cache-clear step (flyctl ssh) is not exercised: the app
here caches to a temp folder this test empties instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import pytest

URL = os.environ.get("CSI_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not URL or not shutil.which("powershell"),
                                reason="CSI_TEST_DATABASE_URL not set, or no Windows PowerShell")
APP_PORT = 8057


def _sql(sql: str):
    import psycopg2

    c = psycopg2.connect(URL)
    try:
        with c.cursor() as cur:
            cur.execute(sql)
            out = cur.fetchall() if cur.description else None
        c.commit()
        return out
    finally:
        c.close()


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("live")
    _sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    _sql((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
    env = {**os.environ, "DATABASE_URL": URL, "PYTHONPATH": str(ROOT)}
    for mod in ("scripts.load_synthetic_competitors", "scripts.load_synthetic"):
        subprocess.run([sys.executable, "-m", mod], cwd=ROOT, env=env, check=True, capture_output=True)
    # What the live database holds: real names on synthetic rows, and one real-scrape row.
    _sql("""UPDATE brands SET canonical_name = 'Zeta Sauce Co' WHERE canonical_name = 'Competitor A';
            UPDATE brands SET canonical_name = 'Quill' WHERE canonical_name = 'Competitor B';
            UPDATE products SET canonical_name = replace(canonical_name, 'Competitor A', 'Zeta Sauce Co'),
                                pack_size_raw = replace(pack_size_raw, 'Competitor A', 'Zeta Sauce Co');
            UPDATE products SET canonical_name = replace(canonical_name, 'Competitor B', 'Quill'),
                                pack_size_raw = replace(pack_size_raw, 'Competitor B', 'Quill');
            INSERT INTO price_snapshots (listing_id, scraped_at, scraped_date, price_cents)
              SELECT rl.id, timestamptz '2020-05-28 14:03:22+00', date '2020-05-28', 897
              FROM retailer_listings rl WHERE rl.retailer_id = 'CSI-AZ-A';""")
    u = urlsplit(URL)
    (tmp / ".env").write_text(f"DATABASE_URL={URL}\n", encoding="utf-8")
    cache = tmp / "cache"
    cache.mkdir()
    app = subprocess.Popen([sys.executable, "-c", f"from app.run import app; app.run(port={APP_PORT})"], cwd=ROOT,
                           env={**env, "CACHE_DIR": str(cache)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/health", timeout=2).read()
                break
            except Exception:
                time.sleep(1)
        yield {"env_file": tmp / ".env", "port": u.port, "cache": cache}
    finally:
        app.terminate()
        app.wait(timeout=20)


def wrapper(live, *flags, answer="rename 2 brands"):
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "owner_rename_live.ps1"),
           "-NoProxy", "-Port", str(live["port"]), "-Url", f"http://127.0.0.1:{APP_PORT}",
           "-EnvFile", str(live["env_file"]), "-NoCacheClear", *flags]
    r = subprocess.run(cmd, input=answer + "\n", capture_output=True, text=True, timeout=600,
                       env={**os.environ, "CSI_TEST_PROBE": "1"})
    for f in live["cache"].iterdir():  # what the live run's cache clear does
        f.unlink()
    return r.returncode, r.stdout + r.stderr


def brands():
    return sorted(n for (n,) in _sql("SELECT canonical_name FROM brands"))


def test_1_the_page_check_fails_while_the_page_shows_a_real_name(live):
    code, out = wrapper(live, "-PageOnly")
    assert code == 1 and "FAIL" in out and "names a real brand" in out, out


def test_2_a_wrong_answer_writes_nothing_and_skips_the_page_check(live):
    code, out = wrapper(live, answer="no")
    assert code == 1, out
    assert "Stopped: nothing written." in out and "Live page name check" not in out
    assert "Zeta Sauce Co" in brands()


def test_3_the_full_run_plans_backs_up_writes_and_the_page_passes(live):
    code, out = wrapper(live)
    for line in ("rows  first", "Real brands found: 2", "Really-scraped snapshots to delete: 1", "Backup:",
                 "Written: the transaction committed", "Live page name check", "PASS"):
        assert line in out, (line, out)
    assert code == 0, out
    assert "Competitor A" in brands() and "Zeta Sauce Co" not in brands()
    assert "DATABASE_URL" not in out and urlsplit(URL).password not in out  # the DSN never prints


def test_4_a_second_run_finds_nothing_and_still_passes(live):
    code, out = wrapper(live)
    assert code == 0 and "No real brand in the database. Nothing to do." in out and "PASS" in out, out
