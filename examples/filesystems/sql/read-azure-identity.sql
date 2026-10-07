SELECT quackframe.register_filesystem(
    provider := 'prefect',
    reference := 'azure-reports-identity',
    filesystem_type := 'azure_managed_identity',
    protocol := 'reports-mi'
);

SELECT * FROM read_csv('reports-mi://reports/daily/*.csv');
