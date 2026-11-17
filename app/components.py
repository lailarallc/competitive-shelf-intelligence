"""Reusable Dash components — adapted from retail-velocity-decision-tool."""

from __future__ import annotations

import os
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback_context, dcc, html

from app.constants import (
    CANVAS, CHICAGO, DATE_RANGE_DEFAULT, DATE_RANGE_OPTIONS,
    FONT_SANS, GREY_LIGHT, RED, TEXT, TEXT_SEC,
)


def chart_footnote(text: str) -> html.Div:
    """Source / methodology footnote placed under a chart.

    The design system requires a footnote under every chart. The "as of" scrape
    date is shown separately by last_scraped_indicator at the top of each tab.
    """
    return html.Div(
        text,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": "11px",
            "fontStyle": "italic",
            "color": TEXT_SEC,
            "marginTop": "12px",
        },
    )


def demo_data_banner() -> html.Div:
    """Visible disclosure that the dashboard runs on a demonstration dataset.

    Competitor prices, promotions, out-of-stock events, and the staged
    assortment changes are synthetic — modeled on public product pages, not
    live scraped figures. Shown on every tab so no reader mistakes the demo
    for live competitive data.
    """
    return html.Div(
        [
            html.Span(
                "Demonstration data",
                style={"fontWeight": "700", "color": CHICAGO, "marginRight": "8px"},
            ),
            html.Span(
                "Competitor prices, promotions, out-of-stock events, and "
                "assortment changes shown here are a synthetic dataset, "
                "not live scraped figures. Competitor brand names are invented "
                "and the two retailer sites are shown as role labels. The scraper "
                "is built and tested on saved pages. It is not running on this demo.",
                style={"color": TEXT},
            ),
        ],
        style={
            "backgroundColor": "#e8eaf4",   # Chicago-95 info surface
            "border": "1px solid #8e9ad0",  # Chicago-70
            "borderRadius": "2px",
            "padding": "10px 16px",
            "fontSize": "13px",
            "fontFamily": FONT_SANS,
            "margin": "16px 0 0",
        },
    )


def metric_card(label: str, value: str, delta: str | None = None) -> html.Div:
    children = [
        html.Div(label, style={"fontSize": "13px", "color": TEXT_SEC, "marginBottom": "4px"}),
        html.Div(value, style={"fontSize": "28px", "fontWeight": "700", "fontFamily": FONT_SANS}),
    ]
    if delta:
        children.append(html.Div(delta, style={"fontSize": "13px", "color": TEXT_SEC}))
    return html.Div(
        children,
        style={
            "background": CANVAS,
            "border": f"1px solid {GREY_LIGHT}",
            "borderRadius": "2px",
            "padding": "16px 20px",
            "minWidth": "140px",
        },
    )


def last_scraped_indicator() -> html.Div:
    """Shows the most recent completed scrape run timestamp (R15).

    Queries lazily at render time so it reflects the actual DB state.
    """
    from app.anonymize import retailer_label
    from app.data import get_last_scraped
    info = get_last_scraped()
    ts = info.get("completed_at")
    retailer = info.get("retailer", "")

    if ts is None:
        text = "Demo data: none loaded yet"
    else:
        if isinstance(ts, datetime):
            formatted = ts.strftime(f"%B {ts.day}, %Y")
        else:
            formatted = str(ts)[:10]
        label = retailer_label(retailer)
        text = f"Demo data through: {formatted} ({label})"

    return html.Div(
        text,
        style={"fontSize": "12px", "color": TEXT_SEC, "marginTop": "6px"},
    )


def error_card(title: str, message: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.H5(title, style={"color": RED, "fontWeight": "600"}),
            html.P(message, style={"color": TEXT_SEC}),
        ]),
        style={"border": f"1px solid {RED}", "borderRadius": "2px"},
    )


def empty_state(message: str) -> html.Div:
    return html.Div(
        [
            html.Div("—", style={"fontSize": "32px", "color": GREY_LIGHT, "marginBottom": "8px"}),
            html.P(message, style={"fontSize": "14px", "color": TEXT_SEC, "margin": "0"}),
        ],
        style={
            "textAlign": "center",
            "padding": "60px 20px",
            "border": f"1px dashed {GREY_LIGHT}",
            "borderRadius": "2px",
            "backgroundColor": CANVAS,
        },
    )


def _toggle_btn_style(selected: bool) -> dict:
    return {
        "fontFamily": FONT_SANS,
        "fontSize": "13px",
        "fontWeight": "500",
        "padding": "4px 12px",
        "borderRadius": "2px",
        "border": f"1px solid {CHICAGO if selected else GREY_LIGHT}",
        "backgroundColor": CHICAGO if selected else CANVAS,
        "color": "#ffffff" if selected else TEXT_SEC,
        "cursor": "pointer",
        "outline": "none",
    }


def date_range_toggles(id_prefix: str) -> html.Div:
    store_id = f"{id_prefix}-date-range"
    return html.Div([
        dcc.Store(id=store_id, data=DATE_RANGE_DEFAULT),
        html.Div(
            [
                html.Button(
                    opt["label"],
                    id=f"{id_prefix}-btn-{opt['value']}",
                    n_clicks=0,
                    style=_toggle_btn_style(opt["value"] == DATE_RANGE_DEFAULT),
                )
                for opt in DATE_RANGE_OPTIONS
            ],
            style={"display": "flex", "gap": "4px", "marginBottom": "16px"},
        ),
    ])


def register_date_range_callbacks(app, id_prefix: str) -> None:
    store_id = f"{id_prefix}-date-range"
    btn_ids = [f"{id_prefix}-btn-{opt['value']}" for opt in DATE_RANGE_OPTIONS]
    values = [opt["value"] for opt in DATE_RANGE_OPTIONS]

    @app.callback(
        Output(store_id, "data"),
        *[Output(bid, "style") for bid in btn_ids],
        *[Input(bid, "n_clicks") for bid in btn_ids],
        prevent_initial_call=True,
    )
    def toggle(*_n_clicks):
        ctx = callback_context
        if not ctx.triggered or ctx.triggered[0]["prop_id"] == ".":
            active = DATE_RANGE_DEFAULT
        else:
            triggered = ctx.triggered[0]["prop_id"].split(".")[0]
            for opt in DATE_RANGE_OPTIONS:
                if triggered == f"{id_prefix}-btn-{opt['value']}":
                    active = opt["value"]
                    break
            else:
                active = DATE_RANGE_DEFAULT
        styles = [_toggle_btn_style(v == active) for v in values]
        return (active, *styles)
