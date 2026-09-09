# Parallax Python — testing map

Where Python tests live, what each surface proves, which fixtures reach a live
database, and which command owns which selection.

The structural rules and the reasoning behind them belong to
`core/spec/language-testing.md`. Quality policy — thresholds, matrices,
exclusions, and required proof — belongs to `spec/python.md` §10. Neither is
restated here.

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
| `_support/cost_durations.py` | What each cost item last cost: the contract `cost_durations.json` is read under, and the store a measuring run writes back through |
| `_support/corpus.py` | A case's document and fixtures, and the grading comparators the run sweep and the API-suite story lane share |
| `_support/db_port.py` | The shared `m-db-port` doubles, each an ADAPTER owning the runtime, acquisition contexts and revocable connections beneath it — `ScriptedAdapter` and its script entries, `RefusingAdapter`, `ConnectsAsItself` for a double that is its own runtime, `DetachableSource` for the pool measurements a scripted runtime publishes and detaches at its close, the `PortCall` recording — and the transaction outcome a fake with no boundary of its own reports |
| `_support/sweep_goldens.py` | The corpus cases the compile and run sweeps grade against authored goldens, and the golden readers both use |
| `_support/distributions.py` | The distribution name tuples and the `Wheelhouse` the `wheelhouse` fixture builds |
| `_support/fake_metamodel.py` | An alternate accepted-Metamodel implementation and the parity model it pins |
| `_support/adoption.py` | `raises_contextualized`, the assertion every suite makes about an ordinary failure escaping an adopted execution — `db.transact`, a standalone `db.find` / `db.wire.find` / `db.read_rows`, or the delivery of an entered standalone stream: an `ExecutionFailure` whose `cause` is the error the block graded, answered as `value` so the assertion reads as it would against a bare raise |
| `_support/model_capabilities.py` | The three model-bound collaborators — cataloged model, row codec, graph construction — built directly over a Domain Model, exactly as `prepare_model` builds them, for a suite grading one of them alone |
| `_support/frontend_probes.py`, `_support/frontend_probes_stringized.py` | Declaration probes on the live-annotation and stringized-annotation paths |
| `_support/inheritance_models.py`, `_support/mirrored_models.py`, `_support/snapshot_models.py`, `_support/value_object_models.py` | Idiomatic Entity and Value Object classes mirroring the corpus models |

`pythonpath = ["tools", "tests"]` (`pyproject.toml`) puts `tests/` on the import
path, so a symbol reads `from _support.corpus import case_document` and a model
module reads `from _support import mirrored_models as mm`, regardless of which
surface pytest collects first; `pyrightconfig.json`'s `extraPaths` carries the
same two roots. A test module imports from `_support`, never from another test
module.

Support code only one surface uses stays inside that surface —
`tests/unit/_authored_storage_support.py`,
`tests/unit/_corpus_identity_support.py`, `_corpus_model_support.py`,
`_document_layout_support.py`, `_keyed_write_drivers.py`,
`_layout_twin_columns.py`,
`_layout_twin_document.py`, `_lifecycle_cost_support.py`,
`_metamodel_support.py`, `_mixed_strategy_model.py`,
`_second_dialect.py`, `_snapshot_graph_support.py`,
`_source_inventory_support.py`, `_stream_page_support.py`,
`_transact_support.py`,
`tests/unit/memory_instruments.py`,
`tests/unit/observation_models.py`, and
`tests/unit/value_object_bad_models.py`.

Two of those serve the cost suites and split by subject:
`memory_instruments.py` is what all three measure WITH, and
`_lifecycle_cost_support.py` is what the two lifecycle suites drive their seam
with. `tools/snapshot_graph_overhead.py` reads the instruments as well, and is
the one place in the tree that spells `tests/unit` as an import root — it
prepends that directory to `sys.path` and then refuses any `memory_instruments`
that did not resolve to the file it named, which is also why
`pyrightconfig.json`'s `extraPaths` carries `tests/unit` beside the two
`pythonpath` roots.

`_support/` is the only package under `tests/`. Every surface directory is
rootless, so pytest imports its modules by bare basename and those basenames must
stay globally unique across the test tree.

## Fixtures

All four are defined in `tests/conftest.py`; the first three are session-scoped
and requested by name, and the last is function-scoped and autouse.

| Fixture | Live database? | Yields |
|---|---|---|
| `profile` | no | The declared matrix profile the database-backed lane runs (`pg-full`) |
| `profile_run` | **yes** | That profile's own run: a self-managed Testcontainers Postgres, paired with the name the run reports under |
| `wheelhouse` | no | A directory of freshly built wheels plus a package-name-to-wheel map |
| `release_case_runtimes` | no | Nothing. After each test it closes every runtime a `Database` composed in that test left open |

`profile` resolves a declaration and opens nothing, so it classifies no item; it
is what `profile_run` is opened by, and what a database-backed test names
when it needs the dialect its run executed in. Requesting it alone leaves an item
`dbfree`.

`release_case_runtimes` classifies no item either, and that is why it reads
`request.fixturenames` instead of requesting `profile_run`: requesting it would
put the live database in every item's fixture closure and reclassify the whole
suite as database-backed. A connected handle owns a pool, so a handle a test
composed and never closed would hold connections and maintenance threads for the
rest of the session; each handle that closes itself leaves this backstop nothing
to do.

`profile_run` is what the profile provisions for itself, so a test never names a
port: it resets through the run, executes through `run.port`, and hands the run
itself to `adapter.run_case`, which reports the profile that opened the database it
executed against. It is the only route to a live database, and
`tools/check_database_access.py` is what keeps it so: it fails when any module
under `tests/` calls a seam that starts a container or opens a connection
anywhere but inside that fixture. It reads an acquisition on a value as well as
on a class, so `adapter.open()` is caught as surely as `PostgresAdapter.open`,
and it follows either through the bindings and containers a test might pass it
along. One call may be waived on its own line with a
`# database-access: <why>` marker; a marker carrying no reason is not honored,
so every waiver is a diff line with its justification on it — the same bargain
`# noqa` and `# pyright: ignore` are reviewed under. There is one in the tree,
on the unit test that proves what `open` delegates to with the delegate
stubbed. When Docker or the provider cannot be brought
up the fixture records the reason and skips, and the terminal summary prints
every recorded reason; `PARALLAX_REQUIRE_DB=1` turns any such skip into a
failure. Docker setup — including the one-time `~/.testcontainers.properties` fix
for runtimes other than Docker Desktop — is in the root `README.md`.

## Scheduling labels

Three classes, and every collected item carries exactly one.

| Class | Marker | Means | Owning command |
|---|---|---|---|
| Database-free | `dbfree` | The item requires neither resource below | `just python-test-dbfree` |
| Database-backed | `db` | Its fixture closure reaches a live database, so Docker is required | `just python-test-db` |
| Cost | `cost` | It reads the whole interpreter, so it needs one no other test shares | `just python-test-cost` |

No marker is ever written beside a test. `tests/conftest.py`'s collection hook
adds one to every item, chosen by what that item requires — `profile_run` in its
resolved fixture closure for `db`, the `in_a_child_interpreter` boundary on its
function for `cost` — so the label covers indirect requests, is decided per item
rather than per file, and can be neither missing nor doubled. Requiring both is a
contradiction the hook fails on rather than an order of precedence. Deleting
`profile_run` from a test's signature, or the boundary from its definition,
reclassifies that test.

`tools/check_database_access.py` and `tools/check_instrument_access.py` are what
keep the labels honest: each confines its class's resource to the one entry point
the classifier reads, so a test acquiring it another way is a finding rather than
a silent misclassification.

Scheduling class is orthogonal to the semantic surface. `compatibility/` and
`api/` hold both database classes; `dialect/` and `distribution/` are entirely
`dbfree`; `provider_contract/` is entirely `db`; `unit/` holds `dbfree` and the
whole of `cost`. A surface is therefore never a substitute for a class, in either
direction.

Two further markers exist and classify nothing — `compile_sweep` and
`adapter_smoke` are focused selectors for iteration, authored where they apply.
They are the whole catalog beside the three classes.

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
| Every cost gate | `just python-check-cost` |
| All three | `just python-check` |
| Iterate on one surface | `just python-test-<surface>` |
| Iterate on one module | `cd languages/python && uv run pytest tests/<surface>/test_<name>.py` |
| The Pydantic parity corpus on the declared floor | `just python-test-pydantic-floor` |

The six `python-test-<surface>` recipes are for iteration and are deliberately no
aggregate's dependency: a surface cuts across both scheduling classes, so a gate
composing one would run part of it twice.

`python-test-pydantic-floor` is outside every aggregate for a different reason.
It selects one module — `tests/unit/test_pydantic_parity.py`, which
`python-test-dbfree` already grades on the locked Pydantic — and overlays the
oldest release `parallax-core` declares onto the workspace resolution for that
one run, so what it adds is the other end of the supported range rather than
another selection. The `ci` / `python-test-pydantic-floor` job below is what owns
that verdict; no local aggregate reaches it.

## Continuous integration

| Workflow and job | Matrix | Runs |
|---|---|---|
| `ci` / `python-check-dbfree` | CPython 3.13 / 3.14 | 3.14 runs `just python-check-dbfree`, checked out at `fetch-depth: 0` because `python-coverage-diff` compares against `origin/main`; 3.13 runs `just python-test-dbfree` with coverage disabled to prove runtime compatibility without repeating the coverage verdict on the slower C tracer |
| `ci` / `python-check-db` | — | `just python-check-db` on CPython 3.14 against Testcontainers Postgres, with `PARALLAX_REQUIRE_DB=1` so a provider skip fails the job |
| `ci` / `python-check-cost` | shards `1/6` to `6/6` | `just python-check-cost I/6` on CPython 3.14, one cell per shard of the class `just check` omits so the local gate stays fast; `test_scheduling_partition.py` proves the matrix expands to those six cells alone, that each runs ungated, and that their selections partition the class |
| `ci` / `python-test-pydantic-floor` | — | `just python-test-pydantic-floor` on CPython 3.14, resolving the parity corpus against the minimum Pydantic release `parallax-core` declares instead of the locked one, so the seam a published value's serialization is built over is graded at both ends of the supported range |
| `python-deps-refresh` / `refresh` (monthly) | — | `uv lock --upgrade` on CPython 3.14, opening a pull request the four jobs above still gate |

The cost cells are balanced by what each cost item last cost, read from
`tests/_support/cost_durations.json`: `--shard I/N` sorts the class's items
heaviest first and places each onto the lightest shard so far, so the N shards
partition the class however the file is populated, and an item the file does not
know weighs the mean of the ones it does. Only the balance depends on the file's
currency, never the partition. The file is a required input to a sharded session
all the same: unreadable for any reason, holding no durations at all, holding
anything but non-negative numbers of seconds a float holds finitely, or holding
durations that together total more than a float holds — no mean for an unknown
item to weigh — it is that session's usage error naming the file, because
weighing every item the same is a shard mechanism doing nothing while every
partition check stays green.

Refresh it after the class changes shape with the recipe-less step
[`AGENTS.md`](AGENTS.md) names, then commit the result.

A store replaces the file only when the session both collected the whole cost
class and ran it to completion: no shard, no path argument or ignored path — the
narrowing that leaves an item uncollected and so unobservable — then a call
report for every cost item it did collect, and a successful exit status. Whatever
expression selected the class is not read: `-m cost` and any wider expression
collect it whole, and one that cuts into it leaves items collected without a call
report. Then what the session measured is the file, and an item deleted or
renamed since the last refresh leaves no entry behind to weigh a shard that will
never run it. Every other session — one cell's `--shard I/N`, a narrower
selection, a run that failed, was interrupted, or never reached part of what it
collected — stores what it measured and keeps every other entry, because those
entries are the only record of the items it did not run.
