# parallax root orchestration.
#
# `just` is the language-agnostic orchestrator that ties the polyglot modules
# together. Each module (core/, reference-harness/, languages/<lang>/) uses its
# own native toolchain; this file only fans out into them.
#
# The sections below follow the same order every time: configuration,
# repository-wide gates, introspection and reports, then one section per scope —
# `core-`, `harness-`, and the language scopes alphabetically.
#   (bare)     repository-wide gates, reports, and graph introspection
#   core-      validation of the core spec + compatibility corpus
#   harness-   the reference harness's own code health and test suite
#   python-    the Python implementation (future: java-, rust-, ...)
#
# Every public recipe reads `<scope>-<operation>[-<qualifier>]`, drawing its
# operation from the closed vocabulary in `core/spec/language-testing.md` — the
# normative contract for the grammar, the roles, and the scheduling partition.
# Three stand outside it: `default`, which is the listing entry point rather
# than a verification command, and the Python scope's `python-static` /
# `python-verify`, which each bundle several operations under one name.
#
# A scope names the subject under validation, not the module implementing it:
# the `core-*` tools live in the harness, and `harness-*` is the harness's own
# health.
#
# Runtime and scheduling classes are declared as `[metadata("runtime:<class>")]`
# and `[metadata("scheduling:<class>")]`, which `just show-gates` reads.
# `[group(...)]` is not a class carrier: `just` organizes `--list` by group, so
# classifying that way would segregate this listing and repeat every recipe once
# per class.
#
# A recipe declaring `[metadata("scheduling:db")]` starts Testcontainers
# containers and needs a reachable Docker daemon, as does `python-verify`, which
# declares no scheduling class. README.md "Running And Inspecting The Project"
# has the one-time ~/.testcontainers.properties fix for runtimes other than
# Docker Desktop.

# ===========================================================================
# Configuration: module paths and the recipe listing.
# ===========================================================================

# Path to the reference harness module.
harness := "reference-harness"

# Path to the Python implementation module.
python := "languages/python"

# Default: list available recipes.
default:
    @just --list

# ===========================================================================
# Repository-wide: the aggregates every scope composes into, plus the gates
# that belong to no single scope.
# ===========================================================================

[doc("Complete merge gate: every blocking check in the repository.")]
check: check-dbfree check-db

[doc("Every blocking check that needs no live database.")]
check-dbfree: core-check lint-markdown harness-check-dbfree python-static

[doc("Every blocking check that needs a live database (Docker).")]
check-db: harness-check-db python-verify

[metadata("runtime:fast")]
[doc("Markdown lint across core/spec, languages/**/spec, and root.")]
lint-markdown:
    pnpm exec markdownlint-cli2

# ===========================================================================
# Introspection and reports: non-blocking output that describes the repository
# rather than judging it, and is therefore reachable from no gate.
# ===========================================================================

[metadata("runtime:fast")]
[doc("Resolved gate graph: roles, execution owners, prerequisites, and runtime classes.")]
show-gates *recipes:
    cd {{harness}} && uv run python -m reference_harness.show_gates .. {{recipes}}

[metadata("runtime:slow")]
[doc("Compatibility-matrix report (implementations x databases; Postgres + MariaDB).")]
report-matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility

# ===========================================================================
# Core spec: validation of the core specification and compatibility corpus.
# ===========================================================================

[doc("Every blocking check over the core spec and compatibility corpus.")]
core-check: core-check-module-graph core-check-slice-profiles core-check-schemas core-check-contract-tools

[metadata("runtime:fast")]
[doc("modules.md DAG legality, per-module fixture coverage, and the active-to-deferred rule.")]
core-check-module-graph:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --coverage ../core/spec ../core/compatibility

[metadata("runtime:fast")]
[doc("Every slice's tagged cases agree with its canonical describe claim in slices.md.")]
core-check-slice-profiles:
    cd {{harness}} && uv run python -m reference_harness.dep_graph_check --profile ../core/spec ../core/compatibility

[metadata("runtime:fast")]
[doc("The meta-schema, every fixture, and a sqlglot parse of all golden/reference SQL.")]
core-check-schemas:
    cd {{harness}} && uv run python -m reference_harness.schema_validate ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.sql_lint ../core/compatibility

# Each diagnostic's own tests live in the harness suite, so `harness-test-dbfree`
# owns them and this recipe stays one operation over one subject: running the
# diagnostics against the canonical inputs they govern.
[metadata("runtime:fast")]
[doc("Every language-contract diagnostic against the real core spec and corpus.")]
core-check-contract-tools:
    cd {{harness}} && uv run python -m reference_harness.slice_inspect --check-all ../core/spec ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.case_format_vocab_check ../core/spec
    cd {{harness}} && uv run python -m reference_harness.neutral_type_vocab_check ../core/spec
    cd {{harness}} && uv run python -m reference_harness.descriptor_contract_check ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.retired_vocab_check ..
    cd {{harness}} && uv run python -m reference_harness.case_comment_check ../core/compatibility

[metadata("runtime:fast")]
[doc("Inspect one canonical slice using the claims, module DAG, and compatibility corpus.")]
core-show-slice slice:
    cd {{harness}} && uv run python -m reference_harness.slice_inspect ../core/spec ../core/compatibility {{slice}}

[metadata("runtime:fast")]
[doc("Validate one completed, root-relative language-spec path against the canonical template.")]
core-show-language-spec language_spec:
    cd {{harness}} && uv run python -m reference_harness.language_spec_validate ../{{language_spec}} ../core/spec

# ===========================================================================
# Harness: the reference harness's own code health and its test suite, which
# runs the compatibility corpus as the executable oracle.
# ===========================================================================

[doc("Every harness check that needs no live database.")]
harness-check-dbfree: harness-format-check harness-lint harness-typecheck harness-test-dbfree

[doc("Every harness check that needs a live database (Docker).")]
harness-check-db: harness-test-db

[metadata("runtime:fast")]
[doc("Harness formatting is deterministic and already applied.")]
harness-format-check:
    cd {{harness}} && uv run ruff format --check .

[metadata("runtime:fast")]
[doc("Ruff lint rules over the harness.")]
harness-lint:
    cd {{harness}} && uv run ruff check .

[metadata("runtime:fast")]
[doc("Format the harness in place (rewrites tracked sources).")]
harness-format:
    cd {{harness}} && uv run ruff format .

[metadata("runtime:fast")]
[doc("Typecheck the harness with basedpyright.")]
harness-typecheck:
    cd {{harness}} && uv run basedpyright

[metadata("runtime:medium", "scheduling:dbfree")]
[doc("Every harness test whose fixture closure reaches no database provider.")]
harness-test-dbfree:
    cd {{harness}} && uv run pytest -m dbfree

[metadata("runtime:slow", "scheduling:db")]
[doc("The compatibility corpus against every selected provider (Testcontainers; Docker).")]
harness-test-db:
    cd {{harness}} && uv run pytest -m db

# A focused selector for iterating on the language-contract diagnostics, and
# deliberately no gate's dependency: it cuts across the scheduling partition, so
# an aggregate composing it would run these tests a second time.
[metadata("runtime:medium")]
[doc("Focused: the language-contract diagnostics' own tests.")]
harness-test-contract-tools:
    cd {{harness}} && uv run pytest tests/contract_tools

# ===========================================================================
# Language: Python. The uv workspace lives under languages/python/packages/*;
# these fan out into it via uv. Recipe names (`python-static`, `python-verify`)
# are pinned by languages/python/spec/python.md §10.
# ===========================================================================

# `check_untracked_sources.py` runs before the coverage rows on purpose:
# diff-cover derives its line inventory from git, so an untracked production
# module scores zero changed lines and `--fail-under 100` passes vacuously over
# whatever was tracked. The guard makes that state a hard failure.
#
# `check_scope_ownership.py` sits beside it and before `lint-imports`, because
# lint-imports can only judge the files a declared scope covers: a production
# module outside every §7 scope passes it by never being examined.
[doc("Every database-free Python quality row.")]
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

# The trailing `|| [ "$?" -eq 5 ]` tolerates pytest's no-tests exit code, which
# the selection returns whenever none of the four markers it names is present.
[doc("Every database-free Python quality row plus the database-backed ones (Docker).")]
python-verify: python-static
    cd {{python}} && uv run pytest -m "conformance or provider_contract or adapter_smoke or api_conformance" || [ "$?" -eq 5 ]
