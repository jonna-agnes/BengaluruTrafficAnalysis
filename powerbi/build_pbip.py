"""Generate a Power BI project (BengaluruTraffic.pbip) over the dbt marts CSV export.

    python powerbi/build_pbip.py [--data-folder output/powerbi]

Open powerbi/BengaluruTraffic.pbip in Power BI Desktop and click Refresh. If the CSVs move,
re-run this script with --data-folder <new folder>.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "BengaluruTraffic"
# Base theme, stored at BengaluruTraffic.Report/StaticResources/SharedResources/BaseThemes/
# (a report needs a base theme to render; this one ships with Power BI Desktop).
THEME, THEME_VERSION = "CY24SU10", "5.61"

# table -> [(column, dataType, M type, summarizeBy)]
S, I, D, B, T = "string", "int64", "double", "boolean", "dateTime"
M_TYPE = {S: "type text", I: "Int64.Type", D: "type number", B: "type logical"}
TABLES = {
    "dim_date": [("date_key", I), ("date_day", T), ("year", I), ("quarter", I), ("month", I),
                 ("month_name", S), ("day_of_month", I), ("day_of_week", I), ("day_name", S), ("is_weekend", B)],
    "dim_road_segment": [("road_segment_id", S), ("area", S), ("road_name", S), ("latitude", D), ("longitude", D)],
    "dim_weather": [("weather_key", S), ("weather", S)],
    "dim_incident": [("incident_key", S), ("incident_type", S)],
    "fact_traffic_5min": [("date_key", I), ("road_segment_id", S), ("window_start", T), ("window_end", T),
                          ("area", S), ("road_name", S), ("total_events", I), ("avg_vehicle_count", D),
                          ("avg_speed_kmph", D), ("avg_occupancy_pct", D), ("peak_congestion_rank", I),
                          ("peak_congestion_level", S)],
    "fact_traffic_events": [("event_id", S), ("date_key", I), ("road_segment_id", S), ("weather_key", S),
                            ("incident_key", S), ("event_ts", T), ("vehicle_count", I), ("avg_speed_kmph", D),
                            ("occupancy_pct", D), ("congestion_level", S), ("incident_duration_minutes", I)],
}
TIMESTAMPS_WITH_ZONE = {"window_start", "window_end", "event_ts"}  # "2026-07-01 00:00:00+05:30"

MEASURES = {
    "fact_traffic_5min": [
        ("Windows", "COUNTROWS ( fact_traffic_5min )", "#,0"),
        ("Total Vehicles", "SUMX ( fact_traffic_5min, fact_traffic_5min[avg_vehicle_count] * fact_traffic_5min[total_events] )", "#,0"),
        ("Avg Speed (km/h)", "AVERAGE ( fact_traffic_5min[avg_speed_kmph] )", "0.00"),
        ("Avg Occupancy %", "AVERAGE ( fact_traffic_5min[avg_occupancy_pct] )", "0.00"),
        ("Avg Congestion Rank", "AVERAGE ( fact_traffic_5min[peak_congestion_rank] )", "0.00"),
        ("Severe Windows %", "DIVIDE ( CALCULATE ( [Windows], fact_traffic_5min[peak_congestion_level] = \"Severe\" ), [Windows] )", "0.0%"),
    ],
    "fact_traffic_events": [
        ("Event Avg Speed (km/h)", "AVERAGE ( fact_traffic_events[avg_speed_kmph] )", "0.0"),
        ("Events", "COUNTROWS ( fact_traffic_events )", "#,0"),
    ],
}
CALC_COLUMNS = {
    "fact_traffic_5min": [
        ("Hour", I, "HOUR ( fact_traffic_5min[window_start] )"),
    ],
}
# Sort by a source column: sorting by a calculated column derived from the same column is circular.
SORT_BY = {("fact_traffic_5min", "peak_congestion_level"): "peak_congestion_rank", ("dim_date", "day_name"): "day_of_week"}

RELATIONSHIPS = [  # (many table, column, one table, column)
    ("fact_traffic_5min", "date_key", "dim_date", "date_key"),
    ("fact_traffic_5min", "road_segment_id", "dim_road_segment", "road_segment_id"),
    ("fact_traffic_events", "date_key", "dim_date", "date_key"),
    ("fact_traffic_events", "road_segment_id", "dim_road_segment", "road_segment_id"),
    ("fact_traffic_events", "weather_key", "dim_weather", "weather_key"),
    ("fact_traffic_events", "incident_key", "dim_incident", "incident_key"),
]


def m_query(table: str, columns, data_folder: str) -> list[str]:
    zone_cols = [c for c, _ in columns if c in TIMESTAMPS_WITH_ZONE]
    plain = [(c, t) for c, t in columns if c not in TIMESTAMPS_WITH_ZONE]
    types = ", ".join(f'{{"{c}", {"type date" if (c == "date_day") else M_TYPE.get(t, "type datetime")}}}'
                      for c, t in plain)
    lines = [
        "let",
        f'    Source = Csv.Document(File.Contents("{data_folder}\\{table}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f'    Typed = Table.TransformColumnTypes(Headers, {{{types}}}, "en-US"){"," if zone_cols else ""}',
    ]
    if zone_cols:  # keep Bengaluru wall-clock time
        conv = ", ".join(
            f'{{"{c}", each if _ = null or _ = "" then null else DateTimeZone.RemoveZone(DateTimeZone.FromText(Text.Replace(_, " ", "T"))), type datetime}}'
            for c in zone_cols)
        lines.append(f"    Local = Table.TransformColumns(Typed, {{{conv}}})")
        lines += ["in", "    Local"]
    else:
        lines += ["in", "    Typed"]
    return lines


def model_bim(data_folder: str) -> dict:
    tables = []
    for table, columns in TABLES.items():
        cols = []
        for c, t in columns:
            col = {"name": c, "dataType": t, "sourceColumn": c,
                   "summarizeBy": "none" if t in (S, B, T) or c.endswith(("_key", "_rank")) or c in
                   ("year", "quarter", "month", "day_of_month", "day_of_week", "latitude", "longitude") else "sum"}
            if (table, c) in SORT_BY:
                col["sortByColumn"] = SORT_BY[(table, c)]
            if t == T:
                col["formatString"] = "yyyy-mm-dd" if c == "date_day" else "yyyy-mm-dd hh:nn"
            cols.append(col)
        for c, t, expr in CALC_COLUMNS.get(table, []):
            cols.append({"type": "calculated", "name": c, "dataType": t, "expression": expr, "summarizeBy": "none"})
        tables.append({
            "name": table,
            "columns": cols,
            "measures": [{"name": n, "expression": e, "formatString": f} for n, e, f in MEASURES.get(table, [])],
            "partitions": [{"name": table, "mode": "import",
                            "source": {"type": "m", "expression": m_query(table, columns, data_folder)}}],
        })
    return {
        "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "en-US",
            "tables": tables,
            "relationships": [{"name": f"{m}_{mc}__{o}", "fromTable": m, "fromColumn": mc, "toTable": o, "toColumn": oc}
                              for m, mc, o, oc in RELATIONSHIPS],
        },
    }


# ---------------------------------------------------------------- report page
def field(kind: str, table: str, prop: str, alias: str) -> dict:
    return {kind: {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}, "Name": f"{table}.{prop}"}


def visual(vid, vtype, x, y, w, h, roles: dict, title: str, sort_desc: tuple | None = None) -> dict:
    """roles: {role: [(kind, table, property)]}  kind = Column | Measure; sort_desc: (table, measure)"""
    aliases, select, projections = {}, [], {}
    for role, items in roles.items():
        for kind, table, prop in items:
            alias = aliases.setdefault(table, f"t{len(aliases)}")
            ref = f"{table}.{prop}"
            if all(s["Name"] != ref for s in select):
                select.append(field(kind, table, prop, alias))
            projections.setdefault(role, []).append({"queryRef": ref, **({"active": True} if kind == "Column" else {})})
    config = {
        "name": vid,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
        "singleVisual": {
            "visualType": vtype,
            "projections": projections,
            "prototypeQuery": {"Version": 2,
                               "From": [{"Name": a, "Entity": t, "Type": 0} for t, a in aliases.items()],
                               "Select": select,
                               **({"OrderBy": [{"Direction": 2, "Expression": {"Measure": {
                                   "Expression": {"SourceRef": {"Source": aliases[sort_desc[0]]}},
                                   "Property": sort_desc[1]}}}]} if sort_desc else {})},
            "vcObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}]},
        },
    }
    return {"x": x, "y": y, "z": 0, "width": w, "height": h, "config": json.dumps(config), "filters": "[]"}


def report_json() -> dict:
    F5, FE, DR, DD, DW = "fact_traffic_5min", "fact_traffic_events", "dim_road_segment", "dim_date", "dim_weather"
    m = lambda t, p: ("Measure", t, p)
    c = lambda t, p: ("Column", t, p)
    visuals = [
        visual("card1", "card", 10, 10, 250, 110, {"Values": [m(F5, "Windows")]}, "5-min windows"),
        visual("card2", "card", 270, 10, 250, 110, {"Values": [m(F5, "Total Vehicles")]}, "Vehicles"),
        visual("card3", "card", 530, 10, 250, 110, {"Values": [m(F5, "Avg Speed (km/h)")]}, "Avg speed (km/h)"),
        visual("card4", "card", 790, 10, 250, 110, {"Values": [m(F5, "Avg Occupancy %")]}, "Avg occupancy %"),
        visual("slicer1", "slicer", 1050, 10, 220, 110, {"Values": [c(DR, "area")]}, "Area"),
        visual("line1", "lineChart", 10, 130, 830, 290,
               {"Category": [c(F5, "Hour")], "Series": [c(DR, "area")], "Y": [m(F5, "Avg Congestion Rank")]},
               "Congestion by hour of day"),
        visual("donut1", "donutChart", 850, 130, 420, 290,
               {"Category": [c(F5, "peak_congestion_level")], "Y": [m(F5, "Windows")]}, "Congestion split"),
        visual("bar1", "clusteredBarChart", 10, 430, 410, 280,
               {"Category": [c(DR, "area")], "Y": [m(F5, "Avg Congestion Rank")]}, "Avg congestion rank by area"),
        visual("bar2", "clusteredBarChart", 430, 430, 410, 280,
               {"Category": [c(DR, "area")], "Y": [m(F5, "Total Vehicles")]}, "Traffic volume by area"),
        visual("col1", "clusteredColumnChart", 850, 430, 420, 135,
               {"Category": [c(DD, "day_name")], "Y": [m(F5, "Avg Congestion Rank")]}, "Congestion by day"),
        visual("col2", "clusteredColumnChart", 850, 575, 420, 135,
               {"Category": [c(DW, "weather")], "Y": [m(FE, "Event Avg Speed (km/h)")]}, "Avg speed by weather"),
    ]
    return {
        "config": json.dumps({"version": THEME_VERSION, "activeSectionIndex": 0,
                              "themeCollection": {"baseTheme": {"name": THEME, "version": THEME_VERSION, "type": 2}}}),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {
            "name": "SharedResources", "type": 2, "disabled": False,
            "items": [{"name": THEME, "path": f"BaseThemes/{THEME}.json", "type": 202}]}}],
        "sections": [{
            "name": "TrafficOverview", "displayName": "Traffic Overview", "displayOption": 1,
            "width": 1280, "height": 720, "filters": "[]", "config": "{}", "visualContainers": visuals,
        }],
    }


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-folder", type=Path, default=HERE.parent / "output" / "powerbi")
    args = parser.parse_args()
    data_folder = str(args.data_folder.resolve())  # M string literals don't escape backslashes

    sm, rp = HERE / f"{NAME}.SemanticModel", HERE / f"{NAME}.Report"
    write_json(HERE / f"{NAME}.pbip", {
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}})
    write_json(sm / "definition.pbism", {"version": "1.0", "settings": {}})
    write_json(sm / "model.bim", model_bim(data_folder))
    write_json(rp / "definition.pbir", {
        "version": "1.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}, "byConnection": None}})
    write_json(rp / "report.json", report_json())
    print(f"wrote {HERE / (NAME + '.pbip')}  (CSV folder: {data_folder})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
