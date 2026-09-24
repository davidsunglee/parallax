# reference-harness

The canonical **compatibility runner** for parallax (the `m-case-format` harness) — Python + uv + sqlglot.

It is **tooling, not an ORM**. It **never compiles queries to SQL** (that is
precisely what a real implementation must do and prove against the golden SQL).
It only proves the compatibility suite is internally consistent and that the
golden SQL is correct for the fixture data, across every database behind the
**database-provider seam**.

The reference harness's internals are non-normative and
MUST NOT be used as design input for a language implementation; the binding
inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the
conformance-adapter contract.

## Layout

The [source directory](src/reference_harness/) contains corpus validation,
independent read/write oracles, and database providers. The harness interprets
authored expectations; it is not a production query compiler.

Verification graph tooling is separate: [gate_graph.py](src/reference_harness/gate_graph.py)
resolves commands, [show_gates.py](src/reference_harness/show_gates.py) displays
them, and [check_gates.py](src/reference_harness/check_gates.py) validates them
against the [testing contract](../core/spec/language-testing.md).

Tests for contract diagnostics live in `tests/contract_tools/`, read oracles in
`tests/oracle/`, and scenarios in `tests/unit_work_scenario/`. The corpus runner
is `tests/test_compatibility.py`; `tests/conftest.py` owns provider fixtures and
derives database scheduling from fixture use.

## Running

From the repo root via `just` (preferred), or directly here with `uv run`:

```sh
uv run python -m reference_harness.schema_validate ../core/compatibility
uv run python -m reference_harness.sql_lint ../core/compatibility
uv run python -m reference_harness.dep_graph_check ../core/spec/modules.md
uv run python -m reference_harness.slice_inspect ../core/spec ../core/compatibility slice-snapshot-1
uv run python -m reference_harness.language_spec_validate ..
uv run python -m reference_harness.language_spec_validate ../languages/<target>/spec/<target>.md ../core/spec
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run python -m reference_harness.check_database_access
uv run pytest -m dbfree   # no database provider is reached
uv run pytest -m db       # boots every selected provider via Testcontainers (Docker required)
uv run python -m reference_harness.matrix ../core/compatibility
uv run python -m reference_harness.show_gates ..
uv run python -m reference_harness.check_gates ..
```

The two `language_spec_validate` lines differ in what they select. The first
discovers each target's binding entrypoint and is the form the gate runs. The
second validates one entrypoint; supporting binding pages are not separate
claims. The checks cover the canonical claim and required topology declarations,
not a checklist of explanatory prose.
