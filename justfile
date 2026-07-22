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
#   python-    the Python implementation (future: java-, rust-, ...)
#
# Database-backed recipes (verify, oracle-test, python-verify) start
# Testcontainers containers and need a reachable Docker daemon. README.md
# "Running And Inspecting The Project" has the one-time
# ~/.testcontainers.properties fix for runtimes other than Docker Desktop.

# Path to the reference harness module.
harness := "reference-harness"

# Default: list available recipes.
default:
    @just --list

# ===========================================================================
# Repo-wide: the top-level gates and reports that span every module.
# ===========================================================================

# Full merge gate: repo lint + core gates + Python lanes + the harness suite (Docker).
# `python-verify` subsumes `python-static`, so only the aggregate is listed here.
verify: lint oracle-typecheck core-dep-graph python-verify oracle-test

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

# Docker-free tests and canonical-input smoke check for the language-contract
# diagnostics, plus the closed-vocabulary drift guards: the m-case-format.md <->
# compatibility-case.schema.json rejectedRule vocabulary, and the m-core.md <->
# m-descriptor.md <-> metamodel.schema.json neutral-type vocabulary.
core-contract-tools:
    cd {{harness}} && uv run pytest tests/test_slice_inspect.py tests/test_language_spec_validate.py tests/test_case_format_vocab_check.py tests/test_neutral_type_vocab_check.py
    cd {{harness}} && uv run python -m reference_harness.slice_inspect --check-all ../core/spec ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.case_format_vocab_check ../core/spec
    cd {{harness}} && uv run python -m reference_harness.neutral_type_vocab_check ../core/spec

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
# Language: Python. The uv workspace lives under languages/python/packages/*;
# these fan out into it via uv. Recipe names (`python-static`, `python-verify`)
# are pinned by languages/python/spec/python.md §10.
# ===========================================================================

python := "languages/python"

# Every database-free §10 row: ruff (lint + format check), Pyright strict, the
# generated import-linter forbidden-edge complement (DAG-sync check) +
# lint-imports, unit tests + branch coverage + diff-cover, the built-artifact /
# clean-install / api-surface proofs, dead-code scan, and the supply-chain
# audit. The Docker-free compile-sweep row joins here in COR-3 Phase 5.
#
# `check_untracked_sources.py` runs before the coverage rows on purpose:
# diff-cover derives its line inventory from git, so an untracked production
# module scores zero changed lines and `--fail-under 100` passes vacuously over
# whatever was tracked. The guard makes that state a hard failure.
#
# `check_scope_ownership.py` sits beside it and before `lint-imports`, because
# lint-imports can only judge the files a declared scope covers: a production
# module outside every §7 scope passes it by never being examined.
python-static:
    cd {{python}} && uv run ruff format --check .
    cd {{python}} && uv run ruff check .
    cd {{python}} && uv run pyright
    cd {{python}} && uv run python tools/check_dag_sync.py
    cd {{python}} && uv run python tools/check_untracked_sources.py
    cd {{python}} && uv run python tools/check_scope_ownership.py
    cd {{python}} && uv run lint-imports
    cd {{python}} && uv run pytest -m unit --cov --cov-branch --cov-report=xml --cov-report=term-missing --cov-fail-under=90
    cd {{python}} && uv run diff-cover coverage.xml --compare-branch origin/main --fail-under 100
    cd {{python}} && uv run pytest -m dialect
    cd {{python}} && uv run pytest -m compile_sweep
    cd {{python}} && uv run pytest -m "artifact or clean_install or api_surface"
    cd {{python}} && uv run vulture
    cd {{python}} && uv build --all-packages -o dist
    cd {{python}} && uv run twine check dist/*
    cd {{python}} && uv lock --check
    cd {{python}} && uv run pip-audit

# Static plus every database-backed §10 row (Docker): the pg-full run sweep,
# provider contract, adapter smoke, and API conformance. Those lanes come
# online in COR-3 Phase 5+ (with the skip-reporting summary block that forbids
# silent database-backed skips); until then the markers collect nothing and
# pytest's no-tests exit code (5) is tolerated.
python-verify: python-static
    cd {{python}} && uv run pytest -m "conformance or provider_contract or adapter_smoke or api_conformance" || [ "$?" -eq 5 ]
