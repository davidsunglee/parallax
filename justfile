# parallax root orchestration.
#
# `just` is the language-agnostic orchestrator that ties the polyglot modules
# together. Each module (core/, reference-harness/, languages/<lang>/) uses its
# own native toolchain; this file only fans out into them.
#
# The scopes this file fans out into:
#   (bare)     repository-wide gates, reports, and graph introspection
#   core-      validation of the core spec + compatibility corpus
#   harness-   the reference harness's own code health and test suite
#   python-    the Python implementation (future: java-, rust-, ...)
#
# Every public recipe reads `<scope>-<operation>[-<qualifier>]`, drawing its
# operation from the closed vocabulary in `core/spec/language-testing.md` — the
# normative contract for the grammar, the roles, the scheduling partition, and
# the order the sections below are declared in. `just check-gates` fails when
# this file stops matching it.
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
# containers and needs a reachable Docker daemon. README.md "Running And
# Inspecting The Project" has the one-time ~/.testcontainers.properties fix for
# runtimes other than Docker Desktop.

# ===========================================================================
# Configuration: module paths and the recipe listing.
# ===========================================================================

# Path to the reference harness module.
harness := "reference-harness"

# Path to the Python implementation module.
python := "languages/python"

# The minimum Pydantic release `parallax-core` declares. The floor and the locked
# release are the two ends of the supported range, and the parity corpus is graded
# on both.
pydantic_floor := "2.13.0"

# The bare `just` entry point. Private because it is the listing itself rather
# than a verification command, and the grammar governs the public interface.
[private]
default:
    @just --list

# ===========================================================================
# Repository-wide: the aggregates every scope composes into, plus the gates
# that belong to no single scope.
# ===========================================================================

# The success summary is a terminal dependency rather than a command body: an
# aggregate carrying a body cannot be composed without re-running it, and a
# `report` passes no judgement about what this file validated, so it adds output
# and no second verdict. It could still fail this aggregate by failing to print
# its line at all, which the contract permits of a non-blocking command and which
# says nothing about any gate above it.
[doc("Merge gate: every blocking check a merge waits on.")]
check: check-gates check-dbfree check-db report-check-summary

[doc("Complete gate: the merge gate plus the cost class CI also runs.")]
check-all: check check-cost report-check-all-summary

[doc("Every blocking check that needs no live database.")]
check-dbfree: core-check lint-markdown harness-check-dbfree python-check-dbfree

[doc("Every blocking check that needs a live database (Docker).")]
check-db: harness-check-db python-check-db

[doc("Every blocking check needing an interpreter no other test shares.")]
check-cost: python-check-cost

[metadata("runtime:fast")]
[doc("This file matches the grammar, roles, and composition core/spec/language-testing.md fixes.")]
check-gates:
    cd {{harness}} && uv run python -m reference_harness.check_gates ..

[metadata("runtime:fast")]
[doc("Markdown lint across core/spec, languages/**/spec, and root.")]
lint-markdown:
    pnpm exec markdownlint-cli2

# ===========================================================================
# Introspection and reports: non-blocking output that describes the repository
# rather than judging it. A gate may depend on one for its output without
# acquiring a second verdict.
# ===========================================================================

[metadata("runtime:fast")]
[doc("Resolved gate graph: roles, execution owners, prerequisites, and runtime classes.")]
show-gates *recipes:
    cd {{harness}} && uv run python -m reference_harness.show_gates .. {{recipes}}

[metadata("runtime:slow")]
[doc("Compatibility-matrix report (implementations x databases; Postgres + MariaDB).")]
report-matrix:
    cd {{harness}} && uv run python -m reference_harness.matrix ../core/compatibility

[metadata("runtime:fast")]
[doc("The line `just check` ends with when every gate it runs passed.")]
report-check-summary:
    @echo 'check OK: every merge-gating check in this repository passed. The cost class is not one of them: `just check-all` adds it, and CI runs it on every change.'

[metadata("runtime:fast")]
[doc("The line `just check-all` ends with when every gate passed.")]
report-check-all-summary:
    @echo "check-all OK: every blocking check in this repository passed."

# ===========================================================================
# Core spec: validation of the core specification and compatibility corpus.
# ===========================================================================

[doc("Every blocking check over the core spec and compatibility corpus.")]
core-check: core-check-module-graph core-check-slice-profiles core-check-schemas core-check-contract-tools core-check-twin-layouts core-check-batch-size-twins core-check-language-spec

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
    cd {{harness}} && uv run python -m reference_harness.object_query_vocab_check ../core/spec
    cd {{harness}} && uv run python -m reference_harness.descriptor_contract_check ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.retired_vocab_check ..
    cd {{harness}} && uv run python -m reference_harness.case_comment_check ../core/compatibility
    cd {{harness}} && uv run python -m reference_harness.canonical_spelling_check ../core/compatibility

[metadata("runtime:fast")]
[doc("Cross-layout descriptor and case twins have equal logical models and observations.")]
core-check-twin-layouts:
    cd {{harness}} && uv run python -m reference_harness.twin_layout_check ../core/compatibility

[metadata("runtime:fast")]
[doc("Streamed batch-size case twins state one read at every page size.")]
core-check-batch-size-twins:
    cd {{harness}} && uv run python -m reference_harness.batch_size_twin_check ../core/compatibility

[metadata("runtime:fast")]
[doc("Every completed language spec still fills in the canonical template.")]
core-check-language-spec:
    cd {{harness}} && uv run python -m reference_harness.language_spec_validate ..

[metadata("runtime:fast")]
[doc("Inspect one canonical slice using the claims, module DAG, and compatibility corpus.")]
core-show-slice slice:
    cd {{harness}} && uv run python -m reference_harness.slice_inspect ../core/spec ../core/compatibility {{slice}}

[metadata("runtime:fast")]
[doc("Validate one root-relative language-spec path, drafted or complete, against the template.")]
core-show-language-spec language_spec:
    cd {{harness}} && uv run python -m reference_harness.language_spec_validate ../{{language_spec}} ../core/spec

# ===========================================================================
# Harness: the reference harness's own code health and its test suite, which
# runs the compatibility corpus as the executable oracle.
# ===========================================================================

[doc("Every harness check that needs no live database.")]
harness-check-dbfree: harness-check-database-access harness-format-check harness-lint harness-typecheck harness-test-dbfree

[doc("Every harness check that needs a live database (Docker).")]
harness-check-db: harness-test-db

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

# A focused selector for iterating on the accepted Object Query read oracle, and
# deliberately no gate's dependency for the opposite reason to the one above: every
# test it selects is `dbfree`, so an aggregate composing it would run them a second
# time inside `harness-test-dbfree`.
[metadata("runtime:fast")]
[doc("Focused: the accepted Object Query read oracle's own tests.")]
harness-test-oracle:
    cd {{harness}} && uv run pytest tests/oracle

# A focused selector for iterating on Unit Work Scenario grading, no gate's
# dependency for the same reason as the one above: every test it selects is
# `dbfree`.
[metadata("runtime:fast")]
[doc("Focused: the Unit Work Scenario package's own tests.")]
harness-test-unit-work-scenario:
    cd {{harness}} && uv run pytest tests/unit_work_scenario

# A scheduling class is only as honest as the restriction on the resource that
# defines it: an item acquiring a provider outside the designated fixture would
# be classified `dbfree` and would still pass on a host with Docker.
[metadata("runtime:fast")]
[doc("Live database access in the harness suite goes through the designated fixture.")]
harness-check-database-access:
    cd {{harness}} && uv run python -m reference_harness.check_database_access

[metadata("runtime:fast")]
[doc("Harness formatting is deterministic and already applied.")]
harness-format-check:
    cd {{harness}} && uv run ruff format --check .

[metadata("runtime:fast")]
[doc("Ruff lint rules over the harness.")]
harness-lint:
    cd {{harness}} && uv run ruff check .

[metadata("runtime:fast")]
[doc("Typecheck the harness with basedpyright.")]
harness-typecheck:
    cd {{harness}} && uv run basedpyright

[metadata("runtime:fast")]
[doc("Format the harness in place (rewrites tracked sources).")]
harness-format:
    cd {{harness}} && uv run ruff format .

# ===========================================================================
# Language: Python. The uv workspace lives under languages/python/packages/*;
# these fan out into it via uv. Recipe names are pinned by
# languages/python/spec/python.md §10.
# ===========================================================================

[doc("Every blocking check over the Python implementation.")]
python-check: python-check-dbfree python-check-db python-check-cost

[doc("Every Python check that needs no live database.")]
python-check-dbfree: python-format-check python-lint python-typecheck python-check-imports python-check-database-access python-check-dead-code python-test-dbfree python-coverage-diff python-check-distribution-metadata python-check-lock python-audit

[doc("Every Python check that needs a live database (Docker).")]
python-check-db: python-test-db

[doc("Every Python check needing an interpreter no other test shares.")]
python-check-cost: python-check-instrument-access python-test-cost

[metadata("runtime:slow", "scheduling:dbfree")]
[doc("Every Python test whose fixture closure reaches no database, plus branch coverage.")]
python-test-dbfree:
    cd {{python}} && uv run pytest -m dbfree --cov --cov-branch --cov-report=xml --cov-report=term-missing --cov-fail-under=95

[metadata("runtime:slow", "scheduling:db")]
[doc("Every Python test whose fixture closure reaches a database (Testcontainers; Docker).")]
python-test-db:
    cd {{python}} && uv run pytest -m db

# No coverage here. Every reading is taken in a child interpreter the parent does
# not trace, so what this selects contributes nothing to a coverage report; the
# production lines these measurements drive are covered by the suites grading
# their behavior, which `python-test-dbfree` owns.
[metadata("runtime:slow", "scheduling:cost")]
[doc("Every Python test reading the whole interpreter, each in one of its own.")]
python-test-cost:
    cd {{python}} && uv run pytest -m cost -n 2

# The six semantic surfaces are focused selectors for iteration, and deliberately
# no gate's dependencies: each cuts across the scheduling partition, so an
# aggregate composing one would run part of it a second time.
[metadata("runtime:slow")]
[doc("Focused: internal seams, diagnostics, and failure modes.")]
python-test-unit:
    cd {{python}} && uv run pytest tests/unit

[metadata("runtime:slow")]
[doc("Focused: the compatibility corpus — compile sweep, rejection sweep, run sweep (Docker).")]
python-test-compatibility:
    cd {{python}} && uv run pytest tests/compatibility

[metadata("runtime:slow")]
[doc("Focused: the API Conformance Suite, the Usage Guide, and the public-API snapshot (Docker).")]
python-test-api:
    cd {{python}} && uv run pytest tests/api

[metadata("runtime:fast")]
[doc("Focused: the pure m-dialect strategy — SQL spelling, quoting, error categories.")]
python-test-dialect:
    cd {{python}} && uv run pytest tests/dialect

[metadata("runtime:medium")]
[doc("Focused: the provider/matrix contract and the psycopg adapter smokes (Docker).")]
python-test-provider-contract:
    cd {{python}} && uv run pytest tests/provider_contract

[metadata("runtime:medium")]
[doc("Focused: built-wheel content and the clean-venv install topologies.")]
python-test-distribution:
    cd {{python}} && uv run pytest tests/distribution

# A focused selector like the six above it, differing in what it RESOLVES rather
# than in what it selects. The lock pins one Pydantic release; what a published
# object's serialization has to hold on is the whole supported range, and its
# floor is the end where a behaviour this seam is built over could differ.
# `--with` overlays that release onto the workspace resolution for one run and
# leaves the lock alone, so `python-test-dbfree` grades the corpus on the lock and
# this grades the same corpus on the floor. No aggregate composes it: the floor is
# a verdict about the declared range rather than about a change, so CI owns it in
# a job of its own, the same division that gives the prior interpreter minor its
# own leg of the `python-check-dbfree` job.
[metadata("runtime:medium")]
[doc("Focused: the Pydantic parity corpus on the declared floor rather than the locked release.")]
python-test-pydantic-floor:
    cd {{python}} && uv run --with 'pydantic=={{pydantic_floor}}' pytest tests/unit/test_pydantic_parity.py

# Like the focused selectors above it this belongs to no aggregate, and for a
# different reason: a `report` passes no judgement, so no number it prints can
# fail a merge. That is deliberate — nothing in this repository is enforced
# against elapsed time, and every CI job runs the floating `ubuntu-latest` label.
# What has been read off it, and under what conditions, is
# `languages/python/docs/execution-lifecycle-baseline.md`.
[metadata("runtime:medium")]
[doc("Execution lifecycle dispatch and overhead against the same workload unobserved.")]
python-report-lifecycle-overhead:
    cd {{python}} && uv run python tools/lifecycle_overhead.py

# Its neighbour above belongs to no aggregate because a wall clock cannot judge;
# this one because a total in bytes is machine- and interpreter-relative, so the
# ratio it prints against the recorded pre-cutover reading is evidence rather
# than a verdict. The SHAPE of what a graph retains is gated instead, in
# `tests/unit/test_snapshot_graph_retention.py`, which `python-test-dbfree` owns.
# What has been read off this, and under what conditions, is
# `languages/python/docs/snapshot-graph-baseline.md`.
[metadata("runtime:medium")]
[doc("Retained Snapshot graph overhead per projection, and what building one costs.")]
python-report-snapshot-graph-overhead:
    cd {{python}} && uv run python tools/snapshot_graph_overhead.py

# The same reason again, over the streamed read's working set: what a running
# delivery holds is a total in bytes, so this prints it as evidence and judges
# nothing. The SHAPE of the bound — a survivor census with no term in the result
# size and none in how far the delivery has got, and both exclusions demonstrated
# — is gated in `tests/unit/test_snapshot_stream_retention.py`, which the `cost`
# class owns and CI runs on every change. What has been read off this, and under
# what conditions, is `languages/python/docs/stream-baseline.md`.
[metadata("runtime:medium")]
[doc("Working set of a running streamed delivery per page size, against what retaining a root costs.")]
python-report-stream-overhead:
    cd {{python}} && uv run python tools/stream_overhead.py

# A `report` for the same reason as its neighbour above: a total in bytes is
# machine- and interpreter-relative, so what it prints is evidence rather than a
# verdict, and it belongs to no aggregate. It measures three arms — the fixture
# that reproduced publication before the flip, the shipping publication path, and
# ordinary validating construction — over every supported CPython minor, running
# a child of its own for each, so it costs more than its neighbours and still
# gates nothing: the two comparisons the measurement contract names are DISPLAYED
# as an escalation block and reach no exit code, and the only thing it exits
# non-zero on is a matrix cell it has no reading for. The aggregates divide the
# first two arms; the third states what a published node costs against one a
# caller built, and enters neither. What grades those comparisons is
# `tests/unit/test_instance_state_baseline.py`, which `python-test-dbfree` owns
# and which feeds them doctored readings. What has been read off this, and under
# what conditions, is `languages/python/docs/instance-state-baseline.md`.
[metadata("runtime:medium")]
[doc("Retained published Entity state under each backing over the canonical mix, on every supported minor.")]
python-report-instance-state:
    cd {{python}} && uv run python tools/instance_state_overhead.py

# Both prerequisites are soundness conditions, not merely file dependencies.
# diff-cover derives its line inventory from git, so an untracked production
# module scores zero changed lines and `--fail-under 100` passes vacuously over
# whatever was tracked.
[metadata("runtime:slow")]
[doc("Every changed line is covered by database-free proof.")]
python-coverage-diff: python-test-dbfree python-check-untracked-sources
    cd {{python}} && uv run diff-cover coverage.xml --compare-branch origin/main --fail-under 100

[metadata("runtime:fast")]
[doc("Python formatting is deterministic and already applied.")]
python-format-check:
    cd {{python}} && uv run ruff format --check .

[metadata("runtime:fast")]
[doc("Ruff lint rules over the Python workspace.")]
python-lint:
    cd {{python}} && uv run ruff check .

[metadata("runtime:fast")]
[doc("Typecheck the Python workspace with Pyright in strict mode.")]
python-typecheck:
    cd {{python}} && uv run pyright

# `check_scope_ownership.py` is a prerequisite rather than a neighbour, because
# lint-imports can only judge the files a declared scope covers: a production
# module outside every §7 scope passes it by never being examined. `check_dag_sync.py`
# generates the contracts lint-imports reads.
[metadata("runtime:fast")]
[doc("Every production import stays inside the generated dependency closure.")]
python-check-imports: python-check-dag-sync python-check-scope-ownership
    cd {{python}} && uv run lint-imports

[metadata("runtime:fast")]
[doc("The generated import-linter contracts agree with modules.md and spec/python.md §7.")]
python-check-dag-sync:
    cd {{python}} && uv run python tools/check_dag_sync.py

[metadata("runtime:fast")]
[doc("Every production file resolves to exactly one most-specific §7 scope.")]
python-check-scope-ownership:
    cd {{python}} && uv run python tools/check_scope_ownership.py

[metadata("runtime:fast")]
[doc("No production or test source exists on disk but outside git.")]
python-check-untracked-sources:
    cd {{python}} && uv run python tools/check_untracked_sources.py

# A scheduling class is only as honest as the restriction on the resource that
# defines it: an item acquiring a database outside the designated fixture would
# be classified `dbfree` and would still pass on a host with Docker.
[metadata("runtime:fast")]
[doc("Live database access in the Python suite goes through the designated fixture.")]
python-check-database-access:
    cd {{python}} && uv run python tools/check_database_access.py

# The same soundness condition one class over: an item reading the whole
# interpreter without acquiring one of its own would be classified `dbfree`, and
# would still pass — against a heap the rest of the suite decided the size of.
[metadata("runtime:fast")]
[doc("Whole-interpreter readings in the Python suite go through the designated boundary.")]
python-check-instrument-access:
    cd {{python}} && uv run python tools/check_instrument_access.py

[metadata("runtime:fast")]
[doc("Dead-code scan over the Python workspace.")]
python-check-dead-code:
    cd {{python}} && uv run vulture

[metadata("runtime:fast")]
[doc("Build every workspace distribution into languages/python/dist.")]
python-build:
    cd {{python}} && uv build --all-packages -o dist

[metadata("runtime:fast")]
[doc("Built distributions carry renderable, well-formed packaging metadata.")]
python-check-distribution-metadata: python-build
    cd {{python}} && uv run twine check dist/*

[metadata("runtime:fast")]
[doc("The committed lockfile agrees with the declared dependencies.")]
python-check-lock:
    cd {{python}} && uv lock --check

[metadata("runtime:fast")]
[doc("Audit the locked dependency set for known vulnerabilities.")]
python-audit:
    cd {{python}} && uv run pip-audit

[metadata("runtime:fast")]
[doc("Format the Python workspace in place (rewrites tracked sources).")]
python-format:
    cd {{python}} && uv run ruff format .
