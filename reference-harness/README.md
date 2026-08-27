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

```text
src/reference_harness/
├── case.py            # the in-memory Case + Model dataclasses + loader
├── schema_validate.py # validate descriptors / queries / cases vs JSON Schema (+ meta-schema)
├── sql_lint.py        # sqlglot-parse every golden / reference SQL string
├── serde.py           # canonical (de)serialize for queries AND the metamodel (JSON + YAML)
├── sql_normalize.py   # sqlglot implementation of the m-sql normalization rules
├── sql_wrapped_union.py # the oracle for the derived table an ordered/limited union wraps as
├── sql_canonical.py   # the sqlglot dialect map + the refusal every canonicality check raises
├── ddl_builder.py     # descriptor -> CREATE TABLE DDL (dialect-aware via the provider)
├── data_loader.py     # load fixture rows
├── dep_graph_check.py # parse modules.md; assert DAG + legal direction
├── matrix.py          # emit the compatibility-matrix report (implementations x databases)
├── case_runner.py     # the layered assertion engine
├── gate_graph.py      # resolve the orchestrator's command graph: roles, classes, closures
├── show_gates.py      # render the resolved command graph
├── check_gates.py     # fail when that graph breaks core/spec/language-testing.md
├── ci_workflow.py     # read a CI workflow as job identifiers and the commands they run
├── runner_config.py   # read a scope's test-runner configuration through a declared profile
├── diagnostics.py     # the shared code/message diagnostic and its failure report
├── markdown_read.py   # read code spans and list items out of Markdown prose
├── check_database_access.py  # live database access stays inside the designated fixture
└── providers/
    ├── __init__.py    # the DatabaseProvider protocol (the seam)
    └── postgres.py    # Testcontainers Postgres provider (dialect = "postgres")
tests/
├── conftest.py            # shared fixtures; derives each item's dbfree/db scheduling class
├── contract_tools/        # the language-contract diagnostics' own tests
└── test_compatibility.py  # pytest: discover cases, run each through run_case per provider
```

## Running

From the repo root via `just` (preferred), or directly here with `uv run`:

```sh
uv run python -m reference_harness.schema_validate ../core/compatibility
uv run python -m reference_harness.sql_lint ../core/compatibility
uv run python -m reference_harness.dep_graph_check ../core/spec/modules.md
uv run python -m reference_harness.slice_inspect ../core/spec ../core/compatibility slice-snapshot-1
uv run python -m reference_harness.language_spec_validate ..
uv run python -m reference_harness.language_spec_validate ../languages/<target>/spec/implementation.md ../core/spec
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run python -m reference_harness.check_database_access
uv run pytest -m dbfree   # no database provider is reached
uv run pytest -m db       # boots Postgres via Testcontainers (Docker required)
uv run python -m reference_harness.matrix ../core/compatibility
uv run python -m reference_harness.show_gates ..
uv run python -m reference_harness.check_gates ..
```

The two `language_spec_validate` lines differ in what they select. The first
discovers and validates every completed language spec in the repository and is
the form the gate runs. The second takes one path and is for a spec still being
drafted; replace `<target>` with the target it belongs to.
