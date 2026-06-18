"""
SAP Production Dashboard – SKU / Material level
=================================================
Fetches ZFGS finished tyre production from SAP OData API for a selected date
range and shows it as KPIs, charts, and a searchable table.
No plan file required.
"""

from datetime import date, datetime, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
SAP_URL = (
    "https://s4api.sap.jktyre.in:44305/"
    "sap/opu/odata/sap/ZINFI_PLT_API_SRV/InfiProdDtlSet"
)
SAP_USER = "INFI_CON"
SAP_PASS = "Welcome@12345678"
ZFGS     = "ZFGS"


# ─────────────────────────────────────────────────────────────────────────────
# SAP fetch
# ─────────────────────────────────────────────────────────────────────────────
def fetch_sap(from_d: date, to_d: date) -> pd.DataFrame:
    frames = []
    total  = (to_d - from_d).days + 1
    bar    = st.progress(0, text="Connecting to SAP…")

    for i, delta in enumerate(range(total), start=1):
        day    = from_d + timedelta(days=delta)
        sap_dt = day.strftime("%Y%m%d")
        bar.progress(i / total, text=f"Fetching {day.strftime('%d %b %Y')}… ({i}/{total})")

        params = {
            "$filter": (
                "Plant eq '1300' "
                f"and PFrDt eq '{sap_dt}' "
                f"and PToDt eq '{sap_dt}' "
                "and Matnr eq ' ' "
                "and Mtart eq 'ZFGS' "
                "and Matkl eq '1125' "
                "and StorgLoc eq ' ' "
                "and Arbpl eq ' ' "
                "and PType eq 'PD'"
            ),
            "$format": "json",
        }
        resp = requests.get(
            SAP_URL, params=params,
            headers={"Accept": "application/json"},
            auth=(SAP_USER, SAP_PASS),
            verify=False, timeout=300,
        )
        resp.raise_for_status()
        results = resp.json().get("d", {}).get("results", [])
        if results:
            df = pd.DataFrame(results)
            df["_date"] = day.isoformat()
            frames.append(df)

    bar.empty()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Processing
# ─────────────────────────────────────────────────────────────────────────────
def process(raw: pd.DataFrame) -> pd.DataFrame:
    """Filter ZFGS, clean numerics, return SKU-level aggregation."""
    if raw.empty:
        return pd.DataFrame(columns=["SKUCode", "Qty_Produced", "Scrap_Qty"])

    zf = raw[raw["Mtart"] == ZFGS].copy()
    zf["ProdQty"]  = pd.to_numeric(zf["ProdQty"],  errors="coerce").fillna(0)
    zf["ScarpQty"] = pd.to_numeric(zf["ScarpQty"], errors="coerce").fillna(0)

    agg = (
        zf.groupby("Matnr", as_index=False)
          .agg(Qty_Produced=("ProdQty", "sum"), Scrap_Qty=("ScarpQty", "sum"))
          .rename(columns={"Matnr": "SKUCode"})
          .sort_values("Qty_Produced", ascending=False)
          .reset_index(drop=True)
    )
    return agg


def daily_trend(raw: pd.DataFrame) -> pd.DataFrame:
    """Daily total ZFGS production for trend chart."""
    if raw.empty:
        return pd.DataFrame()
    zf = raw[raw["Mtart"] == ZFGS].copy()
    zf["ProdQty"] = pd.to_numeric(zf["ProdQty"], errors="coerce").fillna(0)
    return (
        zf.groupby("_date", as_index=False)
          .agg(Qty_Produced=("ProdQty", "sum"))
          .sort_values("_date")
    )


@st.cache_data(show_spinner=False)
def to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Production Dashboard", page_icon="🏭", layout="wide")

st.title("Production Dashboard")
st.caption("Plant 1300 · PCR Finished Tyres (ZFGS) · Live SAP")

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Date Range")

    today          = date.today()
    first_of_month = today.replace(day=1)

    preset = st.radio("Quick select", ["This Month", "Custom Range"], horizontal=True)

    if preset == "This Month":
        from_date = first_of_month
        to_date   = today
        st.markdown(f"**{from_date.strftime('%d %b')} → {to_date.strftime('%d %b %Y')}**")
    else:
        from_date = st.date_input("From", value=first_of_month, max_value=today)
        to_date   = st.date_input("To",   value=today, min_value=from_date, max_value=today)

    if from_date > to_date:
        st.error("'From' must be before 'To'.")
        st.stop()

    days = (to_date - from_date).days + 1
    st.caption(f"{days} day(s) selected")
    st.divider()

    fetch_btn = st.button("Fetch from SAP", type="primary", use_container_width=True)
    st.divider()
    top_n = st.slider("Top N SKUs in bar chart", 10, 50, 20)

# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────
if fetch_btn:
    try:
        raw = fetch_sap(from_date, to_date)
        st.session_state["raw"]        = raw
        st.session_state["range"]      = (from_date, to_date)
        st.session_state["fetched_at"] = datetime.now().strftime("%d %b %Y  %H:%M:%S")
        st.success(f"Fetched {len(raw)} records from SAP.")
    except Exception as e:
        st.error(f"SAP fetch failed: {e}")
        st.stop()

if "raw" not in st.session_state:
    st.info("Select a date range and click **Fetch from SAP** to load data.")
    st.stop()

raw          = st.session_state["raw"]
eff_from, eff_to = st.session_state["range"]
fetched_at   = st.session_state.get("fetched_at", "")

if fetched_at:
    st.caption(f"Last fetched: **{fetched_at}**  |  {len(raw)} raw records")

if st.session_state["range"] != (from_date, to_date):
    st.warning(
        f"Showing data for **{eff_from.strftime('%d %b')} – {eff_to.strftime('%d %b %Y')}**. "
        "Click **Fetch from SAP** to refresh."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Process
# ─────────────────────────────────────────────────────────────────────────────
sku_df  = process(raw)
trend   = daily_trend(raw)
file_tag = f"{eff_from.strftime('%d%b')}_{eff_to.strftime('%d%b%Y')}"

# ─────────────────────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────────────────────
total_qty   = sku_df["Qty_Produced"].sum()
total_scrap = sku_df["Scrap_Qty"].sum()
total_skus  = len(sku_df)
top_sku     = sku_df.iloc[0]["SKUCode"] if not sku_df.empty else "—"
top_qty     = sku_df.iloc[0]["Qty_Produced"] if not sku_df.empty else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Tyres Produced", f"{total_qty:,.0f}")
k2.metric("Total Scrap",          f"{total_scrap:,.0f}")
k3.metric("SKUs Produced",        total_skus)
k4.metric("Top SKU",              top_sku)
k5.metric("Top SKU Qty",          f"{top_qty:,.0f}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────────────────────
col_bar, col_trend = st.columns([3, 2])

with col_bar:
    chart_df = sku_df.head(top_n)
    fig = px.bar(
        chart_df,
        x="SKUCode", y="Qty_Produced",
        title=f"Top {top_n} SKUs by Production  ({eff_from.strftime('%d %b')} – {eff_to.strftime('%d %b %Y')})",
        labels={"SKUCode": "SKU / Material", "Qty_Produced": "Qty Produced"},
        color="Qty_Produced",
        color_continuous_scale="Blues",
        text="Qty_Produced",
    )
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(
        xaxis_tickangle=-45,
        height=420,
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=60, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_trend:
    if len(trend) > 1:
        fig2 = px.line(
            trend, x="_date", y="Qty_Produced",
            title="Daily Production Trend",
            labels={"_date": "Date", "Qty_Produced": "Qty Produced"},
            markers=True,
        )
        fig2.update_layout(height=420, margin=dict(l=0, r=0, t=60, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Daily trend needs more than 1 day of data.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SKU Table
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("SKU Production Detail")

search = st.text_input("Search SKU", placeholder="Type material code…")
filtered = sku_df.copy()
if search.strip():
    filtered = filtered[filtered["SKUCode"].str.contains(search.strip(), case=False, na=False)]

st.dataframe(
    filtered.style.format({"Qty_Produced": "{:,.0f}", "Scrap_Qty": "{:,.0f}"}),
    use_container_width=True,
    height=500,
    hide_index=True,
)
st.caption(f"{len(filtered)} SKU(s) shown")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────────────────────
dl1, dl2 = st.columns(2)

dl1.download_button(
    "Download Excel",
    data=to_excel(filtered),
    file_name=f"Production_{file_tag}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
    type="primary",
)
dl2.download_button(
    "Download CSV",
    data=filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"Production_{file_tag}.csv",
    mime="text/csv",
    use_container_width=True,
)
