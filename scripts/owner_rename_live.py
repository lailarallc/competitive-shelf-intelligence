"""OWNER-RUN ONLY: the live rename end to end. scripts/owner_rename_live.ps1 opens the Fly proxy and runs this.

  1. Reads DATABASE_URL from this repo's .env inside this process and points it at the proxy (127.0.0.1:<port>,
     same user, password and database). Nothing prints it.
  2. scripts/owner_rename_live_brands.py: the plan (rows by brand, retailer and origin; what is renamed, deleted,
     merged), the CSV backup read back against the table counts, the typed confirm, one transaction, a rollback if a
     real name survives.
  3. Clears the live app's query cache (an hour long, on its volume) so the page reads the renamed rows now.
  4. scripts/check_live_page.py against the live page: PASS or FAIL.

    python scripts/owner_rename_live.py --port 15433 [--url URL] [--env-file PATH] [--no-cache-clear] [--page-only]

Exit 0 only when the page check passes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_live_page  # noqa: E402
import owner_rename_live_brands as orl  # noqa: E402
from check_brand_names import PROBE_LETTERS, deny_set  # noqa: E402

APP = "competitive-shelf-intelligence"


def proxied_dsn(env_file: Path, port: int) -> str:
    from dotenv import dotenv_values

    url = dotenv_values(env_file).get("DATABASE_URL")
    if not url:
        raise SystemExit(f"No DATABASE_URL in {env_file}. Nothing changed.")
    u = urlsplit(url)
    auth = u.netloc.rsplit("@", 1)[0] + "@" if "@" in u.netloc else ""
    query = [(k, v) for k, v in parse_qsl(u.query) if k != "sslmode"] + [("sslmode", "prefer")]
    return urlunsplit((u.scheme, f"{auth}127.0.0.1:{port}", u.path, urlencode(query), ""))


def clear_cache(url: str) -> bool:
    """Wake the app, then empty its cache volume. False when it could not."""
    # Cloudflare in front of the app answers Python's default user agent with 403 (2026-11-17), so the request never
    # reached the app and flyctl ssh found no started machine. A browser user agent gets through.
    req = urllib.request.Request(url.rstrip("/") + "/health", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; "
                                 "Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        print(f"  could not wake the app: {e}")
    r = subprocess.run(["flyctl", "ssh", "console", "-a", APP, "-C", "find /cache -mindepth 1 -delete"],
                       capture_output=True, text=True)
    if r.returncode:
        print(f"  flyctl ssh failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.returncode == 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--url", default=check_live_page.URL)
    p.add_argument("--env-file", type=Path, default=ROOT / ".env")
    p.add_argument("--no-cache-clear", action="store_true")
    p.add_argument("--page-only", action="store_true")
    args = p.parse_args(argv)
    deny = deny_set()
    letters = {**orl.LETTERS, **(PROBE_LETTERS if deny != orl.DENIED else {})}

    if not args.page_only:
        import psycopg2

        print("== 1-2. The database: plan, backup, confirm, write ==")
        conn = psycopg2.connect(proxied_dsn(args.env_file, args.port))
        try:
            code = orl.run(conn, True, letters=letters, deny=deny)
        finally:
            conn.close()
        if code:
            print("Stopped before the page check: the database was not changed (see above).")
            return code
        if not args.no_cache_clear:
            print("\n== 3. The live app's cache ==")
            if clear_cache(args.url):
                print("  cleared")
            else:
                print("  NOT cleared: the page may show cached rows for up to an hour. Re-run the page check then:\n"
                      "  powershell -ExecutionPolicy Bypass -File scripts\\owner_rename_live.ps1 -PageOnly")

    print("\n== 4. The name check against the live page ==")
    return check_live_page.main([args.url])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
