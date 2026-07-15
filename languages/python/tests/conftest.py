"""Shared fixtures for the Parallax Python workspace test suites."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

PY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PY_ROOT.parents[1]


def case_document(case: Any) -> dict[str, Any]:
    """A case's raw YAML document as a plain ``dict`` (test-side typed accessor)."""
    return cast("dict[str, Any]", dict(case.document))


# --------------------------------------------------------------------------- #
# Shared corpus-grading helpers (the run sweep and the API-suite story lane    #
# grade against the same case oracles, so the comparators live lane-neutral).  #
# --------------------------------------------------------------------------- #
def case_fixtures(case: Any) -> dict[str, Any]:
    """The fixtures the case's lifecycle loads before its action (m-case-format).

    A writeSequence case starts from an EMPTY schema and builds its own state
    unless it opts in with `given.fixtures: true`; every other shape starts from
    the model's default fixtures (a case that injects nothing omits `given`).
    """
    doc = case_document(case)
    given = cast("dict[str, Any]", doc.get("given") or {})
    if case.shape == "writeSequence" and not given.get("fixtures"):
        return {}
    from parallax.conformance import provision

    return provision.load_fixtures(str(doc["model"]))


def _wire_row(row: dict[str, Any]) -> dict[str, Any]:
    # Observed rows arrive already wire-rendered; authored expectation rows are
    # normalized through the same m-db-port boundary so dates / uuids / bytes are
    # compared in one canonical form.
    from parallax.conformance import engine

    return {key: engine.wire_value(value) for key, value in row.items()}


def _to_decimal(value: object) -> object:
    """Coerce a numeric (or a wire-rendered numeric string) to an exact ``Decimal``.

    The corpus grades numerics as exact Decimals (m-case-format), so a ``decimal``
    money column matches to the cent regardless of scale. A wire-rendered decimal
    arrives as a numeric *string* — its canonical wire form is the exact string, not
    a float — so a numeric-looking string is parsed too; a non-numeric string / date
    / uuid raises and passes through for exact ``==``.
    """
    from decimal import Decimal, InvalidOperation

    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    return value


def _scalar_equal(observed: object, expected: object) -> bool:
    """Exact wire equality, with an exact-Decimal fallback for numerics.

    Exact ``==`` decides every string / date / uuid / bytes / bool value (so this
    never loosens a comparison that already holds); only a residual numeric
    difference — the wire-rendered ``decimal`` string ``"99.99"`` against the
    authored number ``99.99`` — reconciles in Decimal space. ``bool`` is never
    numeric (``True`` never equals ``1``).
    """
    from decimal import Decimal

    if observed == expected:
        return True
    if isinstance(observed, bool) or isinstance(expected, bool):
        return False
    left, right = _to_decimal(observed), _to_decimal(expected)
    return isinstance(left, Decimal) and isinstance(right, Decimal) and left == right


def _row_equal(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
    return observed.keys() == expected.keys() and all(
        _scalar_equal(observed[key], expected[key]) for key in observed
    )


def compare_rows(observed: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    """Order-insensitive multiset comparison (greedy — result sets are tiny)."""
    obs = [_wire_row(row) for row in observed]
    remaining = [_wire_row(row) for row in expected]
    assert len(obs) == len(remaining), f"row count: observed {obs!r} != expected {remaining!r}"
    for row in obs:
        for index, candidate in enumerate(remaining):
            if _row_equal(row, candidate):
                del remaining[index]
                break
        else:
            raise AssertionError(f"observed row unmatched: {row!r}\n  expected pool: {remaining!r}")
    assert not remaining, f"expected rows unmatched: {remaining!r}"


# --------------------------------------------------------------------------- #
# Graph comparison (m-case-format `then.graph` / `then.graphs` leaves): a      #
# recursive structural comparison over nested dicts/lists, sharing the same   #
# exact-Decimal / wire-normalized scalar rules `compare_rows` uses.           #
# --------------------------------------------------------------------------- #
def wire_value_deep(value: object) -> object:
    from parallax.conformance import engine

    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: wire_value_deep(v) for key, v in mapping.items()}
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [wire_value_deep(v) for v in items]
    return engine.wire_value(value)


def _values_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        expected_map = cast("Mapping[str, object]", expected)
        if not isinstance(observed, Mapping):
            return False
        observed_map = cast("Mapping[str, object]", observed)
        return set(observed_map) == set(expected_map) and all(
            _values_equal(observed_map[key], expected_map[key]) for key in expected_map
        )
    if isinstance(expected, list):
        expected_items = cast("list[object]", expected)
        if not isinstance(observed, list):
            return False
        observed_items = cast("list[object]", observed)
        if len(observed_items) != len(expected_items):
            return False
        if all(_values_equal(o, e) for o, e in zip(observed_items, expected_items, strict=True)):
            return True
        # A to-many value-object member's element order is UNSPECIFIED
        # (m-value-object); fall back to order-insensitive multiset matching —
        # a declared relationship `orderBy`'s exact order already matched above.
        remaining = list(expected_items)
        for item in observed_items:
            for index, candidate in enumerate(remaining):
                if _values_equal(item, candidate):
                    del remaining[index]
                    break
            else:
                return False
        return True
    return _scalar_equal(observed, expected)


def compare_graph(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """Assert one assembled `then.graph` / `then.graphs` leaf equals ``expected``
    (m-case-format), both sides normalized through the same wire-value rules
    `compare_rows` uses for a flat row."""
    observed_wire = wire_value_deep(dict(observed))
    expected_wire = wire_value_deep(dict(expected))
    assert _values_equal(observed_wire, expected_wire), (
        f"graph mismatch:\n  observed: {observed_wire!r}\n  expected: {expected_wire!r}"
    )


# Database-backed checks skipped because Docker/Postgres was unavailable — printed
# in a final summary so a skip is never silent (spec §6); CI fails on any skip.
_DB_SKIPS: list[str] = []


def record_db_skip(reason: str) -> None:
    """Record a skipped database-backed check for the end-of-session summary."""
    if reason not in _DB_SKIPS:
        _DB_SKIPS.append(reason)


@pytest.fixture(scope="session")
def provisioner() -> Iterator[Any]:
    """A session-scoped self-managed Testcontainers Postgres (spec §6).

    Skips the database-backed lane with a reason (never silently) when Docker or
    the provider cannot be brought up; the ``python-database`` CI job fails on any
    such skip, so a green CI run has exercised every database-backed check.
    """
    try:
        from parallax.conformance.provision import Provisioner

        instance = Provisioner()
    except Exception as exc:
        reason = f"Testcontainers Postgres unavailable: {type(exc).__name__}: {exc}"
        record_db_skip(reason)
        pytest.skip(reason)
        return
    try:
        yield instance
    finally:
        instance.close()


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


def adapter_schema() -> dict[str, Any]:
    """The conformance-adapter JSON Schema (the adapter wire contract)."""
    schema_path = REPO_ROOT / "core" / "schemas" / "conformance-adapter.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def canonical_snapshot_claim() -> dict[str, Any]:
    """The canonical ``slice-snapshot-1`` describe claim from ``slices.md``."""
    text = (REPO_ROOT / "core" / "spec" / "slices.md").read_text(encoding="utf-8")
    section = text.split("## Snapshot Conformance Slice", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "no fenced json claim under the Snapshot Conformance Slice heading"
    return json.loads(match.group(1))


# Production distributions first, then the dev-only conformance tooling.
PRODUCTION_PACKAGES: tuple[str, ...] = (
    "parallax-core",
    "parallax-snapshot",
    "parallax-postgres",
)
ALL_PACKAGES: tuple[str, ...] = (*PRODUCTION_PACKAGES, "parallax-conformance")


@dataclass(frozen=True)
class Wheelhouse:
    """A directory of freshly built wheels plus a package-name -> wheel map."""

    directory: Path
    wheels: dict[str, Path]


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
