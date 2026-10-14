CREATE OR REPLACE TABLE example AS
SELECT 42 AS answer;

-- quackframe: log-result
SELECT answer FROM example;
