"""Assortment Monitor tab — new entries and possible delists vs prior run."""

from __future__ import annotations

import pandas as pd
import dash_ag_grid as dag
from dash import Input, Output, html

from app.components import chart_footnote, empty_state, last_scraped_indicator
from app.constants import CANVAS, FONT_SANS, FONT_SERIF, GREY_LIGHT, RED, TEXT_SEC, TEAL
from app.data import get_assortment_changes

TAB_ID = "tab-assortment-monitor"
TABLE_ID = "assortment-table"


def layout() -> html.Div:
    return html.Div([
        last_scraped_indicator(),
        html.P(
            "New-entry and delist examples staged in the demonstration dataset. "
            "In production this compares each listing's presence across the two "
            "most recent scrape runs.",
            className="ll-column",
            style={"fontSize": "14px", "color": TEXT_SEC, "marginBottom": "0"},
        ),
        html.Div(
            [
                html.Div(id=TABLE_ID),
                chart_footnote(
                    "Source: demonstration dataset (Walmart and Amazon). New-entry "
                    "and delist rows are staged illustrative examples, not live detections."
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
        Output(TABLE_ID, "children"),
        Input("_refresh-trigger", "data"),
    )
    def update(_):
        df = get_assortment_changes()
        if df.empty:
            return empty_state("No staged assortment changes, or fewer than two scrape runs available.")
        return _build_table(df)


def _build_table(df: pd.DataFrame) -> dag.AgGrid:
    display = df.rename(columns={
        "brand_name": "Brand",
        "product_name": "Product",
        "retailer": "Retailer",
        "first_seen_at": "First Seen",
        "last_seen_at": "Last Seen",
        "status": "Status",
    }).copy()
    display["Retailer"] = display["Retailer"].str.title()
    for col in ["First Seen", "Last Seen"]:
        if col in display.columns:
            display[col] = pd.to_datetime(display[col]).dt.strftime("%Y-%m-%d")

    return dag.AgGrid(
        rowData=display.to_dict("records"),
        columnDefs=[
            {"field": "Brand", "flex": 2, "sortable": True},
            {"field": "Product", "flex": 2, "sortable": True},
            {"field": "Retailer", "flex": 1, "sortable": True},
            {"field": "First Seen", "flex": 0.8, "sortable": True},
            {"field": "Last Seen", "flex": 0.8, "sortable": True},
            {"field": "Status", "flex": 1.5, "minWidth": 140, "sortable": True,
             "cellStyle": {"styleConditions": [
                 {"condition": "params.value === 'New Entry'",
                  "style": {"backgroundColor": "#e4f5f0", "color": TEAL, "fontWeight": "600"}},
                 {"condition": "params.value === 'Possible Delist'",
                  "style": {"backgroundColor": "#fce8e7", "color": RED, "fontWeight": "600"}},
             ]}},
        ],
        defaultColDef={"resizable": False},
        dashGridOptions={"domLayout": "autoHeight", "rowHeight": 36, "headerHeight": 36},
        style={"width": "100%"},
        className="ag-theme-alpine",
    )
