# parallax root orchestration.
#
# `just` is the language-agnostic orchestrator that ties the polyglot modules
# together. Each module (core/, reference-harness/, future python/, java/, ...)
# uses its own native toolchain; this file only fans out into them.

# Path to the reference harness module.
harness := "reference-harness"

# Default: list available recipes.
default:
    @just --list

# ---------------------------------------------------------------------------
# lint: every static check that does not require a database.
#   - ruff (Python lint of the harness)
#   - markdownlint (spec prose)
#   - JSON Schema meta-schema validation (the schemas are themselves valid)
#   - schema validation of every fixture
#   - sqlglot-parse of all golden/reference SQL
# ---------------------------------------------------------------------------
lint: lint-py lint-md lint-schemas

lint-py:
    cd {{harness}} && uv run ruff check .

lint-md:
    pnpm exec markdownlint-cli2

# Validate the schemas against the JSON Schema meta-schema, validate every
# fixture against its schema, and parse all golden/reference SQL with sqlglot.
lint-schemas:
    cd {{harness}} && uv run python -m reference_harness.schema_validate ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.sql_lint ../core/compatibility

# Mechanically check the normative module-dependency graph is a DAG with legal
# edge directions, AND run the Phase 12 coverage gate: every in-scope module
# (MVP / fast-follow / definitely-do, read from scope-and-tiers.md) has at least
# one compatibility fixture tagged to it.
dep-graph:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --coverage ../core/spec ../core/compatibility

# ---------------------------------------------------------------------------
# test: the full compatibility suite. Boots real databases via Testcontainers,
# so Docker must be running.
# ---------------------------------------------------------------------------
test:
    cd {{harness}} && uv run pytest

# verify: everything that must be green before merging (no Docker-less escape).
verify: lint dep-graph test

# matrix: emit the compatibility-matrix report (implementations x databases).
# Wires Postgres + MariaDB (Phase 10 added MariaDB as the second dialect).
matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility
