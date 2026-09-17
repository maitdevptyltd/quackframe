# SQL Function Extensions

Quackframe can expose self-contained Python capabilities to SQL. Each function
is an independent unit of work that conforms to a small installation contract
without being forced into shared thematic implementation.

## Public Naming

Downstream SQL uses a schema-qualified name:

```sql
SELECT quackframe.function_name(...);
```

DuckDB's Python `create_function()` treats a dotted name as a literal function
name rather than normal schema qualification. Quackframe therefore registers a
private Python UDF and creates a public SQL macro:

```text
Python UDF:  _quackframe_function_name
Public SQL:  quackframe.function_name
```

For example:

```sql
CREATE SCHEMA IF NOT EXISTS quackframe;

CREATE OR REPLACE MACRO quackframe.register_secret(
    provider,
    reference,
    secret_type,
    alias := NULL,
    overrides := NULL
) AS _quackframe_register_secret(
    provider,
    reference,
    secret_type,
    alias,
    overrides
);
```

The `quackframe` schema is reserved for Quackframe-managed macros and any
future metadata contract. Project SQL should not create unrelated objects in
that schema.

## Function-owned Packages

Each non-trivial function owns its vertical implementation slice:

```text
sql_functions/
├── definition.py
├── registry.py
├── macros.py
│
├── register_secret/
│   ├── __init__.py
│   ├── function.py
│   ├── models.py
│   ├── validation.py
│   └── providers/
│       ├── protocol.py
│       └── prefect.py
│
└── publish_metric/
    ├── __init__.py
    └── function.py
```

A simple function may begin as one module. When its supporting logic grows, it
becomes a function-named package. Themes such as credentials or observability
may be recorded as metadata and documentation categories; they do not force
unrelated functions into a shared implementation hierarchy.

Limited duplication is preferable to restrictive coupling. Shared code should
be extracted only when the behaviour and invariant genuinely have one owner and
must change together.

## Minimal Function Contract

A function definition needs enough metadata for deterministic registration:

```python
function = SqlFunction(
    name="register_secret",
    callable=register_secret,
    bind_connection=True,
    side_effects=True,
)
```

The eventual contract should describe:

- public and private names;
- the Python callable;
- argument and return types;
- optional-argument macro behaviour;
- null handling and side effects;
- required DuckDB extensions;
- optional Python dependencies;
- safe diagnostic metadata.

The registrar inspects the callable signature rather than requiring every
function package to repeat its parameters manually. Supported type annotations
describe the DuckDB-callable arguments and return value. Unsupported signatures
fail during installation, before project SQL begins.

When `bind_connection` is true, the callable's first parameter receives the
active `DuckDBPyConnection`. The registrar removes that parameter from the
SQL-visible signature and binds the connection before passing the callable to
DuckDB. The prototype demonstrates this cleanly with `functools.partial`;
Quackframe retains the binding behaviour without making that helper part of the
public API.

Optional parameters supported by Quackframe are translated into defaults on
the public macro. The private Python UDF remains fixed-arity, as required by
DuckDB. Unsupported default values, keyword-only parameters, and variadic
parameters fail with a definition error unless Quackframe deliberately adds a
mapping for them.

Functions must use unique public names, register deterministically, avoid
mutating another function's private state, and follow Quackframe's error and
data-safety rules. They do not need common models, providers, or internal base
classes beyond that boundary.

## Function-neutral Boundary

The execution runner opens the DuckDB connection and asks one installer to
register the enabled definitions. It does not know which functions exist, how
they obtain credentials, or whether they need a connection. The registrar
handles only descriptor validation, callable binding, DuckDB registration, and
public macro creation.

Adding a function may add its descriptor to the built-in registry, but it must
not add a function-name branch or function-specific request queue to the runner
or registrar. Function-specific models, strategies, and lifecycle decisions
remain inside the function package.

## Registration

Before project SQL executes, Quackframe:

1. resolves the enabled function definitions;
2. validates unique names, signatures, and function-wide optional dependencies;
3. registers each private Python UDF on the active connection;
4. creates or replaces its public macro in the `quackframe` schema; and
5. reports enabled public names without exposing sensitive configuration.

MVP built-ins belong to one explicit, reviewable registry. The registrar loops
over that collection; it does not discover built-ins by scanning modules or
directories. This makes registration order, optional imports, and the SQL
capability surface deterministic.

Discovery, enablement, and registration remain separate concepts. External
packages may later advertise definitions through Python package entry points,
but discovery would only make them available. A separate allowlist must enable
them before the same generic registrar exposes them to SQL. External discovery
is not required for the MVP.

An optional dependency that belongs to a choice made inside a function is
loaded at that narrower boundary. For example, enabling `register_secret` does
not require Prefect; selecting its `prefect` credential provider does. This
allows other providers to remain independent while the generic function
registrar stays neutral.

## Connection-aware Mutation

A Python UDF that changes the same DuckDB instance may be unable to issue that
change through the connection currently executing the UDF. The prototype avoids
a runner-owned request queue by opening a short-lived duplicate connection to
the same database instance inside the connection-aware function.

`register_secret` uses duplicate-connection execution. The function owns this
behaviour; the core runner has no deferred-operation queue or function-specific
branch. Compatibility is tested against the pinned DuckDB MVP version.

## Persistent Database Consideration

A schema-qualified macro cannot currently be both temporary and stored in an
ordinary `quackframe` schema. In a persistent DuckDB file, public macros may
therefore persist while their Python UDFs remain connection-scoped.

Quackframe recreates enabled macros and private UDFs during every connection
setup. Definitions and signatures are validated before catalog changes begin,
and macro installation is transactional. Persisted macros remain implementation
metadata in persistent databases and are replaced on the next enabled run.

## Related Docs

- [Developer API](developer-api.md): the SQL-facing call convention.
- [Execution Lifecycle](execution-lifecycle.md): when functions are installed.
- [Credential Providers](credential-providers.md): the first planned function
  use case.
- [Configuration](configuration.md): function enablement and optional settings.
