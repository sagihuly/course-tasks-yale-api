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
    df["lease_structure_label"] = df["lease_structure"].fillna("TBD")
    df["city_label"] = df["city"].fillna("Unknown city")
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


def display_value(value: object, fallback: str = "—") -> str:
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def location_card(lease: pd.Series | None):
    if lease is None:
        return html.Div(
            [
                html.Div("SELECT A PIN", className="location-kicker"),
                html.H2("Location intelligence", className="location-title"),
                html.P(
                    "Click a property on the map or use the selector to inspect its exact portfolio record.",
                    className="location-empty",
                ),
            ],
            className="location-empty-state",
        )

    latitude = display_value(lease.get("latitude"))
    longitude = display_value(lease.get("longitude"))
    map_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    return html.Div(
        [
            html.Div("ACTIVE PROPERTY", className="location-kicker"),
            html.H2(display_value(lease.get("tenant")), className="location-title"),
            html.Div(
                [
                    html.Span(display_value(lease.get("space_type")), className="location-chip"),
                    html.Span(display_value(lease.get("lease_structure"), "Structure TBD"), className="location-chip muted"),
                ],
                className="location-chips",
            ),
            html.Div(
                [
                    html.Div("ADDRESS", className="detail-label"),
                    html.Div(
                        f"{display_value(lease.get('address'))}, {display_value(lease.get('city'))}, {display_value(lease.get('state'))} {display_value(lease.get('zip'))}",
                        className="detail-value",
                    ),
                ],
                className="detail-row",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Div("LATITUDE", className="detail-label"), html.Div(latitude, className="detail-value")],
                        className="detail-cell",
                    ),
                    html.Div(
                        [html.Div("LONGITUDE", className="detail-label"), html.Div(longitude, className="detail-value")],
                        className="detail-cell",
                    ),
                ],
                className="detail-grid",
            ),
            html.Div(
                [
                    html.Div("ANNUAL BASE RENT", className="detail-label"),
                    html.Div(money(lease.get("annual_base_rent")), className="detail-value accent"),
                ],
                className="detail-row",
            ),
            html.A("OPEN APPROXIMATE PIN ↗", href=map_url, target="_blank", className="map-link"),
            html.Div("Coordinates are approximate teaching-data locations.", className="location-note"),
        ],
        className="location-card-content",
    )


df_all = load_leases()
cf_all = cashflow_frame(df_all)
property_options = [{"label": "All properties", "value": "ALL"}] + [
    {
        "label": f"{row.tenant_short} · {row.city_label}",
        "value": row.tenant_short,
    }
    for _, row in df_all.sort_values("tenant_short").iterrows()
]

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
                            "Portfolio command center · New Haven corridor · lease intelligence",
                            className="subbrand",
                        ),
                    ],
                    className="brand-lockup",
                ),
                html.Div(
                    [
                        html.Div("SYSTEM ONLINE", className="live-pill"),
                        html.Div("MODEL 5.6 LUNA · 10 LEASE FILES", className="subbrand topbar-meta"),
                    ],
                    className="topbar-status",
                ),
            ],
        ),
        html.Div(
            [
                html.Div("CRE / 02", className="eyebrow"),
                html.H1("See the book.\nMove before the lease does.", className="hero-title"),
                html.P(
                    "A live view of contracted rent, lease expiry, and approximate property geography across the inherited portfolio.",
                    className="hero-copy",
                ),
            ],
            className="hero",
        ),
        html.Div(
            className="controls",
            children=[
                html.Div(
                    [
                        html.Div("SPACE TYPE", className="control-label"),
                        dcc.Dropdown(
                            id="type-filter",
                            options=[{"label": "All space types", "value": "ALL"}]
                            + [
                                {"label": t, "value": t}
                                for t in sorted(df_all["space_type"].dropna().unique())
                            ],
                            value="ALL",
                            clearable=False,
                            className="control-dropdown",
                        ),
                    ],
                    className="control-block",
                ),
                html.Div(
                    [
                        html.Div("FOCUS PROPERTY", className="control-label"),
                        dcc.Dropdown(
                            id="property-filter",
                            options=property_options,
                            value="ALL",
                            clearable=False,
                            className="control-dropdown property-dropdown",
                        ),
                    ],
                    className="control-block property-control",
                ),
                html.Div(
                    "PIN DATA · APPROXIMATE / TEACHING SET",
                    className="control-note",
                ),
            ],
        ),
        html.Div(id="kpi-row", className="kpi-grid"),
        html.Div(
            className="grid-2",
            children=[
                html.Div(
                    className="panel map-panel",
                    children=[
                        html.Div(
                            [
                                html.Div(
                                    [html.Span("01", className="panel-index"), html.H3("PORTFOLIO GEO MAP")],
                                    className="panel-heading",
                                ),
                                html.Div(f"{int(df_all['latitude'].notna().sum())}/{len(df_all)} SITES LOCATED", className="panel-status"),
                            ],
                            className="panel-topline",
                        ),
                        dcc.Graph(
                            id="map-fig",
                            config={"displayModeBar": False, "scrollZoom": True},
                        ),
                    ],
                ),
                html.Div(
                    className="panel location-panel",
                    children=[
                        html.Div(
                            [
                                html.Div(
                                    [html.Span("02", className="panel-index"), html.H3("LOCATION INTELLIGENCE")],
                                    className="panel-heading",
                                ),
                                html.Div("CLICK A PIN", className="panel-status"),
                            ],
                            className="panel-topline",
                        ),
                        html.Div(id="location-card", className="location-card"),
                    ],
                ),
            ],
        ),
        html.Div(
            className="panel cashflow-panel",
            children=[
                html.Div(
                    [
                        html.Div(
                            [html.Span("03", className="panel-index"), html.H3("CONTRACTED CASHFLOW")],
                            className="panel-heading",
                        ),
                        html.Div("BASE RENT · MONTHLY RUN-RATE", className="panel-status"),
                    ],
                    className="panel-topline",
                ),
                dcc.Graph(id="cf-fig", config={"displayModeBar": False}),
            ],
        ),
        html.Div(
            className="panel table-panel",
            children=[
                html.Div(
                    [
                        html.Div(
                            [html.Span("04", className="panel-index"), html.H3("LEASE ABSTRACTS")],
                            className="panel-heading",
                        ),
                        html.Div("AI-EXTRACTED / REVIEWABLE", className="panel-status"),
                    ],
                    className="panel-topline",
                ),
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
                    sort_action="native",
                    filter_action="native",
                    merge_duplicate_headers=True,
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
    Output("location-card", "children"),
    Input("type-filter", "value"),
    Input("property-filter", "value"),
    Input("map-fig", "clickData"),
)
def refresh(space_type: str, property_name: str, click_data: dict | None):
    df = df_all if space_type == "ALL" else df_all[df_all["space_type"] == space_type]
    annual = df["annual_base_rent"].sum(skipna=True)
    sqft = df["sqft"].sum(skipna=True)
    mapped = int(df["latitude"].notna().sum())
    cities = int(df["city_label"].nunique())
    kpis = [
        html.Div(
            [html.Div("Assets", className="label"), html.Div(str(len(df)), className="value")],
            className="kpi",
        ),
        html.Div(
            [html.Div("Mapped sites", className="label"), html.Div(f"{mapped}/{len(df)}", className="value")],
            className="kpi",
        ),
        html.Div(
            [html.Div("Markets", className="label"), html.Div(str(cities), className="value")],
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
            [html.Div("WALT", className="label"), html.Div("—" if walt(df) is None else f"{walt(df):.1f} yrs", className="value")],
            className="kpi",
        ),
        html.Div(
            [html.Div("Expiring 12m", className="label"), html.Div(str(int(df["expiring_12m"].fillna(False).sum())), className="value")],
            className="kpi",
        ),
    ]

    map_df = df.dropna(subset=["latitude", "longitude"]).copy()
    if map_df.empty:
        map_fig = go.Figure()
    else:
        map_fig = px.scatter_map(
            map_df,
            lat="latitude",
            lon="longitude",
            color="lease_structure_label",
            size="sqft",
            size_max=30,
            hover_name="tenant_short",
            custom_data=[
                "tenant_short",
                "address",
                "city_label",
                "space_type",
                "lease_structure_label",
                "annual_base_rent",
                "expiration_date",
                "latitude",
                "longitude",
            ],
            hover_data={
                "tenant_short": False,
                "address": True,
                "city_label": True,
                "space_type": True,
                "lease_structure_label": True,
                "annual_base_rent": ":$,.0f",
                "expiration_date": True,
                "latitude": False,
                "longitude": False,
            },
            center={
                "lat": float(map_df["latitude"].mean()),
                "lon": float(map_df["longitude"].mean()),
            },
            zoom=10,
            height=520,
            color_discrete_map={
                "Triple Net (NNN)": "#38bdf8",
                "Modified Gross": "#a78bfa",
                "Gross": "#34d399",
                "TBD": "#fb7185",
            },
        )
        map_fig.update_traces(marker={"opacity": 0.9})
    map_fig.update_layout(
        **{**PLOTLY_LAYOUT, "margin": dict(l=0, r=0, t=0, b=0)},
        map_style="carto-darkmatter",
    )

    selected_name = property_name if property_name != "ALL" else None
    if click_data and click_data.get("points"):
        custom_data = click_data["points"][0].get("customdata")
        if custom_data is not None and len(custom_data) > 0:
            selected_name = custom_data[0]
    selected_rows = df[df["tenant_short"] == selected_name] if selected_name else df.iloc[0:0]
    selected_lease = selected_rows.iloc[0] if not selected_rows.empty else None

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
    column_specs = [
        ("tenant", "Tenant"),
        ("city", "Market"),
        ("address", "Address"),
        ("space_type", "Space"),
        ("sqft", "SF"),
        ("annual_base_rent", "Annual rent"),
        ("lease_structure", "Structure"),
        ("expiration_date", "Expiration"),
        ("status_label", "Document"),
    ]
    cols = [{"name": label, "id": field} for field, label in column_specs]
    return kpis, map_fig, cf_fig, table_df.to_dict("records"), cols, location_card(selected_lease)


if __name__ == "__main__":
    if not DATA_PATH.exists():
        raise SystemExit("leases.json not found. Run extract_leases.py first.")
    app.run(debug=os.getenv("DASH_DEBUG", "0") == "1")
