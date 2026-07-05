# parallax root orchestration.
#
# `just` is the language-agnostic orchestrator that ties the polyglot modules
# together. Each module (core/, reference-harness/, languages/<lang>/) uses its
# own native toolchain; this file only fans out into them.
#
# Recipes are grouped by scope. Repo-wide gates and reports stay bare; every
# other recipe carries a scope prefix so its category is obvious and future
# languages slot in cleanly:
#   (bare)     repo-wide gates and reports: verify, lint, lint-md, matrix
#   core-      validation of the core spec + compatibility corpus
#   oracle-    the Python reference harness (its own checks + running the oracle)
#   ts-        the TypeScript implementation (future: java-, rust-, py-, ...)

# Path to the reference harness module.
harness := "reference-harness"

# Default: list available recipes.
default:
    @just --list

# ===========================================================================
# Repo-wide: the top-level gates and reports that span every module.
# ===========================================================================

# Full merge gate: repo lint + core gates + all TS lanes + the harness suite (Docker).
verify: lint oracle-typecheck core-dep-graph ts-typecheck ts-lint ts-package-check ts-conformance-compile ts-conformance-run ts-api-conformance oracle-test

# Every static check that needs no database: harness ruff, markdown, core schema/SQL.
lint: oracle-lint lint-md core-schemas

# Markdown lint across core/spec, languages/**/spec, and root.
lint-md:
    pnpm exec markdownlint-cli2

# Compatibility-matrix report (implementations x databases; Postgres + MariaDB).
matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility

# ===========================================================================
# Core spec: validation of the core specification and compatibility corpus.
#   dep-graph: DAG legality; the coverage gate (every in-scope module from
#   scope-and-tiers.md has a tagged fixture); the slice-mvp-1 profile gate (the
#   tagged slice matches its canonical describe claim). schemas: meta-schema +
#   fixture validation + sqlglot parse of all golden/reference SQL.
# ===========================================================================

# Core module DAG + coverage gate + the slice-mvp-1 profile gate.
core-dep-graph:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --coverage ../core/spec ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --profile ../core/spec ../core/compatibility

# Validate the schemas (meta-schema), every fixture, and all golden/reference SQL.
core-schemas:
    cd {{harness}} && uv run python -m reference_harness.schema_validate ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.sql_lint ../core/compatibility

# ===========================================================================
# Oracle: the Python reference harness — its own code health, and running it as
# the executable oracle over the compatibility corpus.
# ===========================================================================

# Static lint of the harness: ruff format check + ruff lint.
oracle-lint:
    cd {{harness}} && uv run ruff format --check .
    cd {{harness}} && uv run ruff check .

# Auto-format the harness (mutates in place).
oracle-format:
    cd {{harness}} && uv run ruff format .

# Typecheck the harness with basedpyright.
oracle-typecheck:
    cd {{harness}} && uv run basedpyright

# The compatibility suite + the harness's own unit tests (pytest, Testcontainers; Docker).
oracle-test:
    cd {{harness}} && uv run pytest

# ===========================================================================
# Language: TypeScript. The pnpm workspace lives under
# languages/typescript/packages/*; these fan out into it. Future languages get
# their own <lang>- section (java-, rust-, py-, ...).
# ===========================================================================

# Static TS lint: Biome (format + lint) and the dependency-cruiser DAG gate.
ts-lint:
    pnpm run ts:lint

# TypeScript typecheck across project references (tsc -b, no emit drift).
ts-typecheck:
    pnpm run ts:typecheck

# TypeScript unit / adapter tests (vitest) across the workspace.
ts-test:
    pnpm run ts:test

# TypeScript V8 line coverage + the same markdown summary CI prints.
ts-coverage:
    pnpm run ts:typecheck
    pnpm run ts:coverage
    node languages/typescript/scripts/coverage-summary.mjs coverage/typescript/coverage-summary.json

# Conformance-slice coverage report (JSON + markdown under coverage/).
ts-conformance-coverage:
    pnpm run ts:conformance-coverage

# Package-export health across the @parallax/* ESM workspace: publint + attw + knip (Docker-free).
ts-package-check:
    pnpm run ts:package-check

# Docker-free conformance lane: full-slice compile sweep + honesty gate + matrix report.
ts-conformance-compile:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/conformance

# Docker-backed conformance run lane: the full slice-mvp-1 slice end-to-end over postgres:17.
ts-conformance-run:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/typescript

# Docker-backed MariaDB run lane: the 25-case set (14 in-slice + 11 marquee) end-to-end over mariadb:11.4.
ts-conformance-run-mariadb:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/typescript/test/mariadb-run.test.ts

# Docker-backed API Conformance Suite + Usage Guide drift check over postgres:17.
ts-api-conformance:
    pnpm run ts:typecheck
    node languages/typescript/scripts/render-guide.mjs --check
    pnpm exec vitest run --root languages/typescript packages/typescript/test/api-conformance

# Docker-backed API Conformance Suite over mariadb:11.4 (reads and developer writes
# run through the MariaDB dialect/adapter seam selected by PARALLAX_DATABASES).
ts-api-conformance-mariadb:
    pnpm run ts:typecheck
    PARALLAX_DATABASES=mariadb pnpm exec vitest run --root languages/typescript packages/typescript/test/api-conformance
