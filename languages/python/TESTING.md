# Python testing map

The [root testing guide](../../TESTING.md) owns the verification workflow.
[pyproject.toml](pyproject.toml) owns tool settings and thresholds, except the
duplication scan's in [.jscpd.json](.jscpd.json) and the deptry flags every
distribution shares, which [the dependency audit](tools/audit_dependencies.py)
states once. The [root justfile](../../justfile) owns commands. This map
explains placement and fixtures without duplicating those inventories.

## Placement

| Surface | Directory | Subject |
|---|---|---|
| Internal | `tests/unit/` | Internal seams, diagnostics, and tool checks |
| Compatibility | `tests/compatibility/` | Portable corpus compilation and execution |
| API | `tests/api/` | Idiomatic public behavior, coverage partition, generated guide, API snapshot |
| Dialect | `tests/dialect/` | Pure dialect strategy |
| Provider | `tests/provider_contract/` | Database provider contract and shipped adapter |
| Distribution | `tests/distribution/` | Built wheels and clean installation |

The test root holds those surfaces, `_support/`, `__init__.py`, and
`conftest.py`. The unit surface mirrors the source path:
`parallax/<pkg>/<sub>/<module>.py` maps to
`tests/unit/<pkg>/<sub>/test_<module>*.py`. Tool tests live under
`tests/unit/tools/`; whole-tree unit tests live at `tests/unit/`.
The other surfaces are organized by behavior.

Put a helper beside its consumers when one subtree contains them all.
Cross-surface support belongs in `tests/_support/`; shared unit-only support
belongs at the narrowest common unit-test directory. Import helpers by their
`tests.*` names, never from another test module. Do not maintain a prose list
of helper modules.

## Where a test goes

Prove a behavior at the most public seam that can observe it:

1. **A compatibility case** for portable behavior: a refusal in the rejected
   lane, SQL text in compile, rows and stored state in run. The corpus is the
   binding-neutral oracle.
2. **`tests/api`** for public behavior, through the public verbs and the shipped
   adapter against `profile_run`'s database. Provider-specific behavior goes to
   `tests/provider_contract`.
3. **`tests/unit`**, `dbfree`, for one of these reasons:
   - a large input space that cases or API tests would spell row by row;
   - a failure a real database cannot provoke, such as an injected adapter,
     pool or driver fault, a race, or a write its rollback erases;
   - grading and comparison logic in `parallax-conformance`, proved with
     refusing inputs, because a bug there makes a check silently stop checking.

The changed-line gate reads the `db` and `dbfree` classes together, so a line a
database test reaches needs no second test.

A unit test reaches production through public verbs or a module's interface; a
scripted port stands in for the database to inject what a real one cannot
produce. A call count or memory layout earns a test only when callers rely on
the count, correctness needs the single run, or losing it changes cost by an
order of growth, such as entity or model width; the cost class owns the rest of
performance. Enforce a structural invariant by type, such as a private factory,
before writing an architecture test.

## What a test proves

A test earns its place by going red when the behavior it names breaks:

- Break the behavior in memory, one condition at a time, and read the assertion
  that fails. A crash, an unrelated refusal, or a fixture artifact is not that
  behavior going red.
- Give each condition its own input, differing from a passing one only in that
  property.
- Assert the effect itself. Coverage shows that a line ran, not that anything
  checked it.
- Check what the seam compares before relying on it:
  - the rejected sweep grades the issue code alone, and a case raises exactly
    one issue;
  - a run-only `harness`-lane case is graded only by the run sweep, through the
    conformance adapter, so it says nothing about compilation or the Typed
    verbs; an `api-conformance`-lane case runs through the public API instead;
  - when two phases raise the same code for an input, a case at the outer door
    pins neither, so the phase with its own door keeps a test;
  - a real database cannot see a write its rollback erases, or tell apart two
    plans that store the same row.

To retire a test, land its replacement first, show a remaining test goes red
under each break the retired one caught, and keep the last `dbfree` test of a
product function.

## Fixtures and resources

[conftest.py](tests/conftest.py) defines the fixtures and scheduling classifier.

| Fixture | Resource |
|---|---|
| `profile` | Matrix declaration only; does not open a database |
| `profile_run` | The live Testcontainers Postgres run |
| `aws_run` | One CI run attempt's database on the deployed Aurora environment |
| `committed_cost_evidence` | Reading retained captures and the memory gates |
| `wheelhouse` | Built distribution wheels |
| `release_case_runtimes` | Autouse cleanup: closes the roots a test registered, and closes any runtime it left open and fails it |

Database-backed tests acquire their database only through `profile_run`.
They provision through the shipped generator:
`schema_delta(evolve(ABSENT, model), dialect)`, so a test database holds exactly
the statements the generator emits, and an authored secondary Index exists there
as the separately named object a violation reports.
Standby proofs reach a primary and its streaming standby through
`profile_run.replication()`, which opens one pair per run on first use; they
live under `tests/provider_contract/replication/` and carry
`xdist_group("replication")` so the database lane opens one pair, not one per
worker.
Tests owning a Database Root close it explicitly or register it through
`tests._support.root_ownership.own_root`. A test that leaves a runtime open
fails, after the cleanup fixture has closed it.

Provider-hosted tests reach the Aurora environment only through `aws_run`,
which [aws_run.py](tests/_support/aws_run.py) implements; they live under
`tests/provider_contract/aws/`. Unlike `profile_run` it never skips: a missing
environment, credential, lock, or answer fails the cell. Its lifetime is
unit-tested over scripted ports, and the suite itself runs only in CI.

The resource-access checker confines each class's resource to its fixture:
provisioning a local server to `profile_run`, reaching the provider to
`aws_run`, and opening a connection to either. A line-local
`# database-access: <reason>` or `# cloud-access: <reason>` exemption, for the
class reporting the call, requires a meaningful reason, such as a mocked
acquisition. When a local provider is unavailable `profile_run` records the
skip; `PARALLAX_REQUIRE_DB=1` makes it fail.

## Scheduling and selection

The collection hook derives exactly one class from each item's resource needs:
`db` or `cloud` from the resource fixture in its closure, `cost` from the
child-interpreter boundary or the committed-evidence fixture, otherwise
`dbfree`. Do not author those markers onto tests. Requiring two classes'
resources is an error. A `cloud` item is selected only when
`PARALLAX_CLOUD_PROVIDERS` names its provider, which only a CI cell does, so no
local selection reaches the provider; a cloud run naming none collects nothing
and fails. The
instrument-access checker requires the boundary on every test that calls a
whole-interpreter reader directly; any other route fails at run time, because
each reader refuses a process the boundary did not start. Likewise the runner
refuses an in-process open of committed evidence by an item that did not request
its fixture.
A test grading the cost tooling over synthetic portfolios supplies its own gates
rather than reading the committed ones.

`--shard I/N` splits the `cost` class into CI cells, balanced by what each item
last cost in [cost_durations.json](tests/_support/cost_durations.json). A change
that adds cost items merges their durations in with
`uv run pytest <selection> --store-cost-durations`. A periodic refresh, which
also drops renamed or deleted items, replaces the file from the whole class
with `uv run pytest -m cost -n auto --store-cost-durations=replace`, and writes
nothing unless that session passes.

`--db-shard I/N` partitions only the database class using
[db_durations.json](tests/_support/db_durations.json), keeping every `xdist_group`
on one shard. The default selects the whole class.

`--timing-report DIR` writes one JSONL file per pytest process under a unique
session directory, starting at plugin configuration. Worker events distinguish
session startup from collection; the controller records each item's setup, call,
and teardown reports, including failures. Reports are flushed as they arrive, so
completed phases survive a later failure. Parallel durations overlap and must not
be summed as elapsed wall time.

Use `just python-test-<surface>` for focused iteration, or select a module from
this directory with `uv run pytest tests/<surface>/<path>`.
The focused selectors are intentionally outside aggregates. Inspect actual
execution ownership with `just show-gates <command>`.

`just python-test-pydantic-floor` tests the declared minimum Pydantic version;
the normal environment uses the lock. CI owns supported-version and shard
matrices in [ci.yml](../../.github/workflows/ci.yml).

## Expected failures and executable documentation

An `xfail` test asserts correct behavior for a reproduced defect and names
that defect. Strict mode in tool configuration makes an unexpected pass fail;
remove the marker when fixed. Environment gaps belong to explicit skips.

Public API examples remain executable conformance tests whether or not the
usage guide publishes them. Curate the guide for teaching, regenerate it from
source, and retain the complete coverage partition and behavioral assertions.

## Memory evidence

[Memory gates](spec/memory-gates.yaml) and
[the budget contract](spec/budget-contract.yaml) own measurement thresholds.
Use the [root cost workflow](../../TESTING.md#ci-and-cost-evidence) for capture
and freshness checks. Shared memory instruments and their test workloads remain
code; changes to them do not require updating an inventory here.
