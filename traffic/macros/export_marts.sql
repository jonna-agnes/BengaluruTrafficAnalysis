{#
  Local (DuckDB) only: export the star-schema marts as CSV for Power BI.
    dbt run-operation export_marts --args "{out_dir: 'E:/traffic_local/powerbi'}"
#}
{% macro export_marts(out_dir) %}
  {% if target.type != 'duckdb' %}
    {{ exceptions.raise_compiler_error("export_marts is for the local DuckDB target only") }}
  {% endif %}
  {% set marts = ['dim_date', 'dim_road_segment', 'dim_weather', 'dim_incident',
                  'fact_traffic_events', 'fact_traffic_5min'] %}
  {% for m in marts %}
    {% set rel = ref(m) %}
    {% set path = out_dir ~ '/' ~ m ~ '.csv' %}
    {% do run_query("COPY (SELECT * FROM " ~ rel ~ ") TO '" ~ path ~ "' (HEADER, DELIMITER ',')") %}
    {% set n = run_query("SELECT COUNT(*) FROM " ~ rel).columns[0].values()[0] %}
    {{ log("exported " ~ m ~ " (" ~ n ~ " rows) -> " ~ path, info=true) }}
  {% endfor %}
{% endmacro %}
