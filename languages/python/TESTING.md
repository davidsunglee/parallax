# Parallax Python — testing map

Where Python tests live, what each surface proves, which fixtures reach a live
database, and which command owns which selection.

The structural rules and the reasoning behind them belong to
`core/spec/language-testing.md`. Quality policy — thresholds, matrices,
exclusions, and required proof — belongs to `spec/python.md` §10. Milestones,
status, and blockers belong to `GUIDE.md`. None of them is restated here.

## Test root

`tests/` is closed. Every entry is a semantic surface directory, `_support/`, or
a file pytest requires at the root.

| Surface | Directory | Proves |
|---|---|---|
| Internal behavior | `tests/unit/` | Internal seams, diagnostics, and failure modes, plus the `tools/` gate scripts' own canaries |
| Portable specification behavior | `tests/compatibility/` | The compatibility corpus: the Docker-free compile sweep, the authored-rejection sweep, and the real-database run sweep |
| Idiomatic public API | `tests/api/` | The API Conformance Suite — idiomatic public-API code against real Postgres, its coverage partition, its no-drift guards, and the Usage Guide — plus the griffe public-API snapshot |
| Core `m-dialect` contract | `tests/dialect/` | The pure dialect strategy: SQL spelling, quoting, and the SQLSTATE-to-category mapping |
| Provider integration contract | `tests/provider_contract/` | The provider/matrix contract and the real psycopg adapter smoke checks |
| Shipped and installed output | `tests/distribution/` | Built-wheel content and public-export health, and the clean-venv production install topologies |

`tests/conftest.py` is the only root file: it holds the fixtures below, the
database-skip ledger, and the terminal-summary hook. Everything else it used to
hold is in `_support/`.

## `_support/`

Cross-surface helpers, models, and probes. It is not a semantic surface and has
no test command of its own.

| Module | Holds |
|---|---|
| `_support/repo.py` | `PY_ROOT`, `REPO_ROOT`, and the canonical core artifacts read from them — `adapter_schema()`, `canonical_snapshot_claim()` |
| `_support/corpus.py` | A case's document and fixtures, and the grading comparators the run sweep and the API-suite story lane share |
| `_support/sweep_goldens.py` | The corpus cases the compile and run sweeps grade against authored goldens, and the golden readers both use |
| `_support/distributions.py` | The distribution name tuples and the `Wheelhouse` the `wheelhouse` fixture builds |
| `_support/fake_metamodel.py` | An alternate accepted-Metamodel implementation and the parity model it pins |
| `_support/frontend_probes.py`, `_support/frontend_probes_stringized.py` | Declaration probes on the live-annotation and stringized-annotation paths |
| `_support/inheritance_models.py`, `_support/mirrored_models.py`, `_support/snapshot_models.py`, `_support/value_object_models.py` | Idiomatic Entity and Value Object classes mirroring the corpus models |

`pythonpath = ["tools", "tests"]` (`pyproject.toml`) puts `tests/` on the import
path, so a symbol reads `from _support.corpus import case_document` and a model
module reads `from _support import mirrored_models as mm`, regardless of which
surface pytest collects first; `pyrightconfig.json`'s `extraPaths` mirrors it. A
test module imports from `_support`, never from another test module.

Support code only one surface uses stays inside that surface —
`tests/unit/_corpus_identity_support.py`, `_document_layout_support.py`,
`_metamodel_support.py`, `_snapshot_graph_support.py`, `_sql_gen_support.py`,
`_transact_support.py`, `tests/unit/observation_models.py`, and
`tests/unit/value_object_bad_models.py`.

`_support/` is the only package under `tests/`. Every surface directory is
rootless, so pytest imports its modules by bare basename and those basenames must
stay globally unique across the test tree.

## Fixtures

Both are session-scoped and defined in `tests/conftest.py`.

| Fixture | Live database? | Yields |
|---|---|---|
| `provisioner` | **yes** | A self-managed Testcontainers Postgres and an open adapter connection |
| `wheelhouse` | no | A directory of freshly built wheels plus a package-name-to-wheel map |

`provisioner` is the only route to a live database, and
`tools/check_database_access.py` is what keeps it so: it fails when any module
under `tests/` calls a seam that starts a container or opens a connection
anywhere but inside that fixture. When Docker or the provider cannot be brought
up the fixture records the reason and skips, and the terminal summary prints
every recorded reason; `PARALLAX_REQUIRE_DB=1` turns any such skip into a
failure. Docker setup — including the one-time `~/.testcontainers.properties` fix
for runtimes other than Docker Desktop — is in the root `README.md`.

## Scheduling labels

Two classes, and every collected item carries exactly one.

| Class | Marker | Means | Owning command |
|---|---|---|---|
| Database-free | `dbfree` | The item's fixture closure reaches no live database | `just python-test-dbfree` |
| Database-backed | `db` | It does, so a Docker daemon is required | `just python-test-db` |

Neither marker is ever written beside a test. `tests/conftest.py`'s collection
hook adds one to every item, chosen by whether the item's resolved fixture
closure contains `provisioner` — so the label covers indirect requests, is
decided per item rather than per file, and can be neither missing nor doubled.
Deleting `provisioner` from a test's signature reclassifies that test.

Scheduling class is orthogonal to the semantic surface. `compatibility/` and
`api/` hold both classes; `unit/`, `dialect/`, and `distribution/` are entirely
`dbfree`; `provider_contract/` is entirely `db`. A surface is therefore never a
substitute for a class, in either direction.

Two further markers exist and classify nothing — `compile_sweep` and
`adapter_smoke` are focused selectors for iteration, authored where they apply.
They are the whole catalog beside `dbfree` and `db`.

## Expected failures

`xfail` is for one shape only: a defect reproduced ahead of its fix. The test
asserts the **correct** behavior and carries `@pytest.mark.xfail(reason=...)`
naming the defect, so the tree stays green while the reproduction stands on its
own as the specification of what the fix must produce. Any other use — a flaky
test, an unfinished feature, an environment gap — belongs to `skip` or to not
being committed.

`xfail_strict = true` (`pyproject.toml`) makes every expected failure strict, so
a reproduction that starts passing reports `XPASS(strict)` and fails the run.
Removing the marker is therefore part of the fix, in the same change, not a
follow-up. Read the `-ra` summary to see each expected failure and its reason.

## Commands

Run from the repository root through `just`, or from `languages/python` through
`uv`.

| Purpose | Command |
|---|---|
| Every database-free gate | `just python-check-dbfree` |
| Every database-backed gate (Docker) | `just python-check-db` |
| Both | `just python-check` |
| Iterate on one surface | `just python-test-<surface>` |
| Iterate on one module | `cd languages/python && uv run pytest tests/<surface>/test_<name>.py` |

The six `python-test-<surface>` recipes are for iteration and are deliberately no
aggregate's dependency: a surface cuts across both scheduling classes, so a gate
composing one would run part of it twice.

## Continuous integration

| Workflow and job | Matrix | Runs |
|---|---|---|
| `ci` / `python-check-dbfree` | CPython 3.12 / 3.13 / 3.14 | `just python-check-dbfree`, checked out at `fetch-depth: 0` because `python-coverage-diff` compares against `origin/main` |
| `ci` / `python-check-db` | — | `just python-check-db` against Testcontainers Postgres, with `PARALLAX_REQUIRE_DB=1` so a provider skip fails the job |
| `python-deps-refresh` / `refresh` (monthly) | — | `uv lock --upgrade`, opening a pull request the two jobs above still gate |
