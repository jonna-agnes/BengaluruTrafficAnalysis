"""Bengaluru Traffic Intelligence: Streamlit view of the pipeline outputs.

    streamlit run streamlit_app/app.py

Reads the snapshot in streamlit_app/data/ (refresh it with streamlit_app/export_data.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA = Path(__file__).resolve().parent / "data"
LEVELS = ["Low", "Moderate", "High", "Severe"]
LEVEL_COLORS = {"Low": "#2e9e5b", "Moderate": "#e3b505", "High": "#f08a24", "Severe": "#d64545"}

st.set_page_config(page_title="Bengaluru Traffic Intelligence", page_icon="🚦", layout="wide")


@st.cache_data
def load():
    traffic = pd.read_parquet(DATA / "traffic_5min.parquet")
    traffic["hour"] = traffic["window_start"].dt.hour
    impact = pd.read_parquet(DATA / "event_impact.parquet")
    forecast = pd.read_csv(DATA / "congestion_forecast.csv")
    briefing = (DATA / "traffic_briefing.md").read_text(encoding="utf-8")
    metrics = json.loads((DATA / "metrics.json").read_text())
    return traffic, impact, forecast, briefing, metrics


traffic, impact, forecast, briefing, metrics = load()

# ------------------------------------------------------------------ sidebar filters
st.sidebar.header("Filters")
areas = sorted(traffic["area"].unique())
sel_areas = st.sidebar.multiselect("Area", areas, default=areas)
dates = sorted(traffic["date_day"].unique())
sel_dates = st.sidebar.select_slider("Dates", options=dates, value=(dates[0], dates[-1]),
                                     format_func=lambda d: pd.Timestamp(d).strftime("%a %d %b"))
day_type = st.sidebar.radio("Days", ["All", "Weekdays", "Weekends"], horizontal=True)
st.sidebar.caption("Data: 7 days of **synthetic** traffic for 20 road segments "
                   "(simulator → S3 → Snowflake → dbt).")

mask = traffic["area"].isin(sel_areas) & traffic["date_day"].between(*sel_dates)
if day_type != "All":
    mask &= traffic["is_weekend"] == (day_type == "Weekends")
t = traffic[mask]
imask = impact["area"].isin(sel_areas) & impact["date_day"].between(*sel_dates)
im = impact[imask]

# ------------------------------------------------------------------ header
st.title("🚦 Bengaluru Traffic Intelligence")
st.caption("Congestion analytics, a 30-minute ML forecast and an AI-written operations briefing, "
           "built on an AWS S3 + Snowflake + dbt pipeline. Data is simulated, not real sensor readings.")

if t.empty:
    st.warning("No data for these filters.")
    st.stop()

tab_dash, tab_fc, tab_ai, tab_about = st.tabs(["📊 Dashboard", "🔮 30-min forecast", "🤖 AI briefing", "🏗️ How it works"])

# ------------------------------------------------------------------ dashboard
with tab_dash:
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("5-min windows", f"{len(t):,}")
    k2.metric("Vehicles", f"{t['vehicles'].sum() / 1e6:.2f}M")
    k3.metric("Avg speed", f"{t['avg_speed_kmph'].mean():.1f} km/h")
    k4.metric("Avg occupancy", f"{t['avg_occupancy_pct'].mean():.1f}%")
    k5.metric("High/Severe share", f"{t['peak_congestion_level'].isin(['High', 'Severe']).mean():.1%}")

    c1, c2 = st.columns([2, 1])
    hourly = t.groupby(["hour", "area"], as_index=False)["peak_congestion_rank"].mean()
    fig = px.line(hourly, x="hour", y="peak_congestion_rank", color="area", markers=False,
                  labels={"hour": "Hour of day", "peak_congestion_rank": "Avg congestion (1 Low – 4 Severe)"},
                  title="Congestion by hour of day")
    fig.update_layout(height=380, legend_title_text="", margin=dict(t=50, b=10))
    c1.plotly_chart(fig, width="stretch")

    split = t["peak_congestion_level"].value_counts().reindex(LEVELS, fill_value=0).reset_index()
    split.columns = ["level", "windows"]
    fig = px.pie(split, names="level", values="windows", hole=0.55, color="level",
                 color_discrete_map=LEVEL_COLORS, category_orders={"level": LEVELS}, title="Congestion split")
    fig.update_layout(height=380, margin=dict(t=50, b=10))
    c2.plotly_chart(fig, width="stretch")

    c3, c4 = st.columns(2)
    by_area = (t.groupby("area", as_index=False)
                .agg(rank=("peak_congestion_rank", "mean"), vehicles=("vehicles", "sum"),
                     speed=("avg_speed_kmph", "mean")))
    fig = px.bar(by_area.sort_values("rank"), x="rank", y="area", orientation="h", color="rank",
                 color_continuous_scale=["#2e9e5b", "#e3b505", "#d64545"], range_color=(1, 3),
                 labels={"rank": "Avg congestion rank", "area": ""}, title="Most congested areas")
    fig.update_layout(height=400, coloraxis_showscale=False, margin=dict(t=50, b=10))
    c3.plotly_chart(fig, width="stretch")

    fig = px.bar(by_area.sort_values("vehicles"), x="vehicles", y="area", orientation="h",
                 labels={"vehicles": "Vehicles", "area": ""}, title="Traffic volume by area")
    fig.update_layout(height=400, margin=dict(t=50, b=10))
    c4.plotly_chart(fig, width="stretch")

    c5, c6 = st.columns(2)
    daily = (t.groupby(["date_day", "day_name"], as_index=False)["peak_congestion_rank"].mean()
              .sort_values("date_day"))
    daily["day"] = pd.to_datetime(daily["date_day"]).dt.strftime("%a %d")
    fig = px.bar(daily, x="day", y="peak_congestion_rank", title="Congestion by day",
                 labels={"day": "", "peak_congestion_rank": "Avg congestion rank"})
    fig.update_layout(height=340, margin=dict(t=50, b=10))
    c5.plotly_chart(fig, width="stretch")

    w = im.groupby("weather", as_index=False)[["events", "speed_sum", "high_severe"]].sum()
    w["avg_speed"] = w["speed_sum"] / w["events"]
    w["pct_high"] = 100 * w["high_severe"] / w["events"]
    fig = px.bar(w.sort_values("avg_speed", ascending=False), x="weather", y="avg_speed",
                 text=w.sort_values("avg_speed", ascending=False)["avg_speed"].round(1),
                 labels={"weather": "", "avg_speed": "Avg speed (km/h)"}, title="Weather impact on speed")
    fig.update_layout(height=340, margin=dict(t=50, b=10))
    c6.plotly_chart(fig, width="stretch")

    st.subheader("Road segments")
    seg = (t.groupby(["road_segment_id", "area", "road_name", "latitude", "longitude"], as_index=False)
            .agg(rank=("peak_congestion_rank", "mean"), speed=("avg_speed_kmph", "mean"),
                 vehicles=("vehicles", "sum")))
    fig = px.scatter_map(seg, lat="latitude", lon="longitude", size="vehicles", color="rank",
                         color_continuous_scale=["#2e9e5b", "#e3b505", "#d64545"], range_color=(1, 3),
                         hover_name="road_name", hover_data={"area": True, "speed": ":.1f", "rank": ":.2f",
                                                             "latitude": False, "longitude": False},
                         zoom=10.3, height=460, map_style="carto-positron")
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), coloraxis_colorbar_title="Congestion")
    st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ forecast
with tab_fc:
    m, b = metrics["model"], metrics["persistence_baseline"]
    st.markdown("A gradient-boosting model predicts each segment's congestion **30 minutes ahead** "
                "from its current speed, occupancy, volume, recent trend, time of day, weather and incidents.")
    f1, f2, f3 = st.columns(3)
    f1.metric("Model accuracy", f"{m['accuracy']:.1%}", f"{(m['accuracy'] - b['accuracy']) * 100:+.1f} pts vs baseline")
    f2.metric("Macro F1", f"{m['macro_f1']:.2f}")
    f3.metric("Baseline (no change) accuracy", f"{b['accuracy']:.1%}")

    fc = forecast[forecast["area"].isin(sel_areas)].copy()
    as_of = pd.to_datetime(forecast["event_ts"].iloc[0]).strftime("%a %d %b %H:%M")
    for_t = pd.to_datetime(forecast["forecast_for"].iloc[0]).strftime("%H:%M")
    st.subheader(f"Forecast for {for_t} IST (based on data at {as_of})")
    trend_icon = {"worsening": "🔺 worsening", "improving": "🔻 improving", "stable": "➖ stable"}
    fc["trend"] = fc["trend"].map(trend_icon).fillna(fc["trend"])
    fc["order"] = fc["forecast_congestion_level"].map({l: i for i, l in enumerate(LEVELS)})
    fc = fc.sort_values(["order", "forecast_confidence"], ascending=[False, False])
    view = fc[["area", "road_name", "congestion_level", "forecast_congestion_level",
               "forecast_confidence", "trend", "avg_speed_kmph"]].rename(columns={
        "area": "Area", "road_name": "Road", "congestion_level": "Now",
        "forecast_congestion_level": "In 30 min", "forecast_confidence": "Confidence",
        "trend": "Trend", "avg_speed_kmph": "Speed now (km/h)"})

    def color_level(v):
        return f"background-color: {LEVEL_COLORS[v]}33; font-weight: 600" if v in LEVEL_COLORS else ""

    st.dataframe(view.style.map(color_level, subset=["Now", "In 30 min"])
                 .format({"Confidence": "{:.0%}", "Speed now (km/h)": "{:.1f}"}),
                 hide_index=True, width="stretch", height=min(740, 38 + 35 * len(view)))

# ------------------------------------------------------------------ AI briefing
with tab_ai:
    st.info("Written by an LLM (via OpenRouter) from pipeline aggregates and the ML forecast. "
            "The model only sees computed facts, never raw rows, so every number traces back to the data.")
    st.markdown(briefing)

# ------------------------------------------------------------------ how it works
with tab_about:
    st.markdown("""
### Pipeline

```
python -m simulator ──▶ clean + 5-min windows ──▶ AWS S3 (Parquet) ──▶ Snowflake ──▶ dbt star schema ──▶ Power BI / this app
   (synthetic events)      (Spark or DuckDB)        raw/ aggregated/     COPY INTO       facts + dims          + ML forecast
                                                                                                           + AI briefing
```

| Step | Tool |
|---|---|
| Generate events (10 areas, 20 segments, every 5 min) | Python |
| Stream / clean / deduplicate / aggregate | Kafka + PySpark (or DuckDB batch) |
| Data lake | Amazon S3 |
| Warehouse | Snowflake (storage integration, external stages, key-pair service user) |
| Modelling + tests | dbt |
| Orchestration | Airflow (optional) |
| BI | Power BI and Streamlit |
| Forecast | scikit-learn |
| Briefing | LLM via OpenRouter |

Source: [github.com/jonna-agnes/BengaluruTrafficAnalysis](https://github.com/jonna-agnes/BengaluruTrafficAnalysis)
""")
