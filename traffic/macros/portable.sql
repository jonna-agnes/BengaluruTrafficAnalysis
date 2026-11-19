{# Use the layer name (staging / intermediate / marts) as the schema, not <target>_<layer>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}

{# ISO weekday, Monday = 1 ... Sunday = 7, on Snowflake and DuckDB. #}
{% macro iso_weekday(expr) -%}
    {%- if target.type == 'duckdb' -%} isodow({{ expr }}) {%- else -%} dayofweekiso({{ expr }}) {%- endif -%}
{%- endmacro %}

{# YYYYMMDD integer key for a date. #}
{% macro date_key(expr) -%}
    cast(year({{ expr }}) * 10000 + month({{ expr }}) * 100 + day({{ expr }}) as integer)
{%- endmacro %}

{# Stable surrogate key for a text attribute. #}
{% macro text_key(expr) -%}
    md5(lower(trim({{ expr }})))
{%- endmacro %}
