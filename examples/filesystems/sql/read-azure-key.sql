SELECT quackframe.register_filesystem(
    'prefect', 'azure-reports-key', 'azure_connection_string'
);

SELECT * FROM read_parquet(
    'azure-reports-key://reports/daily/*.parquet'
);
