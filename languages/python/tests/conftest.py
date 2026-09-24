"""Runner-required fixtures and hooks for the Parallax Python test suites.

Everything the runner does not require lives under ``_support/``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests._support import cost_durations
from tests._support.distributions import ALL_PACKAGES, Wheelhouse
from tests._support.repo import PY_ROOT
from tests._support.root_ownership import close_owned_roots

if TYPE_CHECKING:
    from parallax.conformance.profile import Profile

# Database-backed checks skipped because Docker/Postgres was unavailable — printed
# in a final summary so a skip is never silent; CI fails on any skip.
_DB_SKIPS: list[str] = []

# The designated entry points to a live database. A test reaching one by any other
# route would be classified `dbfree` while needing a container.
_DATABASE_FIXTURES = frozenset({"profile_run"})

# What marks an item as needing an interpreter no other test shares, spelled as
# `tests/unit/memory_instruments.py` sets it. The runner's own module imports no
# instrument, so the two spellings are held together by
# `tools/check_instrument_access.py` rather than by one importing the other.
_OWN_INTERPRETER_ATTRIBUTE = "__parallax_own_interpreter__"

_WHOLE_CLASS = "1/1"
_MERGE, _REPLACE = "merge", "replace"

_recorded_durations: dict[str, float] = {}
_store_durations = False
_DURATION_REFUSALS: list[str] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--shard",
        default=_WHOLE_CLASS,
        metavar="I/N",
        help="run the I-th of N shards of the cost class; every other class is unaffected",
    )
    # Bare to merge, `=replace` to replace. The value is optional, so a path
    # argument following the bare flag is taken as the value; `choices` makes
    # that the option's usage error rather than a silently dropped path.
    parser.addoption(
        "--store-cost-durations",
        nargs="?",
        const=_MERGE,
        choices=(_REPLACE,),
        default=None,
        metavar="replace",
        help=(
            f"after the run, record every cost item's call duration in "
            f"{cost_durations.COST_DURATIONS.name}, merged into what is stored; "
            f"`--store-cost-durations=replace` instead replaces the file, and only when "
            f"the session passed"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    global _store_durations
    _store_durations = config.getoption("--store-cost-durations") is not None and not hasattr(
        config, "workerinput"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Assign each collected item its scheduling class, then keep the cost
    class's requested shard.

    The class is read off what the item requires — its resolved fixture closure
    for a database, the boundary its function carries for an interpreter of its
    own — rather than authored beside the test, so it covers indirect requests,
    is decided per item rather than per module, and can be neither absent nor
    doubled. An item that is not a test function requires neither and is
    therefore `dbfree`.

    Two resources at once is a contradiction rather than a precedence: a reading
    over the whole interpreter cannot be taken of a process a container is also
    living in, so the run fails instead of picking a winner.

    A shard is one of N sets the cost class is balanced into by what each item
    last cost, in a deterministic order over the stable collection order, so the
    N shards partition the class and their union is the whole of it
    (core/spec/language-testing.md §9); `--shard` never touches another class,
    and the default keeps everything.
    """
    for item in items:
        function = item if isinstance(item, pytest.Function) else None
        needs_database = (
            bool(_DATABASE_FIXTURES.intersection(function.fixturenames)) if function else False
        )
        needs_interpreter = (
            getattr(function.obj, _OWN_INTERPRETER_ATTRIBUTE, False) is True if function else False
        )
        if needs_database and needs_interpreter:
            raise pytest.UsageError(
                f"{item.nodeid} requires both a live database and an interpreter of its own; "
                f"a scheduling class names one resource (core/spec/language-testing.md §5)"
            )
        if needs_database:
            item.add_marker(pytest.mark.db)
        elif needs_interpreter:
            item.add_marker(pytest.mark.cost)
        else:
            item.add_marker(pytest.mark.dbfree)

    index, count = cost_durations.index_and_count(str(config.getoption("--shard")))
    if count > 1:
        cost_items = [item for item in items if item.get_closest_marker("cost") is not None]
        known = cost_durations.known()
        shard_of = cost_durations.shard_of_each(
            cost_durations.weights([item.nodeid for item in cost_items], known), count
        )
        deselected = [
            item for item, shard in zip(cost_items, shard_of, strict=True) if shard != index
        ]
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            excluded = set(deselected)
            items[:] = [item for item in items if item not in excluded]


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record a cost item's call duration.

    Under xdist the controller receives every worker's reports, so the one
    process that writes the file observes the whole session.
    """
    if _store_durations and report.when == "call" and "cost" in report.keywords:
        _recorded_durations[report.nodeid] = report.duration


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Store what the cost items this session ran cost.

    A replacement drops every item the session did not observe, so it is refused
    for a session that did not pass: an item it failed to reach would lose its
    only record.
    """
    if not _recorded_durations:
        return
    replace = session.config.getoption("--store-cost-durations") == _REPLACE
    if replace and exitstatus != pytest.ExitCode.OK:
        _DURATION_REFUSALS.append(
            f"{cost_durations.COST_DURATIONS.name} left unchanged: the session did not pass "
            f"(exit status {int(exitstatus)})"
        )
        return
    cost_durations.store(_recorded_durations, replace=replace)


def record_db_skip(reason: str) -> None:
    """Record a skipped database-backed check for the end-of-session summary."""
    if reason not in _DB_SKIPS:
        _DB_SKIPS.append(reason)


@pytest.fixture(scope="session")
def profile() -> Profile:
    """The declared matrix profile the database-backed lane runs.

    Resolving it opens nothing, so this fixture classifies no item: what needs a
    container is a run of this profile, not the declaration.
    """
    from parallax.conformance.profile import profile_for

    return profile_for("pg-full")


@pytest.fixture(scope="session")
def profile_run(profile: Profile) -> Iterator[Any]:
    """A session-scoped run of the declared profile over a self-managed
    Testcontainers Postgres.

    The profile provisions it and pairs its own reporting name with the port it
    opened, so the database-backed lane runs the declaration itself rather than a
    parallel wiring of it, and a case run here cannot be reported under a profile
    that did not open it.

    Skips the database-backed lane with a reason (never silently) when Docker or
    the provider cannot be brought up; the ``python-check-db`` CI job fails on any
    such skip, so a green CI run has exercised every database-backed check.
    """
    opened = ExitStack()
    try:
        run = opened.enter_context(profile.provisioned())
    except Exception as exc:
        reason = f"Testcontainers Postgres unavailable: {type(exc).__name__}: {exc}"
        record_db_skip(reason)
        pytest.skip(reason)
        return
    try:
        yield run
    finally:
        opened.close()


@pytest.fixture(autouse=True)
def release_case_runtimes(request: pytest.FixtureRequest) -> Iterator[None]:
    """Close, after each test, every runtime a Database composed here left open.

    A connected handle owns a pool, so one composed per case and never closed
    would hold connections and maintenance threads for the whole session — and a
    corpus of hundreds of cases would run the server out of connections long
    before it ran out of cases. Each handle that closes itself retires its own;
    this is the backstop for the ones that do not.

    It reads ``request.fixturenames`` rather than requesting the database
    fixture, because requesting it would put it in every item's fixture closure
    and reclassify the whole suite as database-backed.
    """
    with close_owned_roots():
        yield
    for fixture in _DATABASE_FIXTURES.intersection(request.fixturenames):
        request.getfixturevalue(fixture).release_case_runtimes()


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print a refused duration replacement and the database-backed skip summary;
    silent skips are forbidden."""
    for refusal in _DURATION_REFUSALS:
        terminalreporter.write_sep("=", "--store-cost-durations=replace refused", red=True)
        terminalreporter.write_line(refusal)
    if not _DB_SKIPS:
        return
    terminalreporter.write_sep("=", "database-backed checks skipped")
    for reason in _DB_SKIPS:
        terminalreporter.write_line(f"SKIPPED (database): {reason}")
    if os.environ.get("PARALLAX_REQUIRE_DB") == "1":
        terminalreporter.write_line(
            "PARALLAX_REQUIRE_DB=1 set: skipped database checks are a failure"
        )
        raise pytest.UsageError("database-backed checks were skipped but required")


@pytest.fixture(scope="session")
def wheelhouse(tmp_path_factory: pytest.TempPathFactory) -> Wheelhouse:
    """Build every distribution wheel once per session into a temp directory."""
    out = tmp_path_factory.mktemp("wheelhouse")
    for package in ALL_PACKAGES:
        subprocess.run(
            ["uv", "build", "--package", package, "--wheel", "--out-dir", str(out)],
            cwd=PY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    wheels: dict[str, Path] = {}
    for package in ALL_PACKAGES:
        dist = package.replace("-", "_")
        matches = sorted(out.glob(f"{dist}-*.whl"))
        assert matches, f"no wheel built for {package}"
        wheels[package] = matches[-1]
    return Wheelhouse(directory=out, wheels=wheels)
