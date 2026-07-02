# reference-harness

The canonical **M12 compatibility runner** for parallax — Python + uv + sqlglot.

It is **tooling, not an ORM**. It **never compiles operations to SQL** (that is
precisely what a real implementation must do and prove against the golden SQL).
It only proves the compatibility suite is internally consistent and that the
golden SQL is correct for the fixture data, across every database behind the
**database-provider seam**.

## Layout

```text
src/reference_harness/
├── case.py            # the in-memory Case + Model dataclasses + loader
├── schema_validate.py # validate descriptors / operations / cases vs JSON Schema (+ meta-schema)
├── sql_lint.py        # sqlglot-parse every golden / reference SQL string
├── serde.py           # canonical (de)serialize for operations AND the metamodel (JSON + YAML)
├── sql_normalize.py   # sqlglot implementation of the M3 normalization rules
├── ddl_builder.py     # descriptor -> CREATE TABLE DDL (dialect-aware via the provider)
├── data_loader.py     # load fixture rows
├── dep_graph_check.py # parse dependency-graph.md; assert DAG + legal direction
├── matrix.py          # emit the compatibility-matrix report (implementations x databases)
├── case_runner.py     # the layered assertion engine
└── providers/
    ├── __init__.py    # the DatabaseProvider protocol (the seam)
    └── postgres.py    # Testcontainers Postgres provider (dialect = "postgres")
tests/
└── test_compatibility.py  # pytest: discover cases, run each through run_case per provider
```

## Running

From the repo root via `just` (preferred), or directly here with `uv run`:

```sh
uv run python -m reference_harness.schema_validate ../core/compatibility
uv run python -m reference_harness.sql_lint ../core/compatibility
uv run python -m reference_harness.dep_graph_check ../core/spec/dependency-graph.md
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest          # boots Postgres via Testcontainers (Docker required)
uv run python -m reference_harness.matrix ../core/compatibility
```
