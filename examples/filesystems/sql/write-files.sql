SELECT quackframe.register_filesystem('prefect', 'output-files', 'sftp');
COPY (SELECT 42 AS value)
TO 'output-files://files.example.test/exports/result.parquet' (FORMAT PARQUET);
