from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / "leases.json"
AS_OF = pd.Timestamp(date.today()).normalize()

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(5,7,15,0.2)",
    font=dict(color="#e8f4ff", family="IBM Plex Sans"),
    margin=dict(l=40, r=20, t=30, b=40),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)


def load_leases() -> pd.DataFrame:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    df = pd.DataFrame(payload["leases"])
    df["commencement_date"] = pd.to_datetime(df["commencement_date"], errors="coerce")
    df["expiration_date"] = pd.to_datetime(df["expiration_date"], errors="coerce")
    df["annual_base_rent"] = pd.to_numeric(df["annual_base_rent"], errors="coerce")
    df["sqft"] = pd.to_numeric(df["sqft"], errors="coerce")
    df["rent_per_sqft"] = pd.to_numeric(df["rent_per_sqft"], errors="coerce")
    remaining = (df["expiration_date"] - AS_OF).dt.days / 365.25
    df["years_remaining"] = remaining
    df["expiring_12m"] = remaining.between(0, 1)
    df["status_label"] = df["document_status"].fillna("unknown").str.title()
    df["tenant_short"] = df["tenant"].fillna("Unknown tenant")
    return df


def money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def cashflow_frame(df: pd.DataFrame) -> pd.DataFrame:
    valid_expirations = df["expiration_date"].dropna()
    chart_start = AS_OF.to_period("M").to_timestamp()
    chart_end = (
        valid_expirations.max().to_period("M").to_timestamp()
        if not valid_expirations.empty
        else chart_start
    )
    months = pd.date_range(chart_start, chart_end, freq="MS")
    rows = []
    for _, lease in df.iterrows():
        start = lease["commencement_date"]
        end = lease["expiration_date"]
        rent = lease["annual_base_rent"]
        if pd.isna(rent) or pd.isna(end):
            continue
        name = lease["tenant_short"]
        for month in months:
            active = True
            if pd.notna(start) and month < start:
                active = False
            if month > end:
                active = False
            rows.append(
                {
                    "month": month,
                    "tenant": name,
                    "monthly_rent": (rent / 12.0) if active else 0.0,
                }
            )
    return pd.DataFrame(rows)


def walt(df: pd.DataFrame) -> float | None:
    valid = df.dropna(subset=["annual_base_rent", "years_remaining"])
    valid = valid[valid["years_remaining"] > 0]
    if valid.empty:
        return None
    return float(
        (valid["years_remaining"] * valid["annual_base_rent"]).sum()
        / valid["annual_base_rent"].sum()
    )


df_all = load_leases()
cf_all = cashflow_frame(df_all)

app = Dash(__name__, title="Harbor Grid · Lease Intel")
app.layout = html.Div(
    className="app-shell",
    children=[
        html.Div(
            className="topbar",
            children=[
                html.Div(
                    [
                        html.Div("HARBOR GRID", className="brand"),
                        html.Div(
                            "Inherited CRE book · New Haven corridor · live lease intelligence",
                            className="subbrand",
                        ),
                    ]
                ),
                html.Div(
                    "MODEL 5.6 LUNA  ·  AI LEASE ABSTRACTS  ·  10 LEASE FILES",
                    className="subbrand",
                ),
            ],
        ),
        html.Div(
            className="controls",
            children=[
                dcc.Dropdown(
                    id="type-filter",
                    options=[{"label": "All space types", "value": "ALL"}]
                    + [
                        {"label": t, "value": t}
                        for t in sorted(df_all["space_type"].dropna().unique())
                    ],
                    value="ALL",
                    clearable=False,
                    style={"width": "320px", "color": "#0b1224"},
                )
            ],
        ),
        html.Div(id="kpi-row", className="kpi-grid"),
        html.Div(
            className="grid-2",
            children=[
                html.Div(
                    className="panel",
                    children=[
                        html.H3("PORTFOLIO MAP"),
                        dcc.Graph(id="map-fig", config={"displayModeBar": False}),
                    ],
                ),
                html.Div(
                    className="panel",
                    children=[
                        html.H3("CONTRACTED CASHFLOW"),
                        dcc.Graph(id="cf-fig", config={"displayModeBar": False}),
                    ],
                ),
            ],
        ),
        html.Div(
            className="panel",
            children=[
                html.H3("LEASE ABSTRACTS"),
                dash_table.DataTable(
                    id="lease-table",
                    style_header={
                        "backgroundColor": "#071225",
                        "color": "#38bdf8",
                        "fontFamily": "Orbitron",
                        "letterSpacing": "0.08em",
                        "border": "1px solid #1d4ed8",
                    },
                    style_cell={
                        "backgroundColor": "#05070f",
                        "color": "#e8f4ff",
                        "border": "1px solid #12305a",
                        "fontFamily": "IBM Plex Sans",
                        "fontSize": 13,
                        "padding": "8px",
                    },
                    style_data_conditional=[
                        {
                            "if": {"filter_query": "{expiring_12m} = True"},
                            "color": "#fb7185",
                        }
                    ],
                    page_size=10,
                ),
            ],
        ),
    ],
)


@app.callback(
    Output("kpi-row", "children"),
    Output("map-fig", "figure"),
    Output("cf-fig", "figure"),
    Output("lease-table", "data"),
    Output("lease-table", "columns"),
    Input("type-filter", "value"),
)
def refresh(space_type: str):
    df = df_all if space_type == "ALL" else df_all[df_all["space_type"] == space_type]
    annual = df["annual_base_rent"].sum(skipna=True)
    sqft = df["sqft"].sum(skipna=True)
    kpis = [
        html.Div(
            [html.Div("Assets", className="label"), html.Div(str(len(df)), className="value")],
            className="kpi",
        ),
        html.Div(
            [html.Div("Occupied SF", className="label"), html.Div(f"{sqft:,.0f}", className="value")],
            className="kpi",
        ),
        html.Div(
            [html.Div("In-place rent", className="label"), html.Div(money(annual), className="value")],
            className="kpi",
        ),
        html.Div(
            [
                html.Div("WALT", className="label"),
                html.Div(
                    "—" if walt(df) is None else f"{walt(df):.1f} yrs",
                    className="value",
                ),
            ],
            className="kpi",
        ),
        html.Div(
            [
                html.Div("Expiring 12m", className="label"),
                html.Div(str(int(df["expiring_12m"].fillna(False).sum())), className="value"),
            ],
            className="kpi",
        ),
    ]

    map_df = df.dropna(subset=["latitude", "longitude"])
    map_fig = px.scatter_map(
        map_df,
        lat="latitude",
        lon="longitude",
        color="annual_base_rent",
        size="sqft",
        hover_name="tenant",
        hover_data={
            "address": True,
            "space_type": True,
            "expiration_date": True,
            "annual_base_rent": ":$,.0f",
            "latitude": False,
            "longitude": False,
        },
        zoom=10,
        height=430,
        color_continuous_scale=["#1e3a8a", "#38bdf8", "#e0f2fe"],
    )
    map_fig.update_layout(
        **{**PLOTLY_LAYOUT, "margin": dict(l=0, r=0, t=0, b=0)},
        map_style="carto-darkmatter",
        coloraxis_colorbar=dict(title="Rent"),
    )

    tenants = set(df["tenant_short"])
    cf = cf_all[cf_all["tenant"].isin(tenants)]
    if cf.empty:
        cf_fig = go.Figure()
    else:
        cf_fig = px.area(
            cf,
            x="month",
            y="monthly_rent",
            color="tenant",
            height=430,
        )
        cf_fig.update_traces(line=dict(width=1.2))
        cf_fig.update_layout(
            **PLOTLY_LAYOUT,
            yaxis_title="Monthly base rent ($)",
            xaxis_title="",
            hovermode="x unified",
        )

    table_df = df.copy()
    table_df["commencement_date"] = table_df["commencement_date"].dt.strftime("%Y-%m-%d").where(
        table_df["commencement_date"].notna(), None
    )
    table_df["expiration_date"] = table_df["expiration_date"].dt.strftime("%Y-%m-%d").where(
        table_df["expiration_date"].notna(), None
    )
    table_df["annual_base_rent"] = table_df["annual_base_rent"].map(
        lambda x: None if pd.isna(x) else round(float(x), 2)
    )
    cols = [
        {"name": c, "id": c}
        for c in [
            "tenant",
            "landlord",
            "address",
            "space_type",
            "sqft",
            "annual_base_rent",
            "lease_structure",
            "expiration_date",
            "status_label",
        ]
    ]
    return kpis, map_fig, cf_fig, table_df.to_dict("records"), cols


if __name__ == "__main__":
    if not DATA_PATH.exists():
        raise SystemExit("leases.json not found. Run extract_leases.py first.")
    app.run(debug=os.getenv("DASH_DEBUG", "0") == "1")
