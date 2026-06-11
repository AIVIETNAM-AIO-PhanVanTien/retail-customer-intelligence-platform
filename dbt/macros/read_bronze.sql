{% macro read_bronze_parquet() %}
    {# Read all Bronze Parquet partitions into a single DuckDB table #}
    {% set sql %}
        CREATE OR REPLACE VIEW {{ this }} AS
        SELECT * FROM read_parquet('../data/bronze/year_month=*/data.parquet',
                                   filename=false, hive_partition=false)
    {% endset %}
    {{ log("Loading Bronze Parquet into DuckDB", info=true) }}
    {{ return(sql) }}
{% endmacro %}
