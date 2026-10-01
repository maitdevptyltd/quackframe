SELECT quackframe.register_filesystem(
    'prefect', 'azure-reports-key', 'azure_connection_string', 'output-blobs'
);
COPY (SELECT 42 AS value)
TO 'output-blobs://reports/result.parquet' (FORMAT PARQUET);
