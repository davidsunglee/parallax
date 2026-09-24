# Python testing map

The [root testing guide](../../TESTING.md) owns the verification workflow.
[pyproject.toml](pyproject.toml) owns tool settings and thresholds; the
[root justfile](../../justfile) owns commands. This map explains placement and
fixtures without duplicating those inventories.

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

## Fixtures and resources

[conftest.py](tests/conftest.py) defines the fixtures and scheduling classifier.

| Fixture | Resource |
|---|---|
| `profile` | Matrix declaration only; does not open a database |
| `profile_run` | The live Testcontainers Postgres run |
| `wheelhouse` | Built distribution wheels |
| `release_case_runtimes` | Autouse cleanup for roots and runtimes left open by a test |

Database-backed tests acquire their database only through `profile_run`.
Tests owning a Database Root should close it explicitly or register it through
`tests._support.root_ownership.own_root`. The cleanup fixture is a backstop.

The database-access checker confines connection acquisition to the fixture.
A line-local `# database-access: <reason>` exemption requires a meaningful
reason, such as a mocked acquisition. When a provider is unavailable the fixture
records the skip; `PARALLAX_REQUIRE_DB=1` makes it fail.

## Scheduling and selection

The collection hook derives exactly one class from each item's resource needs:
`db` from the live fixture closure, `cost` from the child-interpreter boundary,
otherwise `dbfree`. Do not author those markers onto tests. Requiring both
isolated resources is an error. The database and instrument access checkers
enforce the resource boundaries.

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
