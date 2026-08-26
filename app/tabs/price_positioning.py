"""Price Positioning tab — horizontal bar chart, price per oz by brand × retailer.

One row per brand, sorted most expensive at top. Two bars per brand: Amazon (teal)
and Walmart (navy). Cinderhaven bars carry a bold INK outline to stand out.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.charts import base_chart_layout
from app.components import chart_footnote, last_scraped_indicator
from app.constants import (
    CANVAS,
    COLOR_AMAZON,
    COLOR_WALMART,
    FONT_SANS,
    FONT_SERIF,
    GREY_LIGHT,
    INK,
    OWN_BRAND,
    TEXT_SEC,
)
from app.data import get_latest_price_per_oz

TAB_ID = "tab-price-positioning"
GRAPH_ID = "price-positioning-chart"


def layout() -> html.Div:
    return html.Div([
        last_scraped_indicator(),
        html.P(
            "Price per ounce by brand and retailer, most expensive at top. "
            f"{OWN_BRAND} is positioned at the category median.",
            className="ll-column",
            style={"fontSize": "14px", "color": TEXT_SEC, "marginBottom": "0"},
        ),
        html.Div(
            [
                dcc.Graph(id=GRAPH_ID, config={"displayModeBar": False}),
                chart_footnote(
                    "Source: demonstration dataset modeled on public Walmart and "
                    "Amazon product pages. Bars show each listing's regular "
                    "(non-promotional) price per ounce."
                ),
            ],
            style={
                "backgroundColor": CANVAS,
                "border": f"1px solid {GREY_LIGHT}",
                "borderRadius": "2px",
                "padding": "24px",
                "marginTop": "20px",
            },
        ),
    ], style={"paddingTop": "16px"})


def register_callbacks(app) -> None:
    @app.callback(
        Output(GRAPH_ID, "figure"),
        Input("_refresh-trigger", "data"),
    )
    def update_chart(_):
        df = get_latest_price_per_oz()
        if df.empty:
            fig = go.Figure()
            fig.update_layout(
                **base_chart_layout(height=200),
                annotations=[{
                    "text": "No scrape data yet. Run python scrape.py to collect data.",
                    "xref": "paper", "yref": "paper",
                    "x": 0.5, "y": 0.5, "showarrow": False,
                    "font": {"family": FONT_SANS, "size": 14, "color": TEXT_SEC},
                }],
            )
            return fig
        return _build_figure(df)


def _build_figure(df: pd.DataFrame) -> go.Figure:
    df = df.groupby(["brand_name", "retailer"], as_index=False)["price_per_oz"].mean()

    brand_order = (
        df.groupby("brand_name")["price_per_oz"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    n_brands = len(brand_order)
    height = max(300, n_brands * 80 + 100)

    fig = go.Figure()

    for retailer, color, label in [
        ("amazon",  COLOR_AMAZON,  "Amazon"),
        ("walmart", COLOR_WALMART, "Walmart"),
    ]:
        sub = df[df["retailer"] == retailer].set_index("brand_name")

        x_vals, text_vals, line_colors, line_widths = [], [], [], []
        for brand in brand_order:
            is_own = OWN_BRAND in str(brand)
            if brand in sub.index:
                price = sub.loc[brand, "price_per_oz"]
                x_vals.append(price)
                text_vals.append(f"${price:.2f}/oz")
            else:
                x_vals.append(None)
                text_vals.append("")
            line_colors.append(INK if is_own else "rgba(0,0,0,0)")
            line_widths.append(2 if is_own else 0)

        fig.add_trace(go.Bar(
            x=x_vals,
            y=brand_order,
            orientation="h",
            name=label,
            marker=dict(
                color=color,
                line=dict(color=line_colors, width=line_widths),
            ),
            text=text_vals,
            textposition="outside",
            textfont=dict(family=FONT_SANS, size=11, color=INK),
            cliponaxis=False,
            hovertemplate=f"<b>%{{y}}</b><br>{label}: $%{{x:.2f}}/oz<extra></extra>",
        ))

    chart_layout = base_chart_layout(
        height=height,
        x_title="Price per oz ($)",
        show_legend=True,
        left_margin=160,
    )
    chart_layout["yaxis"]["autorange"] = "reversed"
    chart_layout["xaxis"]["tickprefix"] = "$"
    chart_layout["xaxis"]["tickformat"] = ".2f"
    chart_layout["xaxis"]["showgrid"] = True
    chart_layout["xaxis"]["gridcolor"] = "#d9d9d9"
    chart_layout["barmode"] = "group"
    chart_layout["bargroupgap"] = 0.1
    chart_layout["margin"]["r"] = 110
    chart_layout["legend"] = dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(family=FONT_SANS, size=12),
    )
    fig.update_layout(**chart_layout)
    return fig
