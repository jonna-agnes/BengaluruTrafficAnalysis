"""Bengaluru Traffic Intelligence: Streamlit app on the pipeline outputs.

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
RANK_SCALE = ["#2e9e5b", "#e3b505", "#f08a24", "#d64545"]
DAYTIME = range(7, 21)  # 07:00-20:59: the hours people actually plan trips in

st.set_page_config(page_title="Bengaluru Traffic Intelligence", page_icon="🚦", layout="wide")


# ------------------------------------------------------------------ data
@st.cache_data
def load():
    traffic = pd.read_parquet(DATA / "traffic_5min.parquet")
    traffic["hour"] = traffic["window_start"].dt.hour
    traffic["high_severe"] = traffic["peak_congestion_level"].isin(["High", "Severe"])
    impact = pd.read_parquet(DATA / "event_impact.parquet")
    impact["is_weekend"] = pd.to_datetime(impact["date_day"]).dt.day_of_week >= 5
    forecast = pd.read_csv(DATA / "congestion_forecast.csv")
    segments = (traffic.groupby("road_segment_id", as_index=False)
                .agg(latitude=("latitude", "first"), longitude=("longitude", "first")))
    forecast = forecast.merge(segments, on="road_segment_id", how="left")
    briefing = (DATA / "traffic_briefing.md").read_text(encoding="utf-8")
    metrics = json.loads((DATA / "metrics.json").read_text())
    return traffic, impact, forecast, briefing, metrics


def hours_label(start: int, length: int) -> str:
    return f"{start:02d}:00–{(start + length) % 24:02d}:00"


def level_cell(value) -> str:
    return f"background-color: {LEVEL_COLORS[value]}33; font-weight: 600" if value in LEVEL_COLORS else ""


def chart(fig, height: int = 360):
    fig.update_layout(height=height, margin=dict(t=50, b=10, l=10, r=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")


def road_map(df: pd.DataFrame, title: str, **style):
    """Schematic map: every road at its real coordinates. Plain SVG, so it renders in any browser."""
    fig = px.scatter(df, x="longitude", y="latitude", hover_name="road_name", title=title, **style)
    fig.update_traces(marker={"size": 18, "line": {"width": 1, "color": "white"}})
    for area, g in df.groupby("area"):
        fig.add_annotation(x=g["longitude"].mean(), y=g["latitude"].max(), text=area, showarrow=False,
                           yshift=16, font={"size": 11, "color": "#555"})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(plot_bgcolor="#f4f6f8", showlegend=True)
    return fig


traffic, impact, forecast, briefing, metrics = load()
all_areas = sorted(traffic["area"].unique())

# ------------------------------------------------------------------ sidebar filters
st.sidebar.header("Filters")
picked = st.sidebar.multiselect("Areas", all_areas, placeholder="All areas")
sel_areas = picked or all_areas
dates = sorted(traffic["date_day"].unique())
sel_dates = st.sidebar.select_slider("Dates", options=dates, value=(dates[0], dates[-1]),
                                     format_func=lambda d: pd.Timestamp(d).strftime("%a %d %b"))
day_type = st.sidebar.radio("Days", ["All", "Weekdays", "Weekends"], horizontal=True)
st.sidebar.caption("Data: 7 days of **simulated** traffic for 20 road segments in 10 areas "
                   "(simulator → S3 → Snowflake → dbt).")


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["area"].isin(sel_areas) & df["date_day"].between(*sel_dates)
    if day_type != "All":
        mask &= df["is_weekend"] == (day_type == "Weekends")
    return df[mask]


t, im = apply_filters(traffic), apply_filters(impact)

# ------------------------------------------------------------------ header
st.title("🚦 Bengaluru Traffic Intelligence")
st.caption("Where and when Bengaluru's roads jam, why, and what the next 30 minutes look like. "
           "Built on an AWS S3 + Snowflake + dbt pipeline with an ML forecast and an AI briefing. "
           "Data is simulated, not real sensor readings.")

tabs = st.tabs(["📊 Overview", "🚨 Next 30 min", "🔥 Hotspots", "🧭 Trip planner", "🤖 AI briefing", "ℹ️ About"])
no_data = "No data for these filters. Widen the dates or switch Days back to All."

# ------------------------------------------------------------------ overview
with tabs[0]:
    if t.empty:
        st.info(no_data)
    else:
        k = st.columns(5)
        k[0].metric("5-min windows", f"{len(t):,}")
        k[1].metric("Vehicles", f"{t['vehicles'].sum() / 1e6:.2f}M")
        k[2].metric("Avg speed", f"{t['avg_speed_kmph'].mean():.1f} km/h")
        k[3].metric("Avg occupancy", f"{t['avg_occupancy_pct'].mean():.1f}%")
        k[4].metric("High/Severe share", f"{t['high_severe'].mean():.1%}")

        c1, c2 = st.columns([2, 1])
        with c1:
            hourly = t.groupby(["hour", "area"], as_index=False)["peak_congestion_rank"].mean()
            chart(px.line(hourly, x="hour", y="peak_congestion_rank", color="area",
                          title="Congestion by hour of day",
                          labels={"hour": "Hour of day", "peak_congestion_rank": "Avg congestion (1 Low – 4 Severe)"}),
                  380)
        with c2:
            split = t["peak_congestion_level"].value_counts().reindex(LEVELS, fill_value=0).reset_index()
            split.columns = ["level", "windows"]
            chart(px.pie(split, names="level", values="windows", hole=0.55, color="level",
                         color_discrete_map=LEVEL_COLORS, category_orders={"level": LEVELS},
                         title="Congestion split"), 380)

        c3, c4 = st.columns(2)
        by_area = (t.groupby("area", as_index=False)
                    .agg(rank=("peak_congestion_rank", "mean"), vehicles=("vehicles", "sum")))
        with c3:
            chart(px.bar(by_area.sort_values("rank"), x="rank", y="area", orientation="h", color="rank",
                         color_continuous_scale=RANK_SCALE, range_color=(1, 3),
                         labels={"rank": "Avg congestion rank", "area": ""}, title="Most congested areas")
                  .update_layout(coloraxis_showscale=False), 400)
        with c4:
            chart(px.bar(by_area.sort_values("vehicles"), x="vehicles", y="area", orientation="h",
                         labels={"vehicles": "Vehicles", "area": ""}, title="Traffic volume by area"), 400)

        c5, c6, c7 = st.columns(3)
        with c5:
            daily = t.groupby("date_day", as_index=False)["peak_congestion_rank"].mean()
            daily["day"] = pd.to_datetime(daily["date_day"]).dt.strftime("%a %d")
            chart(px.bar(daily, x="day", y="peak_congestion_rank", title="Congestion by day",
                         labels={"day": "", "peak_congestion_rank": "Avg congestion rank"}), 320)
        for col, dim, title in ((c6, "weather", "Weather impact"), (c7, "incident_type", "Incident impact")):
            with col:
                g = im.groupby(dim, as_index=False)[["events", "speed_sum", "high_severe"]].sum()
                g["avg_speed"] = (g["speed_sum"] / g["events"]).round(1)
                g["pct_high"] = (100 * g["high_severe"] / g["events"]).round(1)
                chart(px.bar(g.sort_values("avg_speed", ascending=False), x=dim, y="avg_speed", text="avg_speed",
                             hover_data={"events": True, "pct_high": ":.1f"}, title=title,
                             labels={dim: "", "avg_speed": "Avg speed (km/h)", "pct_high": "% High/Severe"}), 320)

# ------------------------------------------------------------------ next 30 minutes (control room)
with tabs[1]:
    m, b = metrics["model"], metrics["persistence_baseline"]
    fc = forecast[forecast["area"].isin(sel_areas)].copy()
    as_of = pd.Timestamp(forecast["event_ts"].iloc[0]).strftime("%a %d %b %H:%M")
    target = pd.Timestamp(forecast["forecast_for"].iloc[0]).strftime("%H:%M")
    st.subheader(f"Forecast for {target} IST, from data at {as_of}")

    alerts = fc[fc["forecast_congestion_level"].isin(["High", "Severe"])]
    a = st.columns(4)
    a[0].metric("Roads High/Severe in 30 min", f"{len(alerts)} of {len(fc)}")
    a[1].metric("Severe in 30 min", int((fc["forecast_congestion_level"] == "Severe").sum()))
    a[2].metric("Getting worse", int((fc["trend"] == "worsening").sum()))
    a[3].metric("Model accuracy", f"{m['accuracy']:.1%}", f"{(m['accuracy'] - b['accuracy']) * 100:+.1f} pts vs baseline")

    worst = alerts.sort_values("forecast_confidence", ascending=False).head(3)
    if not worst.empty:
        st.warning("**Act now:** " + "; ".join(
            f"{r.road_name} ({r.area}) → {r.forecast_congestion_level}" for r in worst.itertuples()))

    left, right = st.columns([2, 3])
    with left:
        chart(road_map(fc, "Congestion in 30 minutes", color="forecast_congestion_level",
                       color_discrete_map=LEVEL_COLORS, category_orders={"forecast_congestion_level": LEVELS},
                       hover_data={"area": True, "trend": True, "latitude": False, "longitude": False},
                       labels={"forecast_congestion_level": "In 30 min"}), 520)
    with right:
        only_alerts = st.toggle("Show only High/Severe", value=False)
        view = alerts if only_alerts else fc
        trend_icon = {"worsening": "🔺 worse", "improving": "🔻 better", "stable": "➖ same"}
        order = view.assign(o=view["forecast_congestion_level"].map(LEVELS.index))
        table = (order.sort_values(["o", "forecast_confidence"], ascending=False)
                 .assign(trend=lambda d: d["trend"].map(trend_icon).fillna(d["trend"]))
                 [["road_name", "congestion_level", "forecast_congestion_level", "forecast_confidence", "trend"]]
                 .rename(columns={"road_name": "Road", "congestion_level": "Now",
                                  "forecast_congestion_level": "In 30 min", "forecast_confidence": "Confidence",
                                  "trend": "Trend"}))
        st.dataframe(table.style.map(level_cell, subset=["Now", "In 30 min"]).format({"Confidence": "{:.0%}"}),
                     hide_index=True, width="stretch", height=460)
    st.caption(f"Gradient-boosting model, {m['accuracy']:.1%} accurate on the last 20% of the timeline "
               f"(the baseline 'congestion stays the same' scores {b['accuracy']:.1%}).")

# ------------------------------------------------------------------ hotspots (planners)
with tabs[2]:
    if t.empty:
        st.info(no_data)
    else:
        heat = t.pivot_table(index="area", columns="hour", values="peak_congestion_rank", aggfunc="mean")
        heat = heat.loc[heat.mean(axis=1).sort_values(ascending=False).index]
        fig = px.imshow(heat, color_continuous_scale=RANK_SCALE, zmin=1, zmax=3.5, aspect="auto",
                        labels={"x": "Hour of day", "y": "", "color": "Congestion"},
                        title="When each area jams (average congestion, 1 Low – 4 Severe)")
        chart(fig, 420)

        seg = t.groupby(["road_segment_id", "road_name", "area", "latitude", "longitude"], as_index=False).agg(
            rank=("peak_congestion_rank", "mean"), high=("high_severe", "mean"),
            speed=("avg_speed_kmph", "mean"), vehicles=("vehicles", "sum"))
        worst_hour = (t.groupby(["road_segment_id", "hour"])["peak_congestion_rank"].mean()
                       .reset_index().sort_values("peak_congestion_rank")
                       .drop_duplicates("road_segment_id", keep="last").set_index("road_segment_id")["hour"])
        seg["worst_hour"] = seg["road_segment_id"].map(worst_hour).map(lambda h: hours_label(int(h), 1))
        seg = seg.sort_values("rank", ascending=False)

        st.markdown("**Road ranking** (worst first)")
        st.dataframe(
            seg[["road_name", "area", "rank", "high", "speed", "worst_hour", "vehicles"]].rename(columns={
                "road_name": "Road", "area": "Area", "rank": "Avg congestion", "high": "% High/Severe",
                "speed": "Avg speed", "worst_hour": "Worst hour", "vehicles": "Vehicles"}),
            hide_index=True, width="stretch", height=min(740, 38 + 35 * len(seg)),
            column_config={
                "Avg congestion": st.column_config.ProgressColumn(format="%.2f", min_value=1, max_value=4),
                "% High/Severe": st.column_config.NumberColumn(format="percent"),
                "Avg speed": st.column_config.NumberColumn(format="%.1f km/h"),
                "Vehicles": st.column_config.NumberColumn(format="localized"),
            })

# ------------------------------------------------------------------ trip planner (commuters, logistics)
with tabs[3]:
    st.markdown("Pick a road or area and a day type to see **when to travel and when to avoid it**.")
    p1, p2, p3 = st.columns([2, 2, 1])
    scope = p1.radio("Plan for", ["Area", "Road"], horizontal=True)
    if scope == "Area":
        choice = p2.selectbox("Area", all_areas, index=all_areas.index("Silk Board") if "Silk Board" in all_areas else 0)
        trips = traffic[traffic["area"] == choice]
    else:
        roads = traffic[["road_segment_id", "road_name", "area"]].drop_duplicates().sort_values(["area", "road_name"])
        labels = {r.road_segment_id: f"{r.road_name} ({r.area})" for r in roads.itertuples()}
        choice = p2.selectbox("Road", list(labels), format_func=labels.get)
        trips = traffic[traffic["road_segment_id"] == choice]
    when = p3.radio("Day", ["Weekday", "Weekend"])
    trips = trips[trips["is_weekend"] == (when == "Weekend")]
    window = st.slider("Trip window (hours)", 1, 3, 2)

    prof = (trips.groupby("hour").agg(speed=("avg_speed_kmph", "mean"), rank=("peak_congestion_rank", "mean"),
                                      high=("high_severe", "mean")).reindex(range(24)))
    day = prof.loc[list(DAYTIME)]
    rolling = day["rank"].rolling(window).mean().dropna()   # labelled by the window's last hour
    best_end, worst_end = int(rolling.idxmin()), int(rolling.idxmax())
    best_start, worst_start = best_end - window + 1, worst_end - window + 1
    best = prof.loc[best_start:best_end]
    worst = prof.loc[worst_start:worst_end]

    r1, r2 = st.columns(2)
    r1.success(f"**Best time:** {hours_label(best_start, window)}  \n"
               f"about {best['speed'].mean():.0f} km/h, High/Severe {best['high'].mean():.0%} of the time")
    r2.error(f"**Avoid:** {hours_label(worst_start, window)}  \n"
             f"about {worst['speed'].mean():.0f} km/h, High/Severe {worst['high'].mean():.0%} of the time")

    prof = prof.reset_index().rename(columns={"index": "hour"})
    prof["typical"] = pd.cut(prof["rank"], [0, 1.5, 2.5, 3.5, 5], labels=LEVELS).astype(str)
    fig = px.bar(prof, x="hour", y="speed", color="typical", color_discrete_map=LEVEL_COLORS,
                 category_orders={"typical": LEVELS},
                 hover_data={"high": ":.0%", "rank": ":.2f"},
                 labels={"hour": "Hour of day", "speed": "Expected speed (km/h)", "typical": "Typical congestion",
                         "high": "% High/Severe", "rank": "Avg congestion"},
                 title=f"Expected speed by hour: {choice if scope == 'Area' else labels[choice]}, {when.lower()}s")
    fig.add_vrect(x0=best_start - 0.5, x1=best_end + 0.5, fillcolor="#2e9e5b", opacity=0.12, line_width=0)
    fig.add_vrect(x0=worst_start - 0.5, x1=worst_end + 0.5, fillcolor="#d64545", opacity=0.12, line_width=0)
    chart(fig, 400)
    st.caption("Based on 7 days of history, considering trips between 07:00 and 21:00. Shaded: best (green) and worst (red) window.")

# ------------------------------------------------------------------ AI briefing
with tabs[4]:
    st.info("Written by an LLM (via OpenRouter) from pipeline aggregates and the ML forecast. "
            "The model only sees computed facts, never raw rows, so every number traces back to the data.")
    st.markdown(briefing)
    st.download_button("Download briefing (.md)", briefing, file_name="traffic_briefing.md", mime="text/markdown")

# ------------------------------------------------------------------ about + data
with tabs[5]:
    st.markdown("""
### How the data gets here
```
simulator ──▶ Kafka + Spark (or DuckDB) ──▶ AWS S3 ──▶ Snowflake ──▶ dbt star schema ──▶ this app / Power BI
                 clean + 5-min windows      Parquet    COPY INTO     facts + dims + tests     + ML forecast + AI briefing
```
| Step | Tool |
|---|---|
| Simulate readings (20 roads, every 5 min) | Python |
| Validate, deduplicate, aggregate | Kafka + PySpark Structured Streaming, or DuckDB |
| Data lake / warehouse | Amazon S3 / Snowflake |
| Modelling + data tests | dbt |
| Forecast / briefing | scikit-learn / LLM via OpenRouter |

Source code: [github.com/jonna-agnes/BengaluruTrafficAnalysis](https://github.com/jonna-agnes/BengaluruTrafficAnalysis)
""")
    st.markdown("### Download the data")
    d1, d2 = st.columns(2)
    d1.download_button("5-minute windows (current filters, CSV)", t.drop(columns=["high_severe"]).to_csv(index=False),
                       file_name="traffic_5min_filtered.csv", mime="text/csv", disabled=t.empty)
    d2.download_button("30-minute forecast (CSV)", forecast.to_csv(index=False),
                       file_name="congestion_forecast.csv", mime="text/csv")
