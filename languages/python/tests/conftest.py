"""Runner-required fixtures and hooks for the Parallax Python test suites.

Everything the runner does not require lives under ``_support/``.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

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

# What a cost item is known to cost, by node id, from the last stored run. The
# shards are balanced over these; an item the file does not know weighs the mean
# of the ones it does, so a new test degrades the balance and never the partition.
_COST_DURATIONS = PY_ROOT / "tests" / "_support" / "cost_durations.json"
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
        help=f"after the run, merge every cost item's call duration into {_COST_DURATIONS.name}",
    )


def pytest_configure(config: pytest.Config) -> None:
    global _store_durations
    _store_durations = bool(config.getoption("--store-cost-durations")) and not hasattr(
        config, "workerinput"
    )


def _cardinal(digits: str) -> int | None:
    """The number an ASCII digit string names, or ``None`` when it names none.

    ``str.isdigit`` answers for spellings Python's own parser then rejects, such
    as ``'²'`` and a run of more digits than the interpreter will convert.
    """
    if not (digits.isascii() and digits.isdigit()):
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _shard(spec: str) -> tuple[int, int]:
    """The ``(index, count)`` a ``--shard I/N`` spelling names, one-based.

    Every other spelling is the option's usage error rather than a failure
    partway through the session that read it.
    """
    index, separator, count = spec.partition("/")
    first, total = _cardinal(index), _cardinal(count)
    if separator and first is not None and total is not None and 1 <= first <= total:
        return first, total
    raise pytest.UsageError(f"--shard expects I/N with 1 <= I <= N, not {spec!r}")


def _known_durations() -> dict[str, float]:
    if not _COST_DURATIONS.exists():
        return {}
    return {str(k): float(v) for k, v in json.loads(_COST_DURATIONS.read_text()).items()}


def _shard_of_each(weights: Sequence[float], count: int) -> list[int]:
    """The one-based shard each weighted item lands in.

    Heaviest first, each onto the lightest shard so far, ties to the lowest
    index: deterministic over stable input, and within one item's weight of the
    best balance.
    """
    loads = [0.0] * count
    shard = [0] * len(weights)
    for position in sorted(range(len(weights)), key=lambda p: (-weights[p], p)):
        target = min(range(count), key=lambda i: (loads[i], i))
        loads[target] += weights[position]
        shard[position] = target + 1
    return shard


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

    index, count = _shard(str(config.getoption("--shard")))
    if count == 1:
        return
    cost_items = [item for item in items if item.get_closest_marker("cost") is not None]
    known = _known_durations()
    unknown = sum(known.values()) / len(known) if known else 1.0
    shard_of = _shard_of_each([known.get(item.nodeid, unknown) for item in cost_items], count)
    deselected = [item for item, shard in zip(cost_items, shard_of, strict=True) if shard != index]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        excluded = set(deselected)
        items[:] = [item for item in items if item not in excluded]


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _store_durations and report.when == "call" and "cost" in report.keywords:
        _recorded_durations[report.nodeid] = report.duration


def pytest_sessionfinish() -> None:
    if not _store_durations or not _recorded_durations:
        return
    merged = _known_durations() | {k: round(v, 1) for k, v in _recorded_durations.items()}
    _COST_DURATIONS.write_text(json.dumps(dict(sorted(merged.items())), indent=1) + "\n")


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
