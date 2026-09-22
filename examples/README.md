# Quackframe Examples

These neutral examples demonstrate the downstream integration surface.
They do not prescribe repository names or organization outside the behaviour
being illustrated.

- [Basic](basic/README.md): one SQL file through CLI, F5, or Python.
- [Ordered Files](ordered/README.md): two files sharing one DuckDB session.
- [Prefect Runtime](prefect/README.md): optional Prefect runtime selection
  without checked-in connection details.
- [Secret Registration](secrets/README.md): direct execution with the explicitly
  enabled `register_secret` function for MSSQL, Azure connection strings, and
  private-key SSH.

The basic and ordered examples run without optional integrations. The Prefect
and secret examples require the `prefect` extra plus environment-appropriate
native Prefect configuration.
