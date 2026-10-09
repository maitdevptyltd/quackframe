CREATE TEMP TABLE report AS
SELECT SUM(value) AS total
FROM reporting_input;
