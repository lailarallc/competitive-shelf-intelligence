"""Dash app entry point.

Init order: load_dotenv → Dash → cache → layout → callbacks → health route.
Matches retail-velocity-decision-tool/app/run.py pattern exactly.
"""

from __future__ import annotations

import os
import pathlib
import secrets as _secrets

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

import dash_bootstrap_components as dbc
from dash import Dash
from flask import jsonify

from app.callbacks import register_callbacks
from app.data import cache, init_cache
from app.layout import create_layout
from lailara_frame import wrap

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Competitive Shelf Intelligence | Lailara LLC",
    update_title=None,
    meta_tags=[
        {"name": "description", "content": "Pricing, placement, and assortment movement across your retailers, every month, as a decision-ready brief."},
        {"property": "og:title", "content": "Competitive Shelf Intelligence"},
        {"property": "og:description", "content": "Pricing, placement, and assortment movement across your retailers, every month, as a decision-ready brief."},
        {"property": "og:type", "content": "website"},
        {"property": "og:url", "content": "https://competitive.lailarallc.com/"},
        {"property": "og:image", "content": "https://lailarallc.com/og/s/competitive.png"},
        {"property": "og:image:secure_url", "content": "https://lailarallc.com/og/s/competitive.png"},
        {"property": "og:image:type", "content": "image/png"},
        {"property": "og:image:width", "content": "1200"},
        {"property": "og:image:height", "content": "630"},
        {"property": "og:image:alt", "content": "Competitive Shelf Intelligence"},
        {"name": "twitter:card", "content": "summary_large_image"},
        {"name": "twitter:image", "content": "https://lailarallc.com/og/s/competitive.png"},
    ],
)
server = app.server
server.secret_key = os.environ.get("FLASK_SECRET_KEY") or _secrets.token_hex(32)
init_cache(server)

app.layout = wrap(
    create_layout(),
    tool_name="Competitive Shelf Intelligence",
    no_container=True,
    footer_note="Data: demonstration dataset modeled on public Walmart and Amazon product pages.",
)
register_callbacks(app)


@server.after_request
def _add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@server.route("/health")
def health():
    try:
        from app.db import get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
        return jsonify({"status": "ok"})
    except Exception:
        return jsonify({"status": "error"}), 503


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=debug, port=8050)
