# Prefect Runtime Example

This example selects the optional Prefect runtime adapter while leaving Prefect
connection details outside checked-in configuration.

Configure Prefect through its native profile or environment settings, then run:

```powershell
quackframe run sql/hello.sql
```

The result is one Prefect flow run containing one task named from
`hello.sql`. The SQL and core execution behaviour remain the same as direct
execution.

The function allowlist is deliberately empty. Selecting the Prefect runtime
does not implicitly enable Prefect-backed credentials or another SQL function.

Do not add private API URLs, API keys, or other sensitive integration metadata
to this example.
