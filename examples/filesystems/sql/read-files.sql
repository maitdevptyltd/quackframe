SELECT quackframe.register_filesystem('prefect', 'source-files', 'sftp');

SELECT * FROM read_csv('source-files://files.example.test/reports/*.csv');
