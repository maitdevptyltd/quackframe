# Implementation Review

Temporary notes for decisions agreed during the implementation review. Once a
decision is implemented, move any lasting explanation into the document that
owns the behaviour and remove the completed note from this file.

## Prefect execution names

Status: **Accepted**

File: `src/quackframe/integrations/prefect/runtime.py`

### Current behaviour

The Prefect flow name is changed for each invocation using the runtime folder
name, the first SQL filename, and the number of additional files.

### Decision

- Keep the flow name fixed as `quackframe-run`. Never change it at runtime.
- When it remains a small extension to existing configuration loading, use the
  downstream project's `[project].name` from `pyproject.toml` as the Prefect
  flow run name.
- If that project name is unavailable or using it requires substantial extra
  machinery, leave the flow run name unset and let Prefect generate it.
- Do not derive the flow or flow run name from SQL filenames, timestamps,
  folder names, or Quackframe-generated random values.
- Name each SQL-file execution task from that file's path stem. Keep the full
  path in execution details and errors.

### Reason

The flow represents Quackframe's stable execution process, while a flow run
belongs to the downstream project. An SQL filename describes its individual
task, not the identity of the whole flow or run.

## Prefect runtime loader placement

Status: **Accepted**

File: `src/quackframe/runtimes/registry.py`

### Current behaviour

The runtime registry defines `_load_prefect_runtime()`, but the code does not
explain why a Prefect-specific function belongs in the runtime registry.

### Decision

Add a clear comment explaining that the helper delays the Prefect import until
the Prefect runtime is selected. This allows normal direct execution to work
without Prefect installed and lets Quackframe replace a missing dependency with
an actionable error.

### Reason

Without this explanation, the Prefect-specific helper looks misplaced inside a
general runtime registry. Its location exists to protect the optional dependency
boundary, not to give the registry ownership of Prefect execution behaviour.

## Credential provider registry

Status: **Accepted**

File: `src/quackframe/sql_functions/register_secret/providers/registry.py`

### Current behaviour

`get_provider()` rejects every provider name except `prefect`, imports one
hardcoded module, and always returns `PrefectCredentialProvider`. A new provider
cannot use the existing selection function without rewriting its logic.

### Decision

Rewrite provider selection as a real provider registry. Each provider entry
must describe its public name and how its implementation is loaded. Adding a
new provider should require adding a registry entry and its provider package,
without adding provider-specific branches to `get_provider()` or changing the
secret-registration flow.

Provider implementations must continue to satisfy `CredentialProvider` and
return the existing Quackframe credential models.

### Reason

The provider contract, standard credential models, and registration strategies
were deliberately separated to support multiple credential sources. A
Prefect-only selection function defeats that extension boundary and would make
each new provider require changes to central selection logic.

## Extensible DuckDB secret models

Status: **Accepted**

Files:

- `src/quackframe/sql_functions/register_secret/models.py`
- `src/quackframe/sql_functions/register_secret/strategies.py`
- `src/quackframe/sql_functions/register_secret/function.py`
- `src/quackframe/sql_functions/register_secret/providers/protocol.py`

### Current behaviour

Credential models contain validated data, while `strategies.py` uses a central
secret-type condition to choose separate MSSQL or Azure registration helpers.
Adding a secret type requires editing that central dispatcher.

### Decision

Introduce a provider-independent `DuckDBSecret` abstract Pydantic base model.
Each concrete Quackframe secret model must own:

- its typed credential fields;
- its allowed override resolution and validation; and
- its DuckDB extension loading and temporary-secret registration behaviour.

Prefect Blocks remain storage and retrieval models. The Prefect provider loads
the selected Block and converts it into the corresponding Quackframe
`DuckDBSecret` model. Other providers perform the same conversion from their
own storage formats.

The provider contract returns `DuckDBSecret`. The generic registration function
then asks the returned object to resolve its call-specific overrides and
register itself. It must not branch on concrete secret types. Pydantic model
construction remains responsible for ordinary field validation.

Remove the central secret-type dispatcher once this model-owned behaviour is in
place.

### Reason

Each secret type already owns different fields, overrides, validation,
extensions, and DuckDB registration commands. Keeping those together makes the
model the strategy for that secret type. A new secret type can then be added as
a new model without rewriting the generic registration flow.

This decision covers secret-type extension. Provider discovery remains a
separate concern handled by the credential provider registry decision above.

## Plain-language docstrings

Status: **Accepted**

Scope: all functions, methods, and classes under `src/quackframe`

### Current behaviour

Many docstrings are one sentence long and describe the code's shape rather than
helping a reader understand its purpose. Terms such as "surface" are vague and
important timing, effects, and examples are often omitted.

### Decision

Rewrite docstrings in short, plain-language sections. A useful docstring should
explain what the code controls, when its behaviour occurs, and any important
effect a caller would not immediately know from the name.

Separate distinct concepts into separate paragraphs. Include familiar project
examples when they make a setting or concept concrete. Do not force useful
explanations into one long line, and do not turn docstrings into large essays.

Use this as the reference standard:

```python
class DuckDBConfig(BaseModel):
    """
    Describe how Quackframe prepares a DuckDB session.

    `settings` contains connection options such as `threads`, `memory_limit`,
    and `temp_directory`.

    `extensions` lists DuckDB add-ons such as `azure` and `mssql`, which are
    installed and loaded before SQL files run.
    """
```

### Reason

Docstrings should help a reader understand why code exists without requiring
them to trace several files. Plain wording, separated concepts, and relevant
examples make that possible without adding unnecessary documentation.

## DuckDB function type mapping

Status: **Accepted**

File: `src/quackframe/sql_functions/installer.py`

### Current behaviour

`_duckdb_type()` creates a local `scalar_types` dictionary each time it converts
a Python function annotation into a DuckDB type. This hides the framework's
supported scalar types inside the conversion function.

### Decision

Move the scalar type mapping to a clearly named module-level constant such as
`_DUCKDB_SCALAR_TYPES`.

Keep `_duckdb_type()` responsible for handling optional annotations, the
supported string map, and the error raised for unsupported types. Add new type
mappings only when a real SQL-callable function requires them.

### Reason

The mapping defines which Python input and return types Quackframe can expose
as DuckDB functions. Making it visible at module level documents that framework
boundary, makes supported types easy to find, and gives future additions one
obvious location.

## Runtime registry

Status: **Accepted**

Files:

- `src/quackframe/runtimes/registry.py`
- `src/quackframe/config.py`
- `src/quackframe/cli.py`

### Current behaviour

Runtime names are hardcoded independently in configuration, command-line
choices, and runtime selection. Adding a runtime requires coordinated edits in
all three files.

### Decision

Replace the runtime-selection branches with one explicit runtime registry. Each
entry must provide the public runtime name, its loader, and the actionable
message used when an optional dependency is missing.

Keep optional runtimes lazily loaded. Configuration validation and command-line
choices must use the names exposed by the central registry rather than keeping
their own lists.

Adding a runtime should require its implementation and one registry entry. It
must not require new runtime-name branches in configuration or the command
line.

### Reason

The project presents runtimes as replaceable adapters. A single registry makes
that boundary real while retaining the lazy loading that lets direct execution
work without optional runtime packages installed.

## Provider-specific optional dependencies

Status: **Accepted**

File: `src/quackframe/sql_functions/register_secret/__init__.py`

### Current behaviour

The `register_secret` function declares `required_modules=("prefect",)`. This
requires Prefect whenever the function is enabled, even when a different
credential provider is selected.

### Decision

Remove the global Prefect requirement from the `register_secret` function.
Check optional dependencies only after provider selection, as part of loading
the selected provider.

A non-Prefect provider must be usable without Prefect installed. The Prefect
provider must continue to return an actionable installation error when it is
selected without its dependency.

### Reason

Optional dependencies belong to the integration that uses them. Attaching
Prefect to the provider-independent SQL function defeats the provider boundary
and blocks every future provider from working independently.

## Explicit Prefect secret conversion

Status: **Accepted**

File: `src/quackframe/sql_functions/register_secret/providers/prefect/provider.py`

### Current behaviour

The Prefect provider handles MSSQL explicitly and sends every other secret type
through the Azure conversion path. An unknown or newly added type can therefore
be treated as Azure instead of being rejected clearly.

### Decision

Replace the fallback behaviour with explicit secret-type-to-Block conversion.
Each supported secret type must select its matching Prefect Block and convert
it into the matching Quackframe `DuckDBSecret` model.

Reject unsupported secret types with a clear error. Adding a new secret type
must never make it fall through to an unrelated existing conversion.

### Reason

Explicit conversion protects credential shapes and makes provider support
reviewable. It also prevents future secret types from silently taking the
Azure path when their Prefect conversion has not been implemented.

## Plain-language explanatory comments

Status: **Accepted**

Scope: non-obvious behaviour under `src/quackframe`

### Current behaviour

The current Quackframe source contains only four explanatory comment blocks.
Important decisions involving connection injection, optional imports, generated
SQL, cleanup ownership, provider boundaries, and runtime boundaries are often
left for the reader to infer by tracing several files.

### Decision

Add a higher volume of short explanatory comments around non-obvious code.
Write them in plain, everyday language and explain why the code exists or what
safety rule it protects.

Do not comment straightforward assignments, ordinary control flow, or syntax
that is already obvious. Comments should remove genuine guesswork rather than
narrate each line.

Use the connection-binding code in
`src/quackframe/sql_functions/definition.py` as a reference example:

```python
# Quackframe supplies the active DuckDB connection itself. Remove that first
# parameter from the public SQL signature so SQL callers never provide it.
if self.bind_connection:
    if not parameters:
        raise FunctionDefinitionError(
            f"Connection-bound function '{self.name}' has no parameters"
        )
    parameters = parameters[1:]
```

Review at least these areas for the same treatment:

- delayed imports that keep optional packages optional;
- connection duplication and connection injection;
- generated private functions and public DuckDB macros;
- temporary database ownership and deletion;
- provider and runtime registration boundaries; and
- security rules that prevent secret values entering generated SQL or output.

### Reason

The framework contains architectural and safety decisions that are not obvious
from individual statements. Focused comments let a human reader understand
those decisions without reconstructing them from implementation details and
documentation spread across the repository.
