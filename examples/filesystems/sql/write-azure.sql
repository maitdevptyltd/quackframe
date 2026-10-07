SELECT quackframe.register_filesystem(
    'prefect', 'azure-reports-key', 'azure_connection_string', 'output-blobs'
);
COPY (SELECT 42 AS value)
TO 'output-blobs://reports/result.parquet' (FORMAT PARQUET);

COPY (
    SELECT 42 AS value, 'example' AS account, DATE '2026-09-16' AS file_date
)
TO 'output-blobs://reports/partitioned' (FORMAT CSV, PARTITION_BY (account, file_date));

SELECT
    value,
    regexp_extract(filename, '/account=([^/]+)/', 1) AS account,
    CAST(regexp_extract(filename, '/file_date=([^/]+)/', 1) AS DATE) AS file_date
FROM read_csv(
    'output-blobs://reports/partitioned/**/*.csv',
    filename = true,
    hive_partitioning = false
);
