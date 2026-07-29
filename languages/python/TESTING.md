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
`tests/unit/_metamodel_support.py`, `_snapshot_wrap_support.py`,
`_sql_gen_support.py`, `_transact_support.py`, and
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

`provisioner` is the only route to a live database. When Docker or the provider
cannot be brought up it records the reason and skips, and the terminal summary
prints every recorded reason; `PARALLAX_REQUIRE_DB=1` turns any such skip into a
failure. Docker setup — including the one-time `~/.testcontainers.properties` fix
for runtimes other than Docker Desktop — is in the root `README.md`.

## Commands

Run from the repository root through `just`, or from `languages/python` through
`uv`.

| Purpose | Command |
|---|---|
| Every database-free gate | `just python-static` |
| That plus the database-backed lanes (Docker) | `just python-verify` |
| Iterate on one surface | `cd languages/python && uv run pytest tests/<surface>` |
| Iterate on one module | `cd languages/python && uv run pytest tests/<surface>/test_<name>.py` |

## Continuous integration

| Workflow and job | Matrix | Runs |
|---|---|---|
| `ci` / `python-static` | CPython 3.12 / 3.13 / 3.14 | `just python-static`, checked out at `fetch-depth: 0` because diff-cover compares against `origin/main` |
| `ci` / `python-database` | — | The database-backed pytest selection against Testcontainers Postgres |
| `python-deps-refresh` / `refresh` (monthly) | — | `uv lock --upgrade`, opening a pull request the two jobs above still gate |
