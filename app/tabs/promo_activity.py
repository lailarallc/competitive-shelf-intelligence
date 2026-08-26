"""Promo Activity tab — heatmap timeline and summary table."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import dash_ag_grid as dag
from dash import Input, Output, dcc, html

from app.charts import base_chart_layout
from app.components import chart_footnote, date_range_toggles, empty_state, last_scraped_indicator, register_date_range_callbacks
from app.constants import (
    CANVAS, COLOR_PROMO, DATE_RANGE_DEFAULT, DATE_RANGE_OPTIONS,
    FONT_SANS, FONT_SERIF, GREY_LIGHT, INK, TEXT_SEC,
)

_ALLOWED_DAYS = frozenset(o["value"] for o in DATE_RANGE_OPTIONS)
from app.data import get_promo_events, get_promo_summary

TAB_ID = "tab-promo-activity"
HEATMAP_ID = "promo-heatmap"
SUMMARY_ID = "promo-summary-table"


def layout() -> html.Div:
    return html.Div([
        last_scraped_indicator(),
        html.P(
            "Promotional badges and price drops across brands and retailers.",
            className="ll-column",
            style={"fontSize": "14px", "color": TEXT_SEC, "marginBottom": "0"},
        ),
        html.Div([
            date_range_toggles("promo"),
            dcc.Graph(id=HEATMAP_ID, config={"displayModeBar": False}),
            html.H3(
                "Promo Summary",
                style={"fontFamily": FONT_SANS, "fontWeight": "600",
                       "fontSize": "16px", "marginTop": "24px", "marginBottom": "8px"},
            ),
            html.Div(id=SUMMARY_ID),
            chart_footnote(
                "Source: demonstration dataset (Walmart and Amazon). Promo depth = "
                "(regular price − promotional price) ÷ regular price."
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
    register_date_range_callbacks(app, "promo")

    @app.callback(
        Output(HEATMAP_ID, "figure"),
        Output(SUMMARY_ID, "children"),
        Input("promo-date-range", "data"),
        Input("_refresh-trigger", "data"),
    )
    def update(days, _):
        days = int(days) if days is not None else DATE_RANGE_DEFAULT
        days = days if days in _ALLOWED_DAYS else DATE_RANGE_DEFAULT
        df = get_promo_events(days)
        summary_df = get_promo_summary(days)

        heatmap_fig = _build_heatmap(df) if not df.empty else _empty_fig("No promo events in this window.")
        summary_el = _build_summary(summary_df) if not summary_df.empty else empty_state("No promo data.")

        return heatmap_fig, summary_el


def _build_heatmap(df: pd.DataFrame) -> go.Figure:
    df["label"] = df["brand_name"] + " (" + df["retailer"].str.title() + ")"
    labels = sorted(df["label"].unique())
    dates  = sorted(df["scraped_date"].unique())

    z, text = [], []
    for lbl in labels:
        row_df = df[df["label"] == lbl]
        active_dates = set(str(d) for d in row_df["scraped_date"])
        z_row = [1 if str(d) in active_dates else 0 for d in dates]
        z.append(z_row)
        text.append(["Promo" if v == 1 else "" for v in z_row])

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[str(d) for d in dates],
        y=labels,
        text=text,
        hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
        colorscale=[[0, CANVAS], [1, COLOR_PROMO]],
        showscale=False,
        xgap=1, ygap=1,
    ))
    height = max(200, len(labels) * 32 + 80)
    layout = base_chart_layout(height=height, left_margin=220, x_title="Scrape Date")
    layout["yaxis"]["autorange"] = "reversed"
    fig.update_layout(**layout)
    return fig


def _build_summary(df: pd.DataFrame) -> dag.AgGrid:
    display_df = df.copy()
    display_df.columns = ["Brand", "Retailer", "Promo Events", "Avg Depth (%)"]
    display_df["Retailer"] = display_df["Retailer"].str.title()
    display_df["Avg Depth (%)"] = display_df["Avg Depth (%)"].apply(
        lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
    )
    return dag.AgGrid(
        rowData=display_df.to_dict("records"),
        columnDefs=[
            {"field": "Brand", "flex": 2, "sortable": True},
            {"field": "Retailer", "flex": 1, "sortable": True},
            {"field": "Promo Events", "flex": 1, "sortable": True},
            {"field": "Avg Depth (%)", "flex": 1, "sortable": True},
        ],
        defaultColDef={"resizable": False},
        dashGridOptions={"domLayout": "autoHeight", "rowHeight": 36, "headerHeight": 36},
        style={"width": "100%"},
        className="ag-theme-alpine",
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
