SELECT quackframe.register_secret(
    'prefect',
    'reporting_sql_login',
    'mssql'
);

-- Optional: repurpose the same login for a different database and alias.
SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'reporting-sql-login',
    secret_type := 'mssql',
    alias := 'warehouse_reader',
    overrides := MAP {'database': 'Warehouse'}
);

SELECT quackframe.register_secret(
    'prefect',
    'analytics_storage',
    'azure_connection_string'
);

SELECT quackframe.register_secret(
    'prefect',
    'source_files',
    'ssh_private_key'
);
