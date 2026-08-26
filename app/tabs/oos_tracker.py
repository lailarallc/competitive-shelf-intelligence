"""OOS Tracker tab — heatmap of out-of-stock events + Cinderhaven lost-revenue callout."""

from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.charts import base_chart_layout
from app.components import chart_footnote, date_range_toggles, empty_state, last_scraped_indicator, register_date_range_callbacks
from app.constants import (
    CANVAS, COLOR_OOS, DATE_RANGE_DEFAULT, DATE_RANGE_OPTIONS,
    FONT_SANS, FONT_SERIF, GREY_LIGHT, INK, OWN_BRAND, RED, TEXT_SEC,
)

_ALLOWED_DAYS = frozenset(o["value"] for o in DATE_RANGE_OPTIONS)
from app.data import get_cinderhaven_oos_exposure, get_oos_events

TAB_ID = "tab-oos-tracker"
HEATMAP_ID = "oos-heatmap"
CALLOUT_ID = "oos-lost-revenue-callout"


def layout() -> html.Div:
    return html.Div([
        last_scraped_indicator(),
        html.P(
            "Out-of-stock events across brands and retailers.",
            className="ll-column",
            style={"fontSize": "14px", "color": TEXT_SEC, "marginBottom": "0"},
        ),
        html.Div([
            date_range_toggles("oos"),
            html.Div(id=CALLOUT_ID),
            dcc.Graph(id=HEATMAP_ID, config={"displayModeBar": False}),
            chart_footnote(
                "Source: demonstration dataset (Walmart and Amazon). A filled cell "
                "marks a day a listing was recorded out of stock. Estimated lost "
                "revenue is prorated by the share of the brand's SKUs out of stock."
            ),
        ], style={
            "backgroundColor": CANVAS,
            "border": f"1px solid {GREY_LIGHT}",
            "borderRadius": "2px",
            "padding": "24px",
            "marginTop": "20px",
        }),
    ], style={"paddingTop": "16px"})


def register_callbacks(app) -> None:
    register_date_range_callbacks(app, "oos")

    @app.callback(
        Output(HEATMAP_ID, "figure"),
        Output(CALLOUT_ID, "children"),
        Input("oos-date-range", "data"),
        Input("_refresh-trigger", "data"),
    )
    def update(days, _):
        days = int(days) if days is not None else DATE_RANGE_DEFAULT
        days = days if days in _ALLOWED_DAYS else DATE_RANGE_DEFAULT
        df = get_oos_events(days)
        heatmap = _build_heatmap(df) if not df.empty else _empty_fig("No OOS events in this window.")
        callout = _build_callout(days)
        return heatmap, callout


def _build_heatmap(df: pd.DataFrame) -> go.Figure:
    df["label"] = df["brand_name"] + " / " + df["product_name"].str[:30] + " (" + df["retailer"].str.title() + ")"
    labels = sorted(df["label"].unique())
    dates  = sorted(df["scraped_date"].unique())

    z, text = [], []
    for lbl in labels:
        row_df = df[df["label"] == lbl]
        active = set(str(d) for d in row_df["scraped_date"])
        z_row = [1 if str(d) in active else 0 for d in dates]
        z.append(z_row)
        text.append(["OOS" if v == 1 else "In Stock" for v in z_row])

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[str(d) for d in dates],
        y=labels,
        text=text,
        hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
        colorscale=[[0, CANVAS], [1, COLOR_OOS]],
        showscale=False,
        xgap=1, ygap=1,
    ))
    height = max(200, len(labels) * 32 + 80)
    layout = base_chart_layout(height=height, left_margin=260, x_title="Scrape Date")
    layout["yaxis"]["autorange"] = "reversed"
    fig.update_layout(**layout)
    return fig


def _build_callout(days: int) -> html.Div:
    try:
        daily_rate = float(os.environ.get("CINDERHAVEN_DAILY_REVENUE", 0))
    except (ValueError, TypeError):
        daily_rate = 0.0

    if daily_rate <= 0:
        return html.Div()

    exposure = get_cinderhaven_oos_exposure(days)
    oos_days = exposure["oos_days"]
    # Prorate by SKU share: a single-SKU stockout costs that SKU's share of daily
    # brand revenue, not a whole day of the entire brand's revenue.
    lost = daily_rate * exposure["sku_day_fraction"]

    return html.Div(
        html.Div(
            [
                html.Span(
                    f"{OWN_BRAND} estimated lost revenue",
                    style={"fontSize": "12px", "color": TEXT_SEC, "display": "block"},
                ),
                html.Span(
                    f"${lost:,.0f}",
                    style={
                        "fontSize": "28px", "fontWeight": "700",
                        "color": RED, "display": "block",
                    },
                ),
                html.Span(
                    f"over {oos_days} OOS day{'s' if oos_days != 1 else ''}, "
                    "prorated by SKU share",
                    style={"fontSize": "13px", "color": TEXT_SEC},
                ),
            ],
            style={
                "backgroundColor": CANVAS,
                "border": f"1px solid {GREY_LIGHT}",
                "borderLeft": f"4px solid {RED}",
                "borderRadius": "2px",
                "padding": "16px 24px",
                "marginBottom": "16px",
                "display": "inline-block",
                "minWidth": "260px",
            },
        ),
    )


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **base_chart_layout(height=180),
        annotations=[{
            "text": message, "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5, "showarrow": False,
            "font": {"family": FONT_SANS, "size": 14, "color": TEXT_SEC},
        }],
    )
    return fig
