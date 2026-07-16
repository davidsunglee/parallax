"""Unit tests for value-object materialization graph reads (m-value-object).

A value object materializes WITH its owning entity in one round trip: the owner's
single statement projects the structured-document column, and the harness decodes
that column into the declared nested to-one / to-many projection for `then.graph`
comparison — there is no deep-fetch child statement. These tests exercise the
projection logic and the runner wiring OFFLINE (a fake DB serving the Customer
fixtures the way each driver would), so they also pin that the authored
`then.graph` of cases 023 / 024 equals the materializer's projection of the real
fixtures.

The graph comparison of a to-many value-object member (`phones`) is
order-insensitive (a multiset compare): element order in a `many` member is
unspecified (m-value-object), so the authored arrays match regardless of order
while element multiplicity is still enforced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import load_case, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_single_statement_graph,
    _decode_document,
    _project_value_object,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_CASE_023 = "m-value-object-023-graph-nested-materialization.yaml"
_CASE_024 = "m-value-object-024-graph-filtered-materialization.yaml"


def _customer_model():
    return load_model(COMPATIBILITY_ROOT, "models/customer.yaml")


def _address_decl() -> dict[str, Any]:
    return _customer_model().entity("Customer").value_objects[0]


def _load(case_file: str):
    return load_case(COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / case_file)


class _CustomerDocDb:
    """Serve the Customer fixtures the way each driver returns them.

    The golden statement projects ``t0.address`` and yields ``{id, name, address}``;
    the reference oracle omits it and yields ``{id, name}``. On ``postgres`` the
    ``address`` column is already parsed (a ``dict`` / ``None``, as psycopg yields
    ``jsonb``); on ``mariadb`` it is JSON text (a ``str`` / ``None``, as pymysql
    yields the ``json`` column). This proves the materializer is dialect-agnostic.
    """

    def __init__(self, dialect: str, ids: list[int]) -> None:
        self.dialect = dialect
        by_id = {row["id"]: row for row in _customer_model().entity("Customer").rows}
        self._rows = [by_id[i] for i in ids]

    def _address(self, address: Any) -> Any:
        if self.dialect == "mariadb" and address is not None:
            return json.dumps(address)
        return address

    def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
        if "t0.address" in sql:  # the golden owner statement
            return [
                {"id": r["id"], "name": r["name"], "address": self._address(r.get("address"))}
                for r in self._rows
            ]
        return [{"id": r["id"], "name": r["name"]} for r in self._rows]  # the oracle


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_full_composite_materializes_the_authored_graph(dialect: str) -> None:
    # The whole nested composite (to-one geo -> point, to-many phones) plus every
    # absence-collapse state must materialize from the ONE document column and equal
    # case 023's authored then.graph — on both dialects, from a single statement.
    _assert_single_statement_graph(_load(_CASE_023), _CustomerDocDb(dialect, list(range(1, 11))))


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_filtered_materialization_matches_the_authored_graph(dialect: str) -> None:
    # A filtered read still materializes the matched owners' full composite in one
    # round trip (case 024: Oslo -> ids 1, 2).
    _assert_single_statement_graph(_load(_CASE_024), _CustomerDocDb(dialect, [1, 2]))


def test_a_mismatched_document_fails_the_graph() -> None:
    case = _load(_CASE_023)

    class _Corrupt(_CustomerDocDb):
        def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
            rows = super().query(sql, binds)
            if "t0.address" in sql and rows:
                address = rows[0]["address"]
                if isinstance(address, str):
                    doc = json.loads(address)
                    doc["city"] = "WRONG"
                    rows[0]["address"] = json.dumps(doc)
                elif isinstance(address, dict):
                    corrupted = dict(address)
                    corrupted["city"] = "WRONG"
                    rows[0]["address"] = corrupted
            return rows

    with pytest.raises(CaseFailure):
        _assert_single_statement_graph(case, _Corrupt("postgres", list(range(1, 11))))


def test_reference_oracle_identity_mismatch_fails() -> None:
    # The oracle pins the matched row SET (identity columns): dropping a row from the
    # oracle result must fail even though the graph itself matches.
    case = _load(_CASE_024)

    class _DropOracleRow(_CustomerDocDb):
        def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
            rows = super().query(sql, binds)
            if "t0.address" not in sql:  # the oracle statement
                return rows[:1]
            return rows

    with pytest.raises(CaseFailure):
        _assert_single_statement_graph(case, _DropOracleRow("postgres", [1, 2]))


def test_projection_drops_undeclared_keys_and_collapses_absence() -> None:
    address = _address_decl()

    # A present composite: the undeclared `zip` is dropped, a missing `elevation`
    # is null, the deep to-one and the to-many materialize.
    doc = {
        "street": "S",
        "city": "C",
        "geo": {"country": "NO", "zip": "x", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [{"type": "home", "number": "1"}],
    }
    assert _project_value_object(address, doc) == {
        "street": "S",
        "city": "C",
        "geo": {"country": "NO", "elevation": None, "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [{"type": "home", "number": "1"}],
    }

    # A non-object nested `one` collapses to null; a non-array `many` collapses to [].
    assert _project_value_object(address, {"geo": "scalar", "phones": "scalar"}) == {
        "street": None,
        "city": None,
        "geo": None,
        "phones": [],
    }

    # A null / absent top-level value object is null.
    assert _project_value_object(address, None) is None


def test_decode_document_is_dialect_agnostic() -> None:
    assert _decode_document('{"a": 1}') == {"a": 1}  # MariaDB JSON text
    assert _decode_document(b'{"a": 1}') == {"a": 1}  # MariaDB JSON bytes
    assert _decode_document({"a": 1}) == {"a": 1}  # Postgres parsed jsonb
    assert _decode_document(None) is None  # SQL NULL column
