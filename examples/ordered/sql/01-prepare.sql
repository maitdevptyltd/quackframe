CREATE TEMP TABLE example_values AS
SELECT *
FROM (VALUES ('alpha'), ('beta'), ('gamma')) AS values_table(value);
