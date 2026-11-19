# Python Configuration Example

[run.py](run.py) shows how to call `load_config()` to load project settings,
override database storage and runtime, and pass the configuration to `run()`.

From this directory, with Quackframe installed through Poetry:

```powershell
poetry run python run.py
```

The example executes [sql/example.sql](sql/example.sql) and retains its table
in `data/example.duckdb`. Relative database and SQL paths resolve from the
runtime root supplied in `run.py`.

Use `run()` without a configuration argument when no Python overrides or
configuration inspection are needed; it loads project settings automatically.

## Related Docs

- [Configuration](../../docs/configuration.md): settings and precedence.
- [Developer API](../../docs/developer-api.md): Python and CLI entry points.
- [Examples](../README.md): other downstream usage examples.
