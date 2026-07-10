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

# Full merge gate: repo lint + core gates + primary TS lanes + the harness suite (Docker).
verify: lint oracle-typecheck core-dep-graph ts-typecheck ts-typecheck-tests ts-lint ts-package-check ts-conformance-compile ts-db oracle-test

# Every static check that needs no database: harness ruff, markdown, core schema/SQL,
# and the language-contract diagnostic tools.
lint: oracle-lint lint-md core-schemas core-contract-tools

# Markdown lint across core/spec, languages/**/spec, and root.
lint-md:
    pnpm exec markdownlint-cli2

# Compatibility-matrix report (implementations x databases; Postgres + MariaDB).
matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility

# ===========================================================================
# Core spec: validation of the core specification and compatibility corpus.
#   dep-graph: DAG legality; the coverage gate (every active/cases module from
#   the modules.md catalog has a tagged fixture) + the active->deferred rule; the
#   profile gate (every slice's tagged cases match its canonical describe claim
#   in slices.md). schemas: meta-schema + fixture validation + sqlglot parse
#   of all golden/reference SQL.
# ===========================================================================

# Core module DAG + coverage gate + the per-slice profile gate.
core-dep-graph:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --coverage ../core/spec ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --profile ../core/spec ../core/compatibility

# Validate the schemas (meta-schema), every fixture, and all golden/reference SQL.
core-schemas:
    cd {{harness}} && uv run python -m reference_harness.schema_validate ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.sql_lint ../core/compatibility

# Inspect one canonical slice using the claims, module DAG, and compatibility corpus.
core-slice-inspect slice:
    cd {{harness}} && uv run python -m reference_harness.slice_inspect ../core/spec ../core/compatibility {{slice}}

# Validate a completed, root-relative language-spec path against the canonical template.
core-language-spec-check language_spec:
    cd {{harness}} && uv run python -m reference_harness.language_spec_validate ../{{language_spec}} ../core/spec

# Docker-free tests and canonical-input smoke check for the language-contract diagnostics.
core-contract-tools:
    cd {{harness}} && uv run pytest tests/test_slice_inspect.py tests/test_language_spec_validate.py
    cd {{harness}} && uv run python -m reference_harness.slice_inspect --check-all ../core/spec ../core/compatibility

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

# Typecheck test files too (tsc --noEmit per package after the build; catches test/** errors).
ts-typecheck-tests:
    pnpm run ts:typecheck-tests

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

# --- TypeScript database testing --------------------------------------------

# Docker-free DB contracts: dialect table, provider selection parsing, matrix profile declarations.
ts-db-fast:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/dialect/test/dialect-conformance.test.ts packages/typescript/test/api-conformance/provider-selection.test.ts packages/typescript/test/conformance-profiles.test.ts

# Docker-free conformance lane: full-slice compile sweep + honesty gate + matrix report.
ts-conformance-compile:
    pnpm run ts:typecheck
    pnpm exec vitest run --root languages/typescript packages/conformance

# Primary Docker-backed DB gate: shared adapter/provider contracts, the Postgres compatibility matrix, and Postgres API conformance.
ts-db: ts-db-fast
    pnpm exec vitest run --root languages/typescript packages/typescript/test/db-adapter-smoke.test.ts
    PARALLAX_DATABASES=postgres,mariadb pnpm exec vitest run --root languages/typescript packages/typescript/test/db-provider-contract.test.ts
    pnpm exec vitest run --root languages/typescript packages/typescript/test/slice-run.test.ts
    node languages/typescript/scripts/render-guide.mjs --check
    pnpm exec vitest run --root languages/typescript packages/typescript/test/api-conformance

# Exhaustive Docker-backed DB sweep: primary gate plus MariaDB API and curated matrix profile.
ts-db-all: ts-db
    PARALLAX_DATABASES=mariadb pnpm exec vitest run --root languages/typescript packages/typescript/test/api-conformance
    pnpm exec vitest run --root languages/typescript packages/typescript/test/mariadb-run.test.ts
