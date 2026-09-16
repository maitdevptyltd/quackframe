# MAD.Utilities.DuckDB Prototype Reference

`MAD.Utilities.DuckDB` is the functional prototype that informed Quackframe.
It is evidence for useful behaviour, not the documentation template and not an
automatically accepted production contract.

The prototype repository may not be available to every public contributor. The
relevant product meaning is retained here so Quackframe's public design does
not depend on access to private source material.

## Demonstrated Behaviour

The prototype demonstrates:

- a command accepting one or more ordered SQL files;
- one DuckDB connection shared across those files;
- DuckDB parser-based statement extraction;
- fail-fast errors with file and statement context;
- in-memory or file-backed DuckDB execution;
- cleanup policies for file-backed runs;
- a function-neutral descriptor and explicit registry for SQL-callable Python
  functions;
- callable-signature inspection and active-connection binding;
- generated macro handling for optional Python UDF arguments;
- immediate same-instance mutation through a duplicate DuckDB connection;
- Prefect flow and task instrumentation;
- Prefect Block resolution into temporary MSSQL and scoped Azure
  connection-string DuckDB secrets; and
- safe credential handling through bound parameters.

## Behaviour Carried Forward

Quackframe intends to retain:

- explicit ordered files and a shared DuckDB session;
- one stable execution path for interactive and automated runs;
- safe failure attribution and process exit codes;
- SQL-callable Python capabilities through a registry;
- signature-aware registration and connection-aware callable binding;
- a runner that delegates function installation without understanding concrete
  function behaviour;
- an optional Prefect runtime; and
- temporary MSSQL and Azure connection-string secret registration as initial
  extension use cases.

## Behaviour Reconsidered

Quackframe deliberately revisits:

- direct Prefect imports in the core runner;
- Prefect decoration of core execution functions;
- unconditional import of a Prefect-backed function from the built-in registry;
- a global cleanup policy that may delete a caller-supplied database path;
- internal deployment terminology in a public project.

## Function Registration Takeaways

The reviewed local prototype uses a small descriptor to inspect each callable's
signature, remove an injected DuckDB connection from the SQL-visible arguments,
bind that connection with `functools.partial`, and generate a public macro for
supported optional parameters. One generic registrar loops over an explicit
registry and installs every descriptor. The SQL runner calls that registrar
without naming or branching on individual functions.

Quackframe carries that separation forward. It will change the public naming to
`quackframe.<function_name>`, keep all Python UDF names private, and keep
Prefect-backed providers out of base imports. Built-in registry membership
remains explicit; automatic module scanning is not part of the MVP.

The prototype's `register_prefect_secret` function also duplicates the active
DuckDB connection before creating a temporary secret. This removes the earlier
credential-specific request queue from the runner. Quackframe treats that as
valuable implementation evidence, subject to compatibility tests rather than
an automatically accepted cross-version guarantee.

## Quackframe Decisions Beyond The Prototype

- Core execution is orchestrator-agnostic.
- Prefect support is an optional dependency and adapter.
- Credential providers are independent of runtime selection.
- The provider is selected by the credential function call.
- The runtime root defaults to the current working directory.
- Stable project configuration uses `pyproject.toml` as an input to a typed
  `QuackframeConfig` model.
- Each SQL function is a self-contained unit of work; duplication is preferable
  to restrictive coupling.
- Public calls use `quackframe.<function_name>` macros over private
  `_quackframe_<function_name>` Python UDFs.

## Related Docs

- [Overview](overview.md): Quackframe's accepted product identity.
- [Execution Lifecycle](execution-lifecycle.md): the generalized runner.
- [Runtime Adapters](runtime-adapters.md): the extracted Prefect runtime boundary.
- [Credential Providers](credential-providers.md): generalized credential
  resolution.
- [Roadmap](roadmap.md): the delivered MVP sequence.
