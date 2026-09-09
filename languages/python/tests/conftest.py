"""Runner-required fixtures and hooks for the Parallax Python test suites.

Everything the runner does not require lives under ``_support/``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from _support import cost_durations
from _support.distributions import ALL_PACKAGES, Wheelhouse
from _support.repo import PY_ROOT

if TYPE_CHECKING:
    from parallax.conformance.profile import Profile

# Database-backed checks skipped because Docker/Postgres was unavailable — printed
# in a final summary so a skip is never silent (spec §6); CI fails on any skip.
_DB_SKIPS: list[str] = []

# The designated entry points to a live database. A test reaching one by any other
# route would be classified `dbfree` while needing a container.
_DATABASE_FIXTURES = frozenset({"profile_run"})

# What marks an item as needing an interpreter no other test shares, spelled as
# `tests/unit/memory_instruments.py` sets it. This module loads before any surface
# directory reaches the path and so cannot import that one; the two spellings are
# held together by `tools/check_instrument_access.py`.
_OWN_INTERPRETER_ATTRIBUTE = "__parallax_own_interpreter__"

_WHOLE_CLASS = "1/1"

# The key an xdist worker hands its collected cost items up under.
_COLLECTED_COST_ITEMS = "parallax_collected_cost_items"

_collected_cost_items: set[str] = set()
_recorded_durations: dict[str, float] = {}
_store_durations = False


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--shard",
        default=_WHOLE_CLASS,
        metavar="I/N",
        help="run the I-th of N shards of the cost class; every other class is unaffected",
    )
    parser.addoption(
        "--store-cost-durations",
        action="store_true",
        help=(
            f"after the run, record every cost item's call duration in "
            f"{cost_durations.COST_DURATIONS.name}: a run that measured the whole class replaces "
            f"what is stored, and every narrower or unfinished run merges into it"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    global _store_durations
    _store_durations = bool(config.getoption("--store-cost-durations")) and not hasattr(
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

    # Recorded here rather than read off the finished session because pytest's
    # own deselection — `--deselect`, `-k`, `--lf` — runs after this hook, and
    # what a store compares against is the class this session was handed.
    _collected_cost_items.update(
        item.nodeid for item in items if item.get_closest_marker("cost") is not None
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _store_durations and report.when == "call" and "cost" in report.keywords:
        _recorded_durations[report.nodeid] = report.duration


def _collected_the_whole_class(config: pytest.Config) -> bool:
    """Whether this session collected every cost item there is.

    Only the narrowing that happens before collection is answered for here,
    because it is the narrowing that leaves nothing to observe: a shard, a path
    argument, an ignored path or glob. A marker expression and a keyword deselect
    after the collection hook above has recorded the class, so an item either one
    drops stays counted as collected and unobserved. That is what tells an
    expression holding the class whole — `cost`, or any wider one — from an
    expression cutting into it, without reading either. Everything that narrows a
    session after collection is caught by :func:`pytest_sessionfinish` instead,
    which is what makes this necessary rather than sufficient.
    """
    _, count = cost_durations.index_and_count(str(config.getoption("--shard")))
    return (
        count == 1
        and config.args_source is not pytest.Config.ArgsSource.ARGS
        and not config.option.ignore
        and not config.option.ignore_glob
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Record what the cost items this session ran cost, and how completely it
    measured the class.

    A store replaces the file only for a session that measured the whole class,
    which takes more than collecting it: the run must also have reached a call
    report for every cost item it collected and ended successfully, or an
    interruption, a failure, or a late deselection would delete the entries of
    items it merely never reached.

    A distributed session collects in its workers and never in the process that
    writes the file, so each worker hands its collection up rather than storing
    anything itself.
    """
    if not session.config.getoption("--store-cost-durations"):
        return
    worker_output: dict[str, object] | None = getattr(session.config, "workeroutput", None)
    if worker_output is not None:
        worker_output[_COLLECTED_COST_ITEMS] = sorted(_collected_cost_items)
        return
    if not _recorded_durations:
        return
    cost_durations.store(
        _recorded_durations,
        collected_the_whole_class=_collected_the_whole_class(session.config),
        collected=_collected_cost_items,
        succeeded=exitstatus == pytest.ExitCode.OK,
    )


def pytest_testnodedown(node: Any) -> None:
    """Take the finished xdist worker's collection as part of this session's.

    The workers collect and the process holding this one does not, so what a
    store measures its observations against arrives here or nowhere. Each worker
    collects the whole selection, so a worker that goes down without handing
    anything up leaves the collection short only when no other worker handed the
    same set up; after a crash it is the unsuccessful exit status that keeps the
    session from replacing the file.
    """
    _collected_cost_items.update(
        cast("list[str]", getattr(node, "workeroutput", {}).get(_COLLECTED_COST_ITEMS, []))
    )


def record_db_skip(reason: str) -> None:
    """Record a skipped database-backed check for the end-of-session summary."""
    if reason not in _DB_SKIPS:
        _DB_SKIPS.append(reason)


@pytest.fixture(scope="session")
def profile() -> Profile:
    """The declared matrix profile the database-backed lane runs (spec §6).

    Resolving it opens nothing, so this fixture classifies no item: what needs a
    container is a run of this profile, not the declaration.
    """
    from parallax.conformance.profile import profile_for

    return profile_for("pg-full")


@pytest.fixture(scope="session")
def profile_run(profile: Profile) -> Iterator[Any]:
    """A session-scoped run of the declared profile over a self-managed
    Testcontainers Postgres (spec §6).

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


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print the database-backed skip summary (silent skips are forbidden, §6)."""
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
