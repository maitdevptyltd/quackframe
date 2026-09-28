SELECT quackframe.register_filesystem('prefect', 'source_files', 'sftp');

SELECT * FROM read_csv('sftp://files.example.test/reports/*.csv');
