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
# one compatibility fixture tagged to it. Then run the first-implementation-mvp
# profile gate: the cases tagged into that Conformance Slice are consistent with
# its canonical describe claim in scope-and-tiers.md (no stray module, every
# claimed module covered, every shape in claim, all Postgres goldens).
dep-graph:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --coverage ../core/spec ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --profile ../core/spec ../core/compatibility

# ---------------------------------------------------------------------------
# TypeScript workspace recipes. The pnpm workspace lives under
# languages/typescript/packages/*; these fan out into it the same way the
# Python recipes fan out into the reference harness. None of them need Docker
# (the Testcontainers-backed conformance run lane lands with Phase 3).
# ---------------------------------------------------------------------------

# Static TS lint: Biome (format + lint) and the dependency-cruiser DAG gate.
ts-lint:
    pnpm run ts:lint

# TypeScript typecheck across project references (tsc -b, no emit drift).
ts-typecheck:
    pnpm run ts:typecheck

# TypeScript unit / adapter tests (vitest) across the workspace.
ts-test:
    pnpm run ts:test

# Package-export health across the 13-package ESM workspace: publint (each
# package's `exports` / type entry points are consumable), attw (cross-resolver
# type resolution), and knip (unused files / exports / dependencies). Docker-free.
ts-package-check:
    pnpm run ts:package-check

# The Docker-free conformance lane: the full-slice compile sweep + the honesty
# gate (in-claim never `unsupported`; out-of-claim ⇒ `unsupported` with the right
# diagnostic) + the case-matrix report. This is what agents iterate against in
# seconds; it needs the built CLI dist, so it typechecks first.
ts-conformance-compile:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/conformance

# The Docker-backed conformance run lane: provision `postgres:17` via
# Testcontainers and run the full `first-implementation-mvp` slice end-to-end
# (rows / graph / tableState / affectedRows + roundTrips), asserting the
# case-matrix report is green. Docker must be running.
ts-conformance-run:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/typescript

# The Docker-backed developer-showcase lane (Phase 10c): run the idiomatic `px.*` /
# `px.transaction` showcase over the shipped `@parallax/db-postgres` adapter against
# `postgres:17`, mirroring the whole `first-implementation-mvp` slice (reads / deep
# fetch / temporal / transactions / locking) — asserting managed shapes AND the
# corpus results, plus the no-drift + no-silent-gap coverage guards. Also renders
# the developer guide from the (tested) snippets and checks it is up to date. A
# merge-gating lane alongside the conformance run lane. Docker must be running.
ts-showcase:
    pnpm run ts:typecheck
    node languages/typescript/scripts/render-guide.mjs --check
    pnpm exec vitest run --root languages/typescript packages/typescript/test/showcase

# ---------------------------------------------------------------------------
# test: the full compatibility suite. Boots real databases via Testcontainers,
# so Docker must be running.
# ---------------------------------------------------------------------------
test:
    cd {{harness}} && uv run pytest

# verify: everything that must be green before merging (no Docker-less escape).
# Folds in the TypeScript lanes: the static checks (typecheck / biome / dep-graph
# / package-export health), both conformance lanes (Docker-free compile sweep +
# Docker-backed run lane), and the Docker-backed developer-showcase lane (Phase 10c).
verify: lint dep-graph ts-typecheck ts-lint ts-package-check ts-conformance-compile ts-conformance-run ts-showcase test

# matrix: emit the compatibility-matrix report (implementations x databases).
# Wires Postgres + MariaDB (Phase 10 added MariaDB as the second dialect).
matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility
