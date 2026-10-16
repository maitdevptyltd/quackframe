# DuckDB Error Diagnostics: Empirical Investigation

Date: 2026-10-15. DuckDB: locked and runtime **1.5.5**, engine commit
`d8cdaa33fd` (Variegata). Python: **3.13.9**. Platform:
**Windows-11-10.0.26200-SP0**. Repository baseline:
`e187b7eb0b9f0005afd17a0938afbce75d5c0218`. Scope: synthetic, offline Python
client observations; no Quackframe error-handling changes.

| Potential source | Practical assessment | What the evidence establishes |
| --- | --- | --- |
| Stored values and imported CSV rows | Ordinary processing failures; strong relevance | Casts, malformed JSON, duplicate keys and CSV conversion can print input values without an instruction to log them. |
| Values passed as parameters or SQL literals | Ordinary use, with sensitivity dependent on the actual value | Binding does not prevent a conversion diagnostic from echoing a parameter. Text SQL excerpts can include unrelated literals. |
| PIVOT-derived identifiers | Legitimate transformation; contextual sensitivity | A stored category becomes a column name automatically, then appears in binder suggestions. No manually secret-named table is needed. |
| Ordinary table/column/parameter names | Useful diagnostic metadata; no confidentiality established by these fixtures | A marker containing PRIVATE is still just a name. Repeating it does not demonstrate a password disclosure. |
| Ordinary paths and filenames | Useful diagnostic metadata; contextual sensitivity | The probes establish path echoing, not that the path is a credential or confidential customer information. |
| Credential-bearing URLs | Plausible legitimate access input | The permission-denial probe echoes a whole token-bearing URL. It does not test successful authentication or remote errors. |
| Explicit custom messages | Caller-authored disclosure | Calling error(password) asks for that text to become an error. It is not an accidental credential extraction by the engine. |
| Python UDF messages and exception chains | Plausible propagation mechanisms, deliberately constructed fixtures | Arbitrary messages and underlying errors survive forwarding. No actual upstream SDK or Quackframe wrapper was exercised. |

## Practical findings

Ordinary processing failures can expose supplied values without an instruction
to log them: casts, malformed JSON, duplicate keys and CSV import failures
provide direct evidence. PIVOT also turns stored categories into column names
that can appear in suggestions; sensitivity depends on those categories.

Other probes establish only that diagnostic metadata or explicitly authored
messages are repeated. PRIVATE or SECRET in a synthetic identifier does not
establish confidentiality. A path used as a function name and a password passed
to error(...) are deliberately constructed cases, not evidence of ordinary
credential extraction by the engine.

The 64/84 marker count describes a constructed sample, not a workload exposure
rate or 64 independent vulnerabilities. The 84 runs repeat 42 scenarios in two
formats; repr, args and tracebacks often repeat the same underlying message.
No production likelihood or universal safety of an error category was measured.

## Documented categories and diagnostic contracts

The official [Python API reference](https://duckdb.org/docs/current/clients/python/reference/)
lists the following hierarchy (also inspected in the installed 1.5.5 module).
The hierarchy is an API inventory, not a guarantee about message contents:

| Parent | Documented classes |
| --- | --- |
| Exception | Error, Warning |
| Error | DatabaseError |
| DatabaseError | DataError, IntegrityError, InternalError, NotSupportedError, OperationalError, ProgrammingError, DependencyException, FatalException, InterruptException, PermissionException, SequenceException |
| DataError | ConversionException, OutOfRangeException, TypeMismatchException |
| IntegrityError | ConstraintException |
| InternalError | InternalException |
| NotSupportedError | NotImplementedException |
| OperationalError | ConnectionException, IOException, OutOfMemoryException, SerializationException, TransactionException |
| ProgrammingError | BinderException, CatalogException, InvalidInputException, InvalidTypeException, ParserException, SyntaxException |
| IOException | HTTPException |

The [JSON diagnostics documentation](https://duckdb.org/docs/current/configuration/pragmas#returning-errors-as-json)
documents `errors_as_json` and extra/decomposed information for some errors.
Its example includes category, message, name, candidates, position, object type
and subtype. It does not state that these fields exclude sensitive values or
that every error has the same schema. The
[configuration reference](https://duckdb.org/docs/current/configuration/overview)
lists its default as false. The
[Python UDF documentation](https://duckdb.org/docs/current/clients/python/function#exception-handling)
describes default exception forwarding and illustrates an InvalidInputException
containing the Python exception message and function-location information.

The [internal-errors documentation](https://duckdb.org/docs/current/dev/internal_errors)
describes assertion failures and the resulting restricted database state.
Those examples are documentation evidence, not reproduced failures here.

The version-pinned [ExceptionType enum](https://github.com/duckdb/duckdb/blob/v1.5.5/src/include/duckdb/common/exception.hpp#L42-L87)
provides a broader engine inventory than the Python class names:
INVALID, OUT_OF_RANGE, CONVERSION, UNKNOWN_TYPE, DECIMAL, MISMATCH_TYPE,
DIVIDE_BY_ZERO, OBJECT_SIZE, INVALID_TYPE, SERIALIZATION, TRANSACTION,
NOT_IMPLEMENTED, EXPRESSION, CATALOG, PARSER, PLANNER, SCHEDULER, EXECUTOR,
CONSTRAINT, INDEX, STAT, CONNECTION, SYNTAX, SETTINGS, BINDER, NETWORK,
OPTIMIZER, NULL_POINTER, IO, INTERRUPT, FATAL, INTERNAL, INVALID_INPUT,
OUT_OF_MEMORY, PERMISSION, PARAMETER_NOT_RESOLVED, PARAMETER_NOT_ALLOWED,
DEPENDENCY, HTTP, MISSING_EXTENSION, AUTOLOAD, SEQUENCE, INVALID_CONFIGURATION.
This is source evidence; an enum entry is not proof of a reproducible public
query or a distinct Python class.

Version-pinned [error formatting source](https://github.com/duckdb/duckdb/blob/v1.5.5/src/common/error_data.cpp#L111-L140)
shows JSON conversion using type, message and extra information, and text
location formatting using the query and stored position. It also handles
stack-trace information. The
[exception implementation](https://github.com/duckdb/duckdb/blob/v1.5.5/src/common/exception.cpp)
maps internal types to diagnostic names. These explain mechanisms; the
observations below establish which surfaces appeared in these runs.
Documentation was consulted on 2026-10-15; `/current/` pages can change.

## Method and evidence boundaries

Each scenario runs once with text diagnostics and once with JSON requested,
serially in fresh child processes. Each child has a 15-second timeout, one
DuckDB thread, a 128 MB DuckDB memory limit and no disk spill allowance.
The memory setting bounds DuckDB-managed memory, not the Python process's
entire resident set. Queries and fixtures are tiny; no stress probes run.
Autoload and automatic extension installation are disabled. The URL probe
also disables external access before execution. There are no network SQL
operations, real credentials, `.env` reads or customer data.

The [probe definitions](../tests/investigations/duckdb_errors/probe.py) contain
every setup statement and special Python action. The
[dedicated tests](../tests/investigations/duckdb_errors/test_diagnostics.py)
assert completion, an actual error, nonempty diagnostics and locked-version
agreement. They are an empirical collection harness, not a universal
redaction test or an assertion that a category is safe. The
[machine-readable observations](../tests/investigations/duckdb_errors/observations.json)
retain complete captured messages, structured fields, repr, args, causes,
contexts, formatted tracebacks and per-surface marker matches.
Only absolute temporary-directory and probe-file paths are normalized to
`<fixture>` and `<probe.py>`; SQL, diagnostic messages and line numbers are
otherwise retained. Python's default traceback formatting does not capture
frame locals. Fake-marker matches in source-code lines within a traceback
are not automatically proof of a DuckDB-message disclosure; the separate
surface map identifies each occurrence. Marker matching is case-insensitive:
binder struct-key and catalog function-name diagnostics lowercase some inputs.
The retained output shows their actual spelling.

Status vocabulary: **observed marker repetition** means the supplied marker appeared
on the named diagnostic surface; **no exposure observed** is scoped to that
scenario/surface. A marker match alone does not establish sensitivity. **Not tested** means no probe ran; **unavailable** means a
requested representation did not appear; **unclassified** is reserved for an
output that could not be assigned a category. Python classes and engine
category names are reported separately. Zero native crashes/timeouts occurred
in the completed suite. No implementation epic was changed: this investigation
does not change the public contract or implement a new error policy.

## Scenario-level assessment

Each ID below denotes both `test_diagnostic_probe[text-ID]` and
`test_diagnostic_probe[json-ID]` in the
[test harness](../tests/investigations/duckdb_errors/test_diagnostics.py).
"Both" means text and JSON-requested runs; it does not mean every possible
rendering or execution environment. The labels assess the mechanism, not its
frequency in production:

- **Ordinary data:** legitimate processing can expose supplied values incidentally.
- **Metadata:** output is operational information; the fixture does not establish sensitivity.
- **Contextual:** plausible relevance, but dependent on use or limited by constructed evidence.
- **Deliberate:** the fixture explicitly places marked text in a message or unusual name.
- **Control:** useful comparison or coverage evidence without a sensitive marker disclosure.

| Scenario ID | Assessment | Observed result and practical meaning |
| --- | --- | --- |
| `parser_literal` | Ordinary data | Text quotes the SQL line including the literal; JSON omits it. A syntax error can expose a legitimate data literal without an instruction to print it. |
| `parser_token` | Metadata | Both repeat the invalid token. Calling an identifier PRIVATE does not make the syntax diagnostic a demonstrated secret leak. |
| `parser_multiline` | Control | Neither repeats the literal; the error is at end of input. Useful evidence about excerpt/location variation. |
| `parser_path` | Contextual | Text repeats a path-shaped literal; JSON omits it. Artificial expression, but illustrates incidental excerpt inclusion. Path confidentiality is not established. |
| `parser_path_token` | Contextual | Both quote a path-shaped invalid token. Could resemble a SQL authoring mistake; there is no credential or row disclosure in this fixture. |
| `binder_key_literal` | Metadata | Both repeat the requested struct key, lowercased. Key lookup errors are normal; the SECRET label does not establish a sensitive value. |
| `catalog_path_identifier` | Deliberate | Both repeat a path-shaped function name from `SELECT "FAKE_PATH_PRIVATE/file.csv"()`. It never opens a file. Weak evidence for practical sensitive-path disclosure. |
| `binder_literal` | Ordinary data | Text's SQL excerpt includes an unrelated literal; JSON omits it. The failing column reference need not itself be sensitive. |
| `binder_candidates` | Metadata | Both suggest the manually named column. Normal useful diagnostics, with no actual table value or credential exposed by this test. |
| `catalog_identifier` | Metadata | Both name the missing table. It is a synthetic identifier, not a password; a password-as-table-name interpretation adds an assumption absent from the evidence. |
| `catalog_literal` | Ordinary data | Text includes an unrelated literal when reporting a missing table; JSON omits it. This is stronger evidence than merely giving a table a PRIVATE name. |
| `catalog_candidates` | Metadata | Both suggest the existing table after a typo. Useful metadata; the fixture demonstrates name matching rather than confidential content. |
| `conversion_literal` | Ordinary data | Both echo the failed cast's literal. A normal incorrect type conversion can print a personal/business input. |
| `conversion_parameter` | Ordinary data | Both echo the bound value despite the SQL containing only `?`. Strong evidence that parameterization and diagnostic disclosure are different concerns. |
| `conversion_row` | Ordinary data | Both print a stored value from a failed cast. No SQL instruction asks to log that value. |
| `constraint_row` | Ordinary data | Both print the duplicate UNIQUE key selected from a source table. Legitimate inserts can fail this way. |
| `check_row` | Control | Neither prints the stored marker; both describe the CHECK expression. Contrasts with UNIQUE behavior; does not prove all CHECK diagnostics safe. |
| `custom_literal` | Deliberate | Both return exactly the message supplied to `error(...)`. Expected caller-authored output, not incidental disclosure. |
| `custom_row` | Deliberate | Both return the value explicitly passed to `error(v)`. Real row provenance, but deliberately turning it into a message differs from an engine-generated failure. |
| `custom_connection_string` | Deliberate | Both return the host/password string explicitly passed to `error(?)`. No connector, authentication attempt or driver-generated disclosure was tested. |
| `udf_message` | Contextual | Both forward a hand-written ValueError containing a row and fake secret. UDF forwarding is relevant, but the fake upstream secret was authored by the probe, not discovered in an SDK failure. |
| `python_chain` | Contextual | A real failed parameter cast is wrapped in two deliberately authored Python exceptions. Its text survives nested causes/contexts. This demonstrates Python propagation, not a defect in Quackframe's current wrapper. |
| `missing_file` | Metadata | Both repeat the missing path. Necessary context for an ordinary file error; PRIVATE in the fixture name does not establish confidential content. |
| `url_blocked` | Contextual | Both echo the full URL and query token before network access. Token-bearing access URLs can be legitimate inputs; unlike error(password), this operation asks to read data. Only configuration denial was tested. |
| `csv_row` | Ordinary data | Both include the original CSV line and conversion value, as well as the filename. Strong incidental data disclosure from routine import failure. |
| `parquet_invalid` | Metadata | Both report the filename lacking magic bytes. The synthetic file content marker is not printed. Do not classify this as a demonstrated file-content disclosure. |
| `json_row` | Ordinary data | Both print malformed JSON input read from a table. Normal validation/conversion failure, not an explicit custom message. |
| `regex_parameter` | Contextual | Both echo an invalid supplied regex. User-authored patterns may contain data, but an ordinary pattern is not inherently confidential. |
| `range` | Contextual | Both print the stored numeric overflow operand. Genuine data provenance, but the maximum BIGINT boundary is not itself personal information; the test establishes value echoing only. |
| `transaction` | Control | No marker; output describes an already-open transaction. No meaningful confidential payload was supplied. |
| `dependency` | Control | The parent marker is omitted, while ordinary child-table name `child` is printed. A zero marker count does not mean no metadata appears. Produced CatalogException, not DependencyException. |
| `not_implemented` | Control | Generic unsupported ALTER message; supplied constraint-name marker omitted. No category-wide confidentiality conclusion follows. |
| `sequence` | Metadata | Both name the exhausted sequence and its limit. These are operational details; the PRIVATE name is not evidence of a credential. |
| `closed_connection` | Control | Generic connection-closed error omits the unused literal. JSON was unavailable at the top level. |
| `parameter_missing` | Metadata | Both print the missing parameter name. No bound parameter value exists in this scenario. |
| `setting` | Contextual | Both echo a string incorrectly supplied as a thread count. Invalid configuration is plausible; interpreting that string as secret requires extra assumptions. |
| `extension_missing` | Metadata | Both print an extension path. Useful diagnostic location; no credential or file-content exposure demonstrated. |
| `pivot_conversion` | Ordinary data | Both print the stored failed-cast value during aggregation. An ordinary conversion failure inside PIVOT. |
| `pivot_candidate` | Contextual | Both suggest a column automatically derived from a stored category. Genuine row-to-identifier propagation, not a caller naming a table after a password. Sensitivity depends on the pivoted values. |
| `multiline_binder` | Control | The literal on another line is omitted in both; text identifies the failing line. Useful evidence for diagnostic precision. |
| `unicode_position` | Ordinary data | Text includes a literal; JSON omits it and reports a UTF-8 byte offset. Valuable both for excerpt behavior and location interpretation. |
| `extract_parser` | Ordinary data | Statement extraction, without execution, includes the literal in text but omits it in JSON. Exposure can occur before data execution. |

## Scenario results

The following records are generated from the retained observations. Test IDs
are `test_diagnostic_probe[text-ID]` and `test_diagnostic_probe[json-ID]` in the
dedicated test file. SQL setup executes before the failing statement. Parameters
are bound through `execute(sql, parameters)`; special actions are named explicitly.
Output excerpts trim trailing whitespace and are capped at 2,400 characters per mode; the JSON evidence has
the full output. Position comparisons use zero-based character and UTF-8 byte
offsets of an explicitly chosen anchor, not an assumption that every diagnostic
must point there.

<!-- SCENARIO RESULTS -->

### parser_literal

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parser_literal`, `json-parser_literal`. Source under test: literal. Python action: `execute`.

```sql
SELECT 'FAKE_LITERAL_SECRET' + FROM x;
```

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at or near "FROM"

LINE 1: SELECT 'FAKE_LITERAL_SECRET' + FROM x
                                       ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at or near \"FROM\"",
  "position": "31",
  "error_subtype": "SYNTAX_ERROR"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `31`. Chosen anchor `FROM` starts at character `31` / UTF-8 byte `31`.

### parser_token

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parser_token`, `json-parser_token`. Source under test: identifier. Python action: `execute`.

```sql
SELECT 1 AS x FAKE_IDENTIFIER_PRIVATE;
```

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at or near "FAKE_IDENTIFIER_PRIVATE"

LINE 1: SELECT 1 AS x FAKE_IDENTIFIER_PRIVATE
                      ^
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at or near \"FAKE_IDENTIFIER_PRIVATE\"",
  "position": "14",
  "error_subtype": "SYNTAX_ERROR"
}
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `14`. Chosen anchor `FAKE_IDENTIFIER_PRIVATE` starts at character `14` / UTF-8 byte `14`.

### parser_multiline

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parser_multiline`, `json-parser_multiline`. Source under test: literal. Python action: `execute`.

```sql
SELECT
 'FAKE_LITERAL_SECRET',
 FROM;
```

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at end of input
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at end of input",
  "position": "36",
  "error_subtype": "SYNTAX_ERROR"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `36`. Chosen anchor `FROM` starts at character `32` / UTF-8 byte `32`.

### parser_path

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parser_path`, `json-parser_path`. Source under test: path. Python action: `execute`.

```sql
SELECT '/FAKE_PATH_PRIVATE/file.csv' + FROM x;
```

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at or near "FROM"

LINE 1: SELECT '/FAKE_PATH_PRIVATE/file.csv' + FROM x
                                               ^
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at or near \"FROM\"",
  "position": "39",
  "error_subtype": "SYNTAX_ERROR"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `39`. Chosen anchor `FROM` starts at character `39` / UTF-8 byte `39`.

### parser_path_token

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parser_path_token`, `json-parser_path_token`. Source under test: path. Python action: `execute`.

```sql
SELECT 1 '/FAKE_PATH_PRIVATE/file.csv';
```

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at or near "'/FAKE_PATH_PRIVATE/file.csv'"

LINE 1: SELECT 1 '/FAKE_PATH_PRIVATE/file.csv'
                 ^
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at or near \"'/FAKE_PATH_PRIVATE/file.csv'\"",
  "position": "9",
  "error_subtype": "SYNTAX_ERROR"
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `9`. Chosen anchor `'/FAKE_PATH_PRIVATE/file.csv'` starts at character `9` / UTF-8 byte `9`.

### binder_key_literal

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-binder_key_literal`, `json-binder_key_literal`. Source under test: literal. Python action: `execute`.

```sql
SELECT struct_extract({'a':1}, 'FAKE_LITERAL_SECRET');
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Could not find key "fake_literal_secret" in struct

Candidate Entries: "a"
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Could not find key \"fake_literal_secret\" in struct\n\nCandidate Entries: \"a\""
}
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### catalog_path_identifier

Practical classification: **Deliberate**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-catalog_path_identifier`, `json-catalog_path_identifier`. Source under test: path. Python action: `execute`.

```sql
SELECT "FAKE_PATH_PRIVATE/file.csv"();
```

**Text:** `CatalogException`; engine category: not a structured field.

```text
Catalog Error: Scalar Function with name fake_path_private/file.csv does not exist!
Did you mean "has_table_privilege"?

LINE 1: SELECT "FAKE_PATH_PRIVATE/file.csv"()
               ^
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `CatalogException`; engine category: Catalog.

```json
{
  "exception_type": "Catalog",
  "exception_message": "Scalar Function with name fake_path_private/file.csv does not exist!\nDid you mean \"has_table_privilege\"?",
  "candidates": "has_table_privilege",
  "position": "7",
  "error_subtype": "MISSING_ENTRY",
  "name": "fake_path_private/file.csv",
  "type": "Scalar Function"
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `structured.name`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `7`. No comparison anchor specified.

### binder_literal

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-binder_literal`, `json-binder_literal`. Source under test: literal. Python action: `execute`.

```sql
SELECT absent, 'FAKE_LITERAL_SECRET';
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Referenced column "absent" was not found because the FROM clause is missing

LINE 1: SELECT absent, 'FAKE_LITERAL_SECRET'
               ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Referenced column \"absent\" was not found because the FROM clause is missing",
  "position": "7",
  "error_subtype": "COLUMN_NOT_FOUND",
  "name": "absent"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `7`. Chosen anchor `absent` starts at character `7` / UTF-8 byte `7`.

### binder_candidates

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-binder_candidates`, `json-binder_candidates`. Source under test: candidate. Python action: `execute`.

```sql
CREATE TABLE t(FAKE_CANDIDATE_PRIVATE INT);
SELECT missing FROM t;
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Referenced column "missing" not found in FROM clause!
Candidate bindings: "FAKE_CANDIDATE_PRIVATE"

LINE 1: SELECT missing FROM t
               ^
```

Observed marker repetition: `FAKE_CANDIDATE_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_CANDIDATE_PRIVATE`.

Actual table-derived value marker: no exposure observed.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Referenced column \"missing\" not found in FROM clause!\nCandidate bindings: \"FAKE_CANDIDATE_PRIVATE\"",
  "candidates": "FAKE_CANDIDATE_PRIVATE",
  "position": "7",
  "error_subtype": "COLUMN_NOT_FOUND",
  "name": "missing"
}
```

Observed marker repetition: `FAKE_CANDIDATE_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `structured.candidates`, `traceback`: `FAKE_CANDIDATE_PRIVATE`.

Actual table-derived value marker: no exposure observed.

Reported `position`: `7`. Chosen anchor `missing` starts at character `7` / UTF-8 byte `7`.

### catalog_identifier

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-catalog_identifier`, `json-catalog_identifier`. Source under test: identifier. Python action: `execute`.

```sql
SELECT * FROM FAKE_IDENTIFIER_PRIVATE;
```

**Text:** `CatalogException`; engine category: not a structured field.

```text
Catalog Error: Table with name FAKE_IDENTIFIER_PRIVATE does not exist!
Did you mean "pg_am"?

LINE 1: SELECT * FROM FAKE_IDENTIFIER_PRIVATE
                      ^
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `CatalogException`; engine category: Catalog.

```json
{
  "exception_type": "Catalog",
  "exception_message": "Table with name FAKE_IDENTIFIER_PRIVATE does not exist!\nDid you mean \"pg_am\"?",
  "candidates": "pg_am",
  "position": "14",
  "error_subtype": "MISSING_ENTRY",
  "name": "FAKE_IDENTIFIER_PRIVATE",
  "type": "Table"
}
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `structured.name`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `14`. Chosen anchor `FAKE_IDENTIFIER_PRIVATE` starts at character `14` / UTF-8 byte `14`.

### catalog_literal

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-catalog_literal`, `json-catalog_literal`. Source under test: literal. Python action: `execute`.

```sql
SELECT 'FAKE_LITERAL_SECRET' FROM absent;
```

**Text:** `CatalogException`; engine category: not a structured field.

```text
Catalog Error: Table with name absent does not exist!
Did you mean "pg_settings"?

LINE 1: SELECT 'FAKE_LITERAL_SECRET' FROM absent
                                          ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `CatalogException`; engine category: Catalog.

```json
{
  "exception_type": "Catalog",
  "exception_message": "Table with name absent does not exist!\nDid you mean \"pg_settings\"?",
  "candidates": "pg_settings",
  "position": "34",
  "error_subtype": "MISSING_ENTRY",
  "name": "absent",
  "type": "Table"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `34`. Chosen anchor `absent` starts at character `34` / UTF-8 byte `34`.

### catalog_candidates

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-catalog_candidates`, `json-catalog_candidates`. Source under test: candidate. Python action: `execute`.

```sql
CREATE TABLE FAKE_CANDIDATE_PRIVATE(i INT);
SELECT * FROM FAKE_CANDIDATE_PRIVAT;
```

**Text:** `CatalogException`; engine category: not a structured field.

```text
Catalog Error: Table with name FAKE_CANDIDATE_PRIVAT does not exist!
Did you mean "FAKE_CANDIDATE_PRIVATE"?

LINE 1: SELECT * FROM FAKE_CANDIDATE_PRIVAT
                      ^
```

Observed marker repetition: `FAKE_CANDIDATE_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_CANDIDATE_PRIVATE`.

Actual table-derived value marker: no exposure observed.

**JSON requested:** `CatalogException`; engine category: Catalog.

```json
{
  "exception_type": "Catalog",
  "exception_message": "Table with name FAKE_CANDIDATE_PRIVAT does not exist!\nDid you mean \"FAKE_CANDIDATE_PRIVATE\"?",
  "candidates": "FAKE_CANDIDATE_PRIVATE",
  "position": "14",
  "error_subtype": "MISSING_ENTRY",
  "name": "FAKE_CANDIDATE_PRIVAT",
  "type": "Table"
}
```

Observed marker repetition: `FAKE_CANDIDATE_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `structured.candidates`, `traceback`: `FAKE_CANDIDATE_PRIVATE`.

Actual table-derived value marker: no exposure observed.

Reported `position`: `14`. No comparison anchor specified.

### conversion_literal

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-conversion_literal`, `json-conversion_literal`. Source under test: literal. Python action: `execute`.

```sql
SELECT CAST('FAKE_LITERAL_SECRET' AS INTEGER);
```

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: Could not convert string 'FAKE_LITERAL_SECRET' to INT32

LINE 1: SELECT CAST('FAKE_LITERAL_SECRET' AS INTEGER)
               ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "Could not convert string 'FAKE_LITERAL_SECRET' to INT32",
  "position": "7"
}
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `7`. Chosen anchor `CAST` starts at character `7` / UTF-8 byte `7`.

### conversion_parameter

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-conversion_parameter`, `json-conversion_parameter`. Source under test: parameter. Python action: `execute`.

```sql
SELECT CAST(? AS INTEGER);
```

Bound parameters: `['FAKE_PARAMETER_SECRET']`.

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: Could not convert string 'FAKE_PARAMETER_SECRET' to INT32

LINE 1: SELECT CAST(? AS INTEGER)
               ^
```

Observed marker repetition: `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "Could not convert string 'FAKE_PARAMETER_SECRET' to INT32",
  "position": "7"
}
```

Observed marker repetition: `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `7`. Chosen anchor `CAST` starts at character `7` / UTF-8 byte `7`.

### conversion_row

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-conversion_row`, `json-conversion_row`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE t(v VARCHAR);
INSERT INTO t VALUES ('FAKE_ROW_PERSONAL');
SELECT CAST(v AS INTEGER) FROM t;
```

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: Could not convert string 'FAKE_ROW_PERSONAL' to INT32 when casting from source column v

LINE 1: SELECT CAST(v AS INTEGER) FROM t
               ^
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "Could not convert string 'FAKE_ROW_PERSONAL' to INT32 when casting from source column v",
  "position": "7"
}
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

Reported `position`: `7`. Chosen anchor `CAST` starts at character `7` / UTF-8 byte `7`.

### constraint_row

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-constraint_row`, `json-constraint_row`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE source(v VARCHAR);
INSERT INTO source VALUES ('FAKE_ROW_BUSINESS');
CREATE TABLE target(v VARCHAR UNIQUE);
INSERT INTO target SELECT v FROM source;
INSERT INTO target SELECT v FROM source;
```

**Text:** `ConstraintException`; engine category: not a structured field.

```text
Constraint Error: Duplicate key "v: FAKE_ROW_BUSINESS" violates unique constraint.
```

Observed marker repetition: `FAKE_ROW_BUSINESS`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_BUSINESS`.

Actual table-derived value marker: observed.

**JSON requested:** `ConstraintException`; engine category: Constraint.

```json
{
  "exception_type": "Constraint",
  "exception_message": "Duplicate key \"v: FAKE_ROW_BUSINESS\" violates unique constraint."
}
```

Observed marker repetition: `FAKE_ROW_BUSINESS`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_BUSINESS`.

Actual table-derived value marker: observed.

No structured position field observed.

### check_row

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-check_row`, `json-check_row`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE source(v VARCHAR);
INSERT INTO source VALUES ('FAKE_ROW_PERSONAL');
CREATE TABLE target(v VARCHAR CHECK(length(v)<2));
INSERT INTO target SELECT v FROM source;
```

**Text:** `ConstraintException`; engine category: not a structured field.

```text
Constraint Error: CHECK constraint failed on table target with expression CHECK((length(v) < 2))
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

**JSON requested:** `ConstraintException`; engine category: Constraint.

```json
{
  "exception_type": "Constraint",
  "exception_message": "CHECK constraint failed on table target with expression CHECK((length(v) < 2))"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

No structured position field observed.

### custom_literal

Practical classification: **Deliberate**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-custom_literal`, `json-custom_literal`. Source under test: custom. Python action: `execute`.

```sql
SELECT error('FAKE_CUSTOM_SECRET');
```

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: FAKE_CUSTOM_SECRET
```

Observed marker repetition: `FAKE_CUSTOM_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_CUSTOM_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "FAKE_CUSTOM_SECRET"
}
```

Observed marker repetition: `FAKE_CUSTOM_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_CUSTOM_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### custom_row

Practical classification: **Deliberate**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-custom_row`, `json-custom_row`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE t(v VARCHAR);
INSERT INTO t VALUES ('FAKE_ROW_PERSONAL');
SELECT error(v) FROM t;
```

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: FAKE_ROW_PERSONAL
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "FAKE_ROW_PERSONAL"
}
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

No structured position field observed.

### custom_connection_string

Practical classification: **Deliberate**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-custom_connection_string`, `json-custom_connection_string`. Source under test: connection string. Python action: `execute`.

```sql
SELECT error(?);
```

Bound parameters: `['Host=FAKE_HOST_PRIVATE;Password=FAKE_CONNECTION_SECRET']`.

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: Host=FAKE_HOST_PRIVATE;Password=FAKE_CONNECTION_SECRET
```

Observed marker repetition: `FAKE_CONNECTION_SECRET`, `FAKE_HOST_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_HOST_PRIVATE`, `FAKE_CONNECTION_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "Host=FAKE_HOST_PRIVATE;Password=FAKE_CONNECTION_SECRET"
}
```

Observed marker repetition: `FAKE_CONNECTION_SECRET`, `FAKE_HOST_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_HOST_PRIVATE`, `FAKE_CONNECTION_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### udf_message

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-udf_message`, `json-udf_message`. Source under test: upstream. Python action: `udf`.

```sql
CREATE TABLE t(v VARCHAR);
INSERT INTO t VALUES ('FAKE_ROW_PERSONAL');
SELECT upstream(v) FROM t;
```

Register `upstream(value: str) -> str`, raising `ValueError("FAKE_UPSTREAM_SECRET: " + value)`.

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: Python exception occurred while executing the UDF: ValueError: FAKE_UPSTREAM_SECRET: FAKE_ROW_PERSONAL

At:
  <probe.py>(316): upstream
  <probe.py>(323): execute
  <probe.py>(403): probe
  <probe.py>(446): <module>

```

Observed marker repetition: `FAKE_ROW_PERSONAL`, `FAKE_UPSTREAM_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_PERSONAL`, `FAKE_UPSTREAM_SECRET`.

Actual table-derived value marker: observed.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "Python exception occurred while executing the UDF: ValueError: FAKE_UPSTREAM_SECRET: FAKE_ROW_PERSONAL\n\nAt:\n  <probe.py>(316): upstream\n  <probe.py>(323): execute\n  <probe.py>(403): probe\n  <probe.py>(446): <module>\n"
}
```

Observed marker repetition: `FAKE_ROW_PERSONAL`, `FAKE_UPSTREAM_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_PERSONAL`, `FAKE_UPSTREAM_SECRET`.

Actual table-derived value marker: observed.

No structured position field observed.

### python_chain

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-python_chain`, `json-python_chain`. Source under test: cause/context. Python action: `chain`.

```sql
SELECT CAST(? AS INTEGER);
```

Bound parameters: `['FAKE_PARAMETER_SECRET']`.

Catch the DuckDB error; raise `ValueError("FAKE_CONTEXT_SECRET")` from it, then `RuntimeError("FAKE_CAUSE_SECRET")` from that wrapper.

**Text:** `RuntimeError`; engine category: not a structured field.

```text
FAKE_CAUSE_SECRET
```

Observed marker repetition: `FAKE_CAUSE_SECRET`, `FAKE_CONTEXT_SECRET`, `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`: `FAKE_CAUSE_SECRET`.

- `traceback`: `FAKE_PARAMETER_SECRET`, `FAKE_CAUSE_SECRET`, `FAKE_CONTEXT_SECRET`.

- `cause.message`, `cause.repr`, `cause.args`, `context.message`, `context.repr`, `context.args`: `FAKE_CONTEXT_SECRET`.

- `cause.traceback`, `context.traceback`: `FAKE_PARAMETER_SECRET`, `FAKE_CONTEXT_SECRET`.

- `cause.cause.message`, `cause.cause.repr`, `cause.cause.args`, `cause.cause.traceback`, `cause.context.message`, `cause.context.repr`, `cause.context.args`, `cause.context.traceback`, `context.cause.message`, `context.cause.repr`, `context.cause.args`, `context.cause.traceback`, `context.context.message`, `context.context.repr`, `context.context.args`, `context.context.traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `RuntimeError`; engine category: not a structured field.

```text
FAKE_CAUSE_SECRET
```

Observed marker repetition: `FAKE_CAUSE_SECRET`, `FAKE_CONTEXT_SECRET`, `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`: `FAKE_CAUSE_SECRET`.

- `traceback`: `FAKE_PARAMETER_SECRET`, `FAKE_CAUSE_SECRET`, `FAKE_CONTEXT_SECRET`.

- `cause.message`, `cause.repr`, `cause.args`, `context.message`, `context.repr`, `context.args`: `FAKE_CONTEXT_SECRET`.

- `cause.traceback`, `context.traceback`: `FAKE_PARAMETER_SECRET`, `FAKE_CONTEXT_SECRET`.

- `cause.cause.message`, `cause.cause.repr`, `cause.cause.args`, `cause.cause.structured.exception_message`, `cause.cause.traceback`, `cause.context.message`, `cause.context.repr`, `cause.context.args`, `cause.context.structured.exception_message`, `cause.context.traceback`, `context.cause.message`, `context.cause.repr`, `context.cause.args`, `context.cause.structured.exception_message`, `context.cause.traceback`, `context.context.message`, `context.context.repr`, `context.context.args`, `context.context.structured.exception_message`, `context.context.traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

Top-level structured JSON unavailable in this scenario; inspect cause/context evidence for the chained case.

### missing_file

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-missing_file`, `json-missing_file`. Source under test: path. Python action: `execute`.

```sql
SELECT * FROM read_csv('FAKE_PATH_PRIVATE/missing.csv');
```

**Text:** `IOException`; engine category: not a structured field.

```text
IO Error: No files found that match the pattern "FAKE_PATH_PRIVATE/missing.csv"

LINE 1: SELECT * FROM read_csv('FAKE_PATH_PRIVATE/missing.csv')
                      ^
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `IOException`; engine category: IO.

```json
{
  "exception_type": "IO",
  "exception_message": "No files found that match the pattern \"FAKE_PATH_PRIVATE/missing.csv\"",
  "position": "14"
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `14`. Chosen anchor `read_csv` starts at character `14` / UTF-8 byte `14`.

### url_blocked

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-url_blocked`, `json-url_blocked`. Source under test: URL. Python action: `external_disabled`.

```sql
SELECT * FROM read_csv('https://FAKE_HOST_PRIVATE.invalid/file?token=FAKE_URL_TOKEN');
```

Execute `SET enable_external_access=false` first. No URL request occurs.

**Text:** `PermissionException`; engine category: not a structured field.

```text
Permission Error: Cannot access file "https://FAKE_HOST_PRIVATE.invalid/file?token=FAKE_URL_TOKEN" - file system operations are disabled by configuration

LINE 1: SELECT * FROM read_csv('https://FAKE_HOST_PRIVATE.invalid/file?token=FAKE...
                      ^
```

Observed marker repetition: `FAKE_HOST_PRIVATE`, `FAKE_URL_TOKEN`.

- `message`, `repr`, `args`, `traceback`: `FAKE_HOST_PRIVATE`, `FAKE_URL_TOKEN`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `PermissionException`; engine category: Permission.

```json
{
  "exception_type": "Permission",
  "exception_message": "Cannot access file \"https://FAKE_HOST_PRIVATE.invalid/file?token=FAKE_URL_TOKEN\" - file system operations are disabled by configuration",
  "position": "14"
}
```

Observed marker repetition: `FAKE_HOST_PRIVATE`, `FAKE_URL_TOKEN`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_HOST_PRIVATE`, `FAKE_URL_TOKEN`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `14`. Chosen anchor `read_csv` starts at character `14` / UTF-8 byte `14`.

### csv_row

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-csv_row`, `json-csv_row`. Source under test: file row. Python action: `csv`.

```sql
SELECT * FROM read_csv('FAKE_PATH_PRIVATE.csv', columns={'v':'INTEGER'}, header=true);
```

Local fixture `FAKE_PATH_PRIVATE.csv`: `v\nFAKE_ROW_PERSONAL\n`.

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: CSV Error on Line: 2
Original Line: FAKE_ROW_PERSONAL
Error when converting column "v". Could not convert string "FAKE_ROW_PERSONAL" to 'INTEGER'

Column v is being converted as type INTEGER
This type was either manually set or derived from an existing table. Select a different type to correctly parse this column.
* Check whether the null string value is set correctly (e.g., nullstr = 'N/A')

  file = FAKE_PATH_PRIVATE.csv
  delimiter = , (Auto-Detected)
  quote = (empty) (Auto-Detected)
  escape = (empty) (Auto-Detected)
  new_line = \r\n (Auto-Detected)
  header = true (Set By User)
  skip_rows = 0 (Auto-Detected)
  comment = (empty) (Auto-Detected)
  strict_mode = true (Auto-Detected)
  date_format =  (Auto-Detected)
  timestamp_format =  (Auto-Detected)
  null_padding = 0
  sample_size = 20480
  ignore_errors = false
  all_varchar = 0
The Column types set by the user do not match the ones found by the sniffer.
Column at position: 0 Set type: INTEGER Sniffed type: VARCHAR


```

Observed marker repetition: `FAKE_PATH_PRIVATE`, `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`, `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "CSV Error on Line: 2\nOriginal Line: FAKE_ROW_PERSONAL\nError when converting column \"v\". Could not convert string \"FAKE_ROW_PERSONAL\" to 'INTEGER'\n\nColumn v is being converted as type INTEGER\nThis type was either manually set or derived from an existing table. Select a different type to correctly parse this column.\n* Check whether the null string value is set correctly (e.g., nullstr = 'N/A')\n\n  file = FAKE_PATH_PRIVATE.csv\n  delimiter = , (Auto-Detected)\n  quote = (empty) (Auto-Detected)\n  escape = (empty) (Auto-Detected)\n  new_line = \\r\\n (Auto-Detected)\n  header = true (Set By User)\n  skip_rows = 0 (Auto-Detected)\n  comment = (empty) (Auto-Detected)\n  strict_mode = true (Auto-Detected)\n  date_format =  (Auto-Detected)\n  timestamp_format =  (Auto-Detected)\n  null_padding = 0\n  sample_size = 20480\n  ignore_errors = false\n  all_varchar = 0\nThe Column types set by the user do not match the ones found by the sniffer. \nColumn at position: 0 Set type: INTEGER Sniffed type: VARCHAR\n\n"
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`, `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PATH_PRIVATE`, `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### parquet_invalid

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parquet_invalid`, `json-parquet_invalid`. Source under test: path/file. Python action: `parquet`.

```sql
SELECT * FROM read_parquet('FAKE_PATH_PRIVATE.parquet');
```

Local fixture `FAKE_PATH_PRIVATE.parquet`: bytes `FAKE_ROW_BUSINESS`.

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: No magic bytes found at end of file 'FAKE_PATH_PRIVATE.parquet'

LINE 1: SELECT * FROM read_parquet('FAKE_PATH_PRIVATE.parquet')
                      ^
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "No magic bytes found at end of file 'FAKE_PATH_PRIVATE.parquet'",
  "position": "14"
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `14`. Chosen anchor `read_parquet` starts at character `14` / UTF-8 byte `14`.

### json_row

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-json_row`, `json-json_row`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE t(v VARCHAR);
INSERT INTO t VALUES ('FAKE_ROW_PERSONAL');
SELECT CAST(v AS JSON) FROM t;
```

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: Malformed JSON at byte 0 of input: unexpected character.  Input: "FAKE_ROW_PERSONAL" when casting from source column v

LINE 1: SELECT CAST(v AS JSON) FROM t
               ^
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "Malformed JSON at byte 0 of input: unexpected character.  Input: \"FAKE_ROW_PERSONAL\" when casting from source column v",
  "position": "7"
}
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

Reported `position`: `7`. No comparison anchor specified.

### regex_parameter

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-regex_parameter`, `json-regex_parameter`. Source under test: parameter. Python action: `execute`.

```sql
SELECT regexp_matches('x', ?);
```

Bound parameters: `['[FAKE_PARAMETER_SECRET']`.

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: missing ]: [FAKE_PARAMETER_SECRET
```

Observed marker repetition: `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "missing ]: [FAKE_PARAMETER_SECRET"
}
```

Observed marker repetition: `FAKE_PARAMETER_SECRET`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PARAMETER_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### range

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-range`, `json-range`. Source under test: numeric row. Python action: `execute`.

```sql
CREATE TABLE t(v BIGINT);
INSERT INTO t VALUES (9223372036854775807);
SELECT v + 1 FROM t;
```

**Text:** `OutOfRangeException`; engine category: not a structured field.

```text
Out of Range Error: Overflow in addition of INT64 (9223372036854775807 + 1)!
```

Observed marker repetition: `9223372036854775807`.

- `message`, `repr`, `args`, `traceback`: `9223372036854775807`.

Actual table-derived value marker: observed.

**JSON requested:** `OutOfRangeException`; engine category: Out of Range.

```json
{
  "exception_type": "Out of Range",
  "exception_message": "Overflow in addition of INT64 (9223372036854775807 + 1)!"
}
```

Observed marker repetition: `9223372036854775807`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `9223372036854775807`.

Actual table-derived value marker: observed.

No structured position field observed.

### transaction

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-transaction`, `json-transaction`. Source under test: identifier. Python action: `execute`.

```sql
BEGIN TRANSACTION;
BEGIN TRANSACTION;
```

**Text:** `TransactionException`; engine category: not a structured field.

```text
TransactionContext Error: cannot start a transaction within a transaction
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `TransactionException`; engine category: TransactionContext.

```json
{
  "exception_type": "TransactionContext",
  "exception_message": "cannot start a transaction within a transaction"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### dependency

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-dependency`, `json-dependency`. Source under test: identifier. Python action: `execute`.

```sql
CREATE TABLE FAKE_IDENTIFIER_PRIVATE(i INT PRIMARY KEY);
CREATE TABLE child(i INT REFERENCES FAKE_IDENTIFIER_PRIVATE(i));
DROP TABLE FAKE_IDENTIFIER_PRIVATE;
```

**Text:** `CatalogException`; engine category: not a structured field.

```text
Catalog Error: Could not drop the table because this table is main key table of the table "child"
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

**JSON requested:** `CatalogException`; engine category: Catalog.

```json
{
  "exception_type": "Catalog",
  "exception_message": "Could not drop the table because this table is main key table of the table \"child\""
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

No structured position field observed.

### not_implemented

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-not_implemented`, `json-not_implemented`. Source under test: identifier. Python action: `execute`.

```sql
CREATE TABLE t(i INT);
ALTER TABLE t ADD CONSTRAINT FAKE_IDENTIFIER_PRIVATE UNIQUE(i);
```

**Text:** `NotImplementedException`; engine category: not a structured field.

```text
Not implemented Error: No support for that ALTER TABLE option yet!
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

**JSON requested:** `NotImplementedException`; engine category: Not implemented.

```json
{
  "exception_type": "Not implemented",
  "exception_message": "No support for that ALTER TABLE option yet!"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: no exposure observed.

No structured position field observed.

### sequence

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-sequence`, `json-sequence`. Source under test: identifier. Python action: `execute`.

```sql
CREATE SEQUENCE FAKE_IDENTIFIER_PRIVATE MAXVALUE 2 START 2;
SELECT nextval('FAKE_IDENTIFIER_PRIVATE');
SELECT nextval('FAKE_IDENTIFIER_PRIVATE');
```

**Text:** `SequenceException`; engine category: not a structured field.

```text
Sequence Error: nextval: reached maximum value of sequence "FAKE_IDENTIFIER_PRIVATE" (2)
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `SequenceException`; engine category: Sequence.

```json
{
  "exception_type": "Sequence",
  "exception_message": "nextval: reached maximum value of sequence \"FAKE_IDENTIFIER_PRIVATE\" (2)"
}
```

Observed marker repetition: `FAKE_IDENTIFIER_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_IDENTIFIER_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### closed_connection

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-closed_connection`, `json-closed_connection`. Source under test: connection. Python action: `closed`.

```sql
SELECT 'FAKE_LITERAL_SECRET';
```

Close the connection before executing the query.

**Text:** `ConnectionException`; engine category: not a structured field.

```text
Connection Error: Connection already closed!
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ConnectionException`; engine category: not a structured field.

```text
Connection Error: Connection already closed!
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Top-level structured JSON unavailable in this scenario; inspect cause/context evidence for the chained case.

### parameter_missing

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-parameter_missing`, `json-parameter_missing`. Source under test: parameter name. Python action: `execute`.

```sql
SELECT $FAKE_PARAMETER_NAME;
```

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: Values were not provided for the following prepared statement parameters: FAKE_PARAMETER_NAME
```

Observed marker repetition: `FAKE_PARAMETER_NAME`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PARAMETER_NAME`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "Values were not provided for the following prepared statement parameters: FAKE_PARAMETER_NAME"
}
```

Observed marker repetition: `FAKE_PARAMETER_NAME`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PARAMETER_NAME`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### setting

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-setting`, `json-setting`. Source under test: setting value. Python action: `execute`.

```sql
SET threads='FAKE_SETTING_PRIVATE';
```

**Text:** `InvalidInputException`; engine category: not a structured field.

```text
Invalid Input Error: Failed to cast value: Could not convert string 'FAKE_SETTING_PRIVATE' to INT64
```

Observed marker repetition: `FAKE_SETTING_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_SETTING_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `InvalidInputException`; engine category: Invalid Input.

```json
{
  "exception_type": "Invalid Input",
  "exception_message": "Failed to cast value: Could not convert string 'FAKE_SETTING_PRIVATE' to INT64"
}
```

Observed marker repetition: `FAKE_SETTING_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_SETTING_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### extension_missing

Practical classification: **Metadata**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-extension_missing`, `json-extension_missing`. Source under test: extension path. Python action: `execute`.

```sql
LOAD 'FAKE_PATH_PRIVATE.duckdb_extension';
```

**Text:** `IOException`; engine category: not a structured field.

```text
IO Error: Extension "FAKE_PATH_PRIVATE.duckdb_extension" not found.

Candidate extensions: "http", "fts", "https", "httpfs", "motherduck"
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `IOException`; engine category: IO.

```json
{
  "exception_type": "IO",
  "exception_message": "Extension \"FAKE_PATH_PRIVATE.duckdb_extension\" not found.\n\nCandidate extensions: \"http\", \"fts\", \"https\", \"httpfs\", \"motherduck\""
}
```

Observed marker repetition: `FAKE_PATH_PRIVATE`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_PATH_PRIVATE`.

Actual table-derived value marker: not applicable; no table fixture.

No structured position field observed.

### pivot_conversion

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-pivot_conversion`, `json-pivot_conversion`. Source under test: row. Python action: `execute`.

```sql
CREATE TABLE t(category VARCHAR, v VARCHAR);
INSERT INTO t VALUES ('group_a','FAKE_ROW_PERSONAL');
PIVOT t ON category USING sum(CAST(v AS INTEGER));
```

**Text:** `ConversionException`; engine category: not a structured field.

```text
Conversion Error: Could not convert string 'FAKE_ROW_PERSONAL' to INT32 when casting from source column v

LINE 1: SELECT * FROM t PIVOT (sum(CAST(v AS INTEGER)) FOR (category) IN "__pivot_enum_88b018da...
                                      ^
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

**JSON requested:** `ConversionException`; engine category: Conversion.

```json
{
  "exception_type": "Conversion",
  "exception_message": "Could not convert string 'FAKE_ROW_PERSONAL' to INT32 when casting from source column v",
  "position": "30"
}
```

Observed marker repetition: `FAKE_ROW_PERSONAL`.

- `message`, `repr`, `args`, `structured.exception_message`, `traceback`: `FAKE_ROW_PERSONAL`.

Actual table-derived value marker: observed.

Reported `position`: `30`. Chosen anchor `CAST` starts at character `30` / UTF-8 byte `30`.

### pivot_candidate

Practical classification: **Contextual**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-pivot_candidate`, `json-pivot_candidate`. Source under test: row-derived identifier. Python action: `execute`.

```sql
CREATE TABLE t(category VARCHAR, v INT);
INSERT INTO t VALUES ('FAKE_ROW_BUSINESS',1);
SELECT missing FROM (PIVOT t ON category USING sum(v));
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Referenced column "missing" not found in FROM clause!
Candidate bindings: "FAKE_ROW_BUSINESS"

LINE 1: SELECT missing FROM (SELECT * FROM t PIVOT (sum(v) FOR (category...
               ^
```

Observed marker repetition: `FAKE_ROW_BUSINESS`.

- `message`, `repr`, `args`, `traceback`: `FAKE_ROW_BUSINESS`.

Actual table-derived value marker: observed.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Referenced column \"missing\" not found in FROM clause!\nCandidate bindings: \"FAKE_ROW_BUSINESS\"",
  "candidates": "FAKE_ROW_BUSINESS",
  "position": "7",
  "error_subtype": "COLUMN_NOT_FOUND",
  "name": "missing"
}
```

Observed marker repetition: `FAKE_ROW_BUSINESS`.

- `message`, `repr`, `args`, `structured.exception_message`, `structured.candidates`, `traceback`: `FAKE_ROW_BUSINESS`.

Actual table-derived value marker: observed.

Reported `position`: `7`. Chosen anchor `missing` starts at character `7` / UTF-8 byte `7`.

### multiline_binder

Practical classification: **Control**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-multiline_binder`, `json-multiline_binder`. Source under test: literal. Python action: `execute`.

```sql
SELECT
 'FAKE_LITERAL_SECRET',
 absent;
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Referenced column "absent" was not found because the FROM clause is missing

LINE 3:  absent
         ^
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Referenced column \"absent\" was not found because the FROM clause is missing",
  "position": "32",
  "error_subtype": "COLUMN_NOT_FOUND",
  "name": "absent"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `32`. Chosen anchor `absent` starts at character `32` / UTF-8 byte `32`.

### unicode_position

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-unicode_position`, `json-unicode_position`. Source under test: literal. Python action: `execute`.

```sql
SELECT 'éFAKE_LITERAL_SECRET', absent;
```

**Text:** `BinderException`; engine category: not a structured field.

```text
Binder Error: Referenced column "absent" was not found because the FROM clause is missing

LINE 1: SELECT 'éFAKE_LITERAL_SECRET', absent
                                       ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `BinderException`; engine category: Binder.

```json
{
  "exception_type": "Binder",
  "exception_message": "Referenced column \"absent\" was not found because the FROM clause is missing",
  "position": "32",
  "error_subtype": "COLUMN_NOT_FOUND",
  "name": "absent"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `32`. Chosen anchor `absent` starts at character `31` / UTF-8 byte `32`.

### extract_parser

Practical classification: **Ordinary data**. See the scenario-level assessment for relevance and limits.

Test IDs: `text-extract_parser`, `json-extract_parser`. Source under test: literal. Python action: `extract`.

```sql
SELECT 'FAKE_LITERAL_SECRET' + FROM x;
```

Call `connection.extract_statements(sql)` instead of executing.

**Text:** `ParserException`; engine category: not a structured field.

```text
Parser Error: syntax error at or near "FROM"

LINE 1: SELECT 'FAKE_LITERAL_SECRET' + FROM x
                                       ^
```

Observed marker repetition: `FAKE_LITERAL_SECRET`.

- `message`, `repr`, `args`, `traceback`: `FAKE_LITERAL_SECRET`.

Actual table-derived value marker: not applicable; no table fixture.

**JSON requested:** `ParserException`; engine category: Parser.

```json
{
  "exception_type": "Parser",
  "exception_message": "syntax error at or near \"FROM\"",
  "position": "31",
  "error_subtype": "SYNTAX_ERROR"
}
```

No supplied marker exposure observed in captured surfaces for this scenario.

Actual table-derived value marker: not applicable; no table fixture.

Reported `position`: `31`. Chosen anchor `FROM` starts at character `31` / UTF-8 byte `31`.

## Factual conclusions

The completed run contains **42 scenarios / 84 passing probe tests**, covering
**13 distinct DuckDB Python exception classes**, plus one deliberately created
Python RuntimeError wrapper. Every final probe produced an error; no native
crash, timeout, or unclassified final result occurred. **64 of 84 runs** exposed
at least one supplied marker on a captured diagnostic surface. That count
includes identifiers and deliberate custom messages, not only confidential row
values; it is not an estimated exposure rate for workloads.

Actual stored row markers appeared in eight scenarios in both modes:
`conversion_row`, `constraint_row`, `custom_row`, `udf_message`, `json_row`,
`range`, `pivot_conversion`, and `pivot_candidate`. Separately, `csv_row`
exposed a local file's data line. These have different practical meanings:
casts, UNIQUE errors, JSON conversion and CSV import expose inputs incidentally;
`custom_row` explicitly turns the row into a message; `udf_message` hand-writes
an exception including the value; and `range` uses the maximum BIGINT boundary,
which establishes value echoing rather than personal information by itself.
The CHECK constraint scenario omitted its row marker.

The PIVOT candidate result demonstrates a BinderException containing a stored
category without that value appearing in the failing SELECT. This is a genuine
row-to-identifier mechanism, not a caller naming a table after a password.
It does not make every ordinary candidate name confidential.

Parser, binder and catalog diagnostics repeat supplied inputs in both formats,
but some fixtures are only metadata: `parser_token` names an invalid token,
`binder_key_literal` names a missing struct key, and `catalog_path_identifier`
uses a path as a function name without accessing any file. Their PRIVATE/SECRET
labels do not establish actual sensitivity. In contrast, incidental data
literals in `parser_literal`, `binder_literal` and `catalog_literal` appear in
text excerpts and disappear from JSON. Removing an excerpt is distinct from
removing sensitive message content. JSON preserves useful diagnostic fields
in those cases while retaining actual values in conversion and CSV errors.

The full token-bearing URL in `url_blocked` is an access argument, not an
explicit print request. Credential-bearing URLs can be legitimate inputs;
the observed denial echoes the full URL before a network request. This is
contextually relevant, but says nothing about remote authentication behavior.
`custom_connection_string`, conversely, explicitly calls error(?) with a
password-bearing message and does not exercise any connector or authentication.
Ordinary file and extension paths are useful metadata; the tests do not
establish that those paths contain credentials or confidential information.

JSON was recoverable from **40 of 42 JSON-requested top-level exceptions**.
The Python client retained a textual exception prefix before the JSON object;
`json.loads(str(error))` alone would not parse these prefixed messages. The
collector decodes from the first opening brace and retains the original string.
`closed_connection` remained plain text. `python_chain` had a plain RuntimeError
at the top, with the DuckDB JSON diagnostic in its nested cause/context.
JSON `exception_message` still contained values, full URL query tokens, file
paths, CSV lines and UDF stack-location text in the relevant cases. JSON changed
the representation; these observations do not establish a redaction guarantee.

For the ASCII scenarios with a matching anchor, positions matched zero-based
byte/character offsets. `unicode_position` reported **32**, matching the UTF-8
byte offset of `absent`, rather than character offset **31** after `é`.
`parser_multiline` reported end-of-input position **36**, rather than the chosen
`FROM` anchor at **32**, consistent with its end-of-input message. Text showed
line/caret context for many, but not all, errors. `multiline_binder` pointed to
`absent` on line 3 and omitted the marker on line 2. PIVOT conversion position
**30** matched the `CAST` expression in the tested SQL; the outer PIVOT candidate
failure pointed at `missing` (offset **7**). These observations do not establish
position semantics for every rewrite, Unicode character, client or statement
batch. Errors such as CSV conversion, constraints and custom messages had no
structured SQL position in these runs. A CSV's reported file line is different
from a SQL-source position.

Exception `repr` and `args` preserved message-bearing content. Formatted
tracebacks included exception messages and source locations. The deliberately
chained case preserved the parameter marker through nested cause/context
objects even though the top-level string contained only a wrapper marker.
The UDF failure contained a Python error description and function locations
inside DuckDB's own diagnostic. No conclusions about real backend SDK chains
or Quackframe's current exception conversion follow from these direct probes.

## Responsibility and diagnostic usefulness

Ordinary SQL processing can turn input values into diagnostics without an
explicit logging request. That belongs within evaluation of a runtime's error
handling. Missing names, candidate names, filenames, types and positions are
also valuable diagnostic information; suppressing them has a real usability
cost. These tests do not justify treating every name or path as confidential.

Callers control object names and explicit `error(...)` messages. Deliberately
embedding credentials there is different from a library exposing a credential
used legitimately for access. The contrived probes document this boundary;
they do not create an obligation to infer and remove every possible secret
from arbitrary caller-authored prose. UDF forwarding remains contextual because
a developer might author the message or merely propagate a dependency's error.
The current fixture establishes forwarding only.

This investigation does not choose output settings, sanitization rules, fallback
behavior or implementation. It also does not claim any error class universally
safe. Both absolute safety claims and universal-redaction conclusions exceed
the evidence.

## Evidence interpretation

The 84 passing tests assert that errors occurred, diagnostics are nonempty and
the expected DuckDB version ran. They do not assert expected sensitivity
classifications or prove safe error handling. The retained observations provide
the substantive evidence; a green run alone is not a privacy regression result.

The direct probes do not exercise Quackframe or Prefect delivery. No real SDK
authentication error was reproduced. Python traceback source text and repeated
cause/context paths are not independent engine leaks. The manually authored
UDF and chain cases establish propagation, not a defect in current wrappers.

## Untested, unavailable and unreproduced cases

- The `dependency` attempt produced **CatalogException**, not DependencyException.
  Its output describes the referencing table `child` and omits the supplied
  parent-table marker. A distinct DependencyException was not reproduced.
- No probes produced Python FatalException, HTTPException, InternalException,
  InterruptException, InvalidTypeException, OutOfMemoryException,
  SerializationException, SyntaxException or TypeMismatchException.
  These classes remain untested rather than safe or impossible to expose.
- Engine enum entries not observed as distinct categories include INVALID,
  UNKNOWN_TYPE, DECIMAL, MISMATCH_TYPE, DIVIDE_BY_ZERO, OBJECT_SIZE, INVALID_TYPE,
  SERIALIZATION, EXPRESSION, PLANNER, SCHEDULER, EXECUTOR, INDEX, STAT, SYNTAX,
  SETTINGS, NETWORK, OPTIMIZER, NULL_POINTER, INTERRUPT, FATAL, INTERNAL,
  OUT_OF_MEMORY, PARAMETER_NOT_RESOLVED, PARAMETER_NOT_ALLOWED, DEPENDENCY,
  HTTP, MISSING_EXTENSION, AUTOLOAD and INVALID_CONFIGURATION. In particular,
  the invalid setting yielded Invalid Input, and missing local extension
  yielded IO. Their scenario names are not claims about engine classification.
- Resource exhaustion, damaged database/WAL files, assertion failures and
  native crashes were not induced. Serial tiny fixtures cannot establish
  transaction-conflict, cancellation, concurrency or native stack behavior.
- Remote storage, SQL connectors, live HTTP responses, authentication errors,
  cloud credentials, Prefect services, backend SDK failures and installed
  third-party extension diagnostics were not executed. The blocked synthetic
  URL is evidence about a Permission diagnostic, not network-error behavior.
- Only Python 3.13.9 on Windows and the locked DuckDB build were executed.
  CLI, JDBC, other Python versions, other operating systems, debug builds,
  multi-statement offsets, SQL truncation limits, long values, non-BMP Unicode,
  tracebacks with captured locals and logging-framework serialization remain
  untested. Existing Quackframe sanitization was not exercised by this harness.
- JSON was unavailable at the top level in the closed-connection and Python
  wrapper cases described above. No final result was classified as unknown.
- During harness development, a sandbox prevented access to a fresh temporary
  directory. An initial sequence definition also failed in setup because its
  minimum equaled its maximum. The fixture and cleanup were corrected; these
  preliminary infrastructure/setup failures are not counted as probe results.
  No hanging or crashing probe was retried.

## Reproduction and validation

Use the repository's Poetry environment with its locked DuckDB version. This
run reused the existing environment read-only via process-local `VIRTUAL_ENV`;
no packages were installed and no original-checkout files were edited. On a
normally configured checkout, the environment override is unnecessary.
Run from the repository root in PowerShell:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DUCKDB_INVESTIGATION_OUTPUT = "$PWD/tests/investigations/duckdb_errors/observations.json"
poetry run pytest tests/investigations/duckdb_errors/test_diagnostics.py -q --maxfail=1 -p no:cacheprovider
poetry run ruff check tests/investigations/duckdb_errors
poetry run ruff format --check tests/investigations/duckdb_errors
poetry run pyright tests/investigations/duckdb_errors
poetry run python .agents/skills/quackframe-documentation/scripts/check_doc_links.py
git diff --check
```

Setting `DUCKDB_INVESTIGATION_OUTPUT` intentionally replaces the synthetic
observations file. Without it, the suite does not update the retained evidence.
Do not replace the retained completed evidence with a partial run without
recording that limitation. To reproduce one scenario without collecting all:

```powershell
poetry run python tests/investigations/duckdb_errors/probe.py conversion_row json
```

The test runner supplies the timeout; the standalone command does not.

Actual validation: dedicated suite **84 passed**;
changed-file Ruff check and format check passed; changed-file Pyright reported
**0 errors and 0 warnings** using an explicit existing-environment interpreter
(`--pythonpath E:/projects/quackframe/.venv/Scripts/python.exe`). Sandboxed
Pyright initially could not resolve installed packages; the same scoped check
passed with the interpreter accessible. No full repository suite, holistic
review, benchmarks or release workflow ran. Documentation/link and whitespace
checks passed: all local Markdown targets/anchors exist, and changed-file
whitespace checks are clean.

The practical classifications were checked against the retained probe inputs
and observations without rerunning tests. Documentation link and whitespace
checks passed after integrating the assessment.

## Related Docs

- [Documentation index](README.md): architecture and investigation entry points.
- [Execution lifecycle](execution-lifecycle.md): current Quackframe behavior,
  which this investigation does not change.
- [Python extensions](python-extensions.md): SQL-callable extension boundaries.
