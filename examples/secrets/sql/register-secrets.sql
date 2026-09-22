SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'reporting_reader',
    overrides := MAP {'database': 'Reporting'}
);

SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'shared-sql-login',
    secret_type := 'mssql',
    alias := 'warehouse_reader',
    overrides := MAP {'database': 'Warehouse'}
);

SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'analytics-storage',
    secret_type := 'azure_connection_string',
    alias := 'analytics_storage',
    overrides := MAP {'scope': 'az://example-container/reports/'}
);

SELECT quackframe.register_secret(
    provider := 'prefect',
    reference := 'source-files',
    secret_type := 'ssh_private_key',
    alias := 'incoming_files',
    overrides := MAP {'scope': 'sftp://files.example.test/incoming/'}
);
