"""Unit tests for value-object materialization graph reads (m-value-object).

A value object materializes WITH its owning entity in one round trip: the owner's
single statement projects the structured-document column, and the harness decodes
that column into the declared nested to-one / to-many projection for `then.graph`
comparison — there is no deep-fetch child statement. These tests exercise the
projection logic and the runner wiring OFFLINE (a fake DB serving the Customer
fixtures the way each driver would), so they also pin that the authored
`then.graph` of cases 023 / 024 equals the materializer's projection of the real
fixtures.

The graph comparison of a to-many value-object member (`phones`) preserves
document order: element order in a `many` member is semantic (m-value-object).
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.case import load_case, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _alias_document_presence_projections,
    _assert_single_statement_graph,
    _graphs_equal,
    _MaterializedRow,
    _project_value_object,
    _reference_identity_row,
)
from reference_harness.document_codec import DocumentEncodingError, decode_stored

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_CASE_023 = "m-value-object-023-graph-nested-materialization.yaml"
_CASE_024 = "m-value-object-024-graph-filtered-materialization.yaml"
_CASE_119 = "m-inheritance-119-value-object-family-variant-overlap-graph.yaml"


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


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_document_presence_projection_gets_a_collision_safe_execution_alias(
    dialect: str,
) -> None:
    sql = (
        "select t0.name as __parallax_document_presence_1, "
        "not t0.address is null, t0.address from customer t0"
    )
    executable, keys = _alias_document_presence_projections(sql, dialect, _customer_model())
    assert keys == frozenset({"__parallax_document_presence_1_1"})
    assert "__parallax_document_presence_1" in executable
    assert "__parallax_document_presence_1_1" in executable


@pytest.mark.parametrize(
    ("dialect", "lock"),
    [("postgres", "for share of t0"), ("mariadb", "lock in share mode")],
)
def test_document_presence_aliasing_preserves_an_outer_lock_around_a_nested_union(
    dialect: str, lock: str
) -> None:
    sql = (
        "select t0.id, not t0.address is null, t0.address from customer t0 join ("
        "select t1.id from customer t1 union all select t2.id from customer t2"
        f") u on u.id = t0.id {lock}"
    )
    executable, keys = _alias_document_presence_projections(sql, dialect, _customer_model())
    assert keys == frozenset({"__parallax_document_presence_1"})
    assert executable.lower().endswith(lock)
    if dialect == "mariadb":
        assert "for share" not in executable.lower()


def test_unquoted_projection_alias_collisions_use_database_identifier_folding() -> None:
    sql = (
        "select t0.name as __PARALLAX_DOCUMENT_PRESENCE_1, "
        "not t0.address is null, t0.address from customer t0"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_1_1"})
    assert "__parallax_document_presence_1_1" in executable


def test_document_presence_metadata_resolves_a_derived_table_alias() -> None:
    sql = (
        "select not p1.address is null, p1.address "
        "from (select * from customer t0 where t0.id > 0 offset 0) p1"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_0"})
    assert "__parallax_document_presence_0" in executable


def test_document_presence_metadata_resolves_an_explicit_derived_passthrough() -> None:
    sql = (
        "select not p1.address is null, p1.address "
        "from (select t0.address as address from customer t0) p1"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_0"})
    assert "__parallax_document_presence_0" in executable


def test_derived_alias_over_a_scalar_column_is_not_document_presence_metadata() -> None:
    sql = (
        "select not p1.address is null, p1.address "
        "from (select t0.id as address from customer t0) p1"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert executable == sql
    assert keys == frozenset()


def test_quoted_derived_scalar_alias_does_not_collide_with_unquoted_document_alias() -> None:
    sql = (
        'select not p1."Address" is null, p1."Address" '
        'from (select t0.address as address, t0.id as "Address" from customer t0) p1'
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert executable == sql
    assert keys == frozenset()


def test_quoted_derived_document_alias_retains_its_distinct_identity() -> None:
    sql = (
        'select not p1."Address" is null, p1."Address" '
        'from (select t0.id as address, t0.address as "Address" from customer t0) p1'
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_0"})
    assert executable.count("__parallax_document_presence_0") == 1


def test_set_operation_lineage_rejects_a_later_arms_swapped_ordinal() -> None:
    sql = (
        "select not p1.address is null, p1.address from ("
        "select t0.address as address, t0.id as id from customer t0 "
        "union all select t0.id as id, t0.address as address from customer t0) p1"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert executable == sql
    assert keys == frozenset()


def test_set_operation_lineage_keeps_the_first_arms_output_ordinal() -> None:
    sql = (
        "select not p1.address is null, p1.address from ("
        "select t0.address as address, t0.id as id from customer t0 "
        "union all select t0.address as payload, t0.id as customer_id from customer t0) p1"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_0"})
    assert executable.count("__parallax_document_presence_0") == 1


def test_a_syntactic_pair_over_a_scalar_column_is_not_presence_metadata() -> None:
    sql = "select not t0.id is null, t0.id from customer t0"
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert executable == sql
    assert keys == frozenset()


def test_tpcs_false_padding_is_presence_only_when_a_sibling_branch_proves_the_ordinal() -> None:
    sql = (
        "select false, cast(null as jsonb), 'A' as family_variant "
        "union all select not t0.address is null, t0.address, "
        "'B' as family_variant from customer t0"
    )
    executable, keys = _alias_document_presence_projections(sql, "postgres", _customer_model())
    assert keys == frozenset({"__parallax_document_presence_0"})
    assert executable.count("__parallax_document_presence_0") == 2


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


@pytest.mark.parametrize("stored_profile", [None, '"VariantNote"'])
def test_family_variant_overlap_tracks_null_and_equal_vo_payload_provenance(
    stored_profile: Any,
) -> None:
    loaded = _load(_CASE_119)
    case = replace(loaded, raw=deepcopy(loaded.raw))
    case.then["graph"] = {
        "VariantRecord": [{"id": 2, "profile": None, "familyVariant": "VariantNote"}]
    }

    class _OverlapDb:
        dialect = "postgres"

        def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
            if sql == "select id, kind from variant_record":
                return [{"id": 2, "kind": "note"}]
            return [{"id": 2, "kind": "note", "familyVariant": stored_profile}]

    _assert_single_statement_graph(case, _OverlapDb())


@pytest.mark.parametrize("payload", [None, "VariantNote"])
def test_reference_identity_filter_uses_consumption_state_not_payload_equality(
    payload: Any,
) -> None:
    unconsumed = _MaterializedRow(
        {"id": 2, "familyVariant": payload},
        value_object_columns={"familyVariant": payload},
    )
    consumed = _MaterializedRow(
        {"id": 2, "familyVariant": payload},
        value_object_columns={"familyVariant": payload},
        consumed_value_object_columns={"familyVariant"},
    )
    assert _reference_identity_row(unconsumed) == {"id": 2}
    assert _reference_identity_row(consumed) == {"id": 2, "familyVariant": payload}


def test_projection_drops_undeclared_keys_and_publishes_what_the_document_held() -> None:
    address = _address_decl()

    # A present composite: the undeclared `zip` is dropped, the omitted `elevation`
    # contributes no key, the deep to-one and the to-many materialize.
    doc = {
        "street": "S",
        "city": "C",
        "geo": {"country": "NO", "zip": "x", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [{"type": "home", "number": "1"}],
    }
    assert _project_value_object(address, doc) == {
        "street": "S",
        "city": "C",
        "geo": {"country": "NO", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [{"type": "home", "number": "1"}],
    }

    # A nested `one` the document HOLDS as a non-object collapses to null and keeps
    # its key; a `many` is always carried, because it has no absent state. The
    # omitted leaves are absent rather than null.
    assert _project_value_object(address, {"geo": "scalar", "phones": "scalar"}) == {
        "geo": None,
        "phones": [],
    }

    # A null / absent top-level value object is null.
    assert _project_value_object(address, None) is None


def test_projection_decodes_every_leaf_by_its_declared_type() -> None:
    # A document stores the codec's portable spelling for each declared type, and a
    # getter yields what a Column of that type reads back as. Six of the twelve rows
    # differ between the two — the ones models/customer.yaml does not reach — so the
    # projection is exercised here against the model that declares one leaf of every
    # type, at both depths.
    profile = (
        load_model(COMPATIBILITY_ROOT, "models/document-codec.yaml")
        .entity("Sample")
        .value_objects[0]
    )
    stored = {
        "amount": "10.25",
        "blob": "0a1b",
        "day": "2026-01-15",
        "clock": "09:30:00",
        "instant": "2026-01-15T09:30:00.000000Z",
        "token": "123e4567-e89b-12d3-a456-426614174000",
        "entries": [{"price": "19.99", "issued": "2026-02-01"}],
    }
    projected = cast("dict[str, Any]", _project_value_object(profile, stored))
    assert projected["amount"] == Decimal("10.25")
    assert projected["instant"] == "2026-01-15T09:30:00+00:00"
    assert projected["blob"] == "0a1b"
    assert projected["day"] == "2026-01-15"
    assert projected["clock"] == "09:30:00"
    assert projected["token"] == "123e4567-e89b-12d3-a456-426614174000"
    element = cast("list[dict[str, Any]]", projected["entries"])[0]
    assert element["price"] == Decimal("19.99")
    assert element["issued"] == "2026-02-01"


def test_a_present_leaf_outside_its_declared_type_fails_where_absence_still_collapses() -> None:
    # The two halves of one boundary, at the projection the graph comparison reads. A
    # member the document HOLDS in a state the model has — a JSON null, an
    # occurrence of the wrong kind — is carried, collapsed; a member the document
    # omits is carried only where it has no absent state (`entries`, a `many`). A
    # leaf that IS supplied and is not an encoding of its declared type is a state
    # the model does not have, so it is refused instead of reaching the projected
    # node as the raw stored value.
    profile = (
        load_model(COMPATIBILITY_ROOT, "models/document-codec.yaml")
        .entity("Sample")
        .value_objects[0]
    )
    collapsing = cast(
        "dict[str, Any]",
        _project_value_object(profile, {"small": None, "origin": "unknown", "entries": None}),
    )
    assert collapsing["small"] is None
    assert "amount" not in collapsing
    assert collapsing["origin"] is None
    assert collapsing["entries"] == []

    with pytest.raises(DocumentEncodingError, match="invalid stored data"):
        _project_value_object(profile, {"amount": "bogus"})
    with pytest.raises(DocumentEncodingError, match="invalid stored data"):
        _project_value_object(profile, {"entries": [{"issued": "2026-13-40"}]})


def test_decode_document_is_dialect_agnostic() -> None:
    assert decode_stored('{"a": 1}') == {"a": 1}  # MariaDB JSON text
    assert decode_stored(b'{"a": 1}') == {"a": 1}  # MariaDB JSON bytes
    assert decode_stored({"a": 1}) == {"a": 1}  # Postgres parsed jsonb
    assert decode_stored(None) is None  # SQL NULL column


def test_many_value_object_document_order_is_semantic() -> None:
    model = _customer_model()
    actual = {
        "Customer": [
            {
                "id": 1,
                "address": {
                    "phones": [
                        {"type": "home", "number": "1"},
                        {"type": "work", "number": "2"},
                    ]
                },
            }
        ]
    }
    expected = {
        "Customer": [
            {
                "id": 1,
                "address": {
                    "phones": [
                        {"type": "work", "number": "2"},
                        {"type": "home", "number": "1"},
                    ]
                },
            }
        ]
    }
    assert not _graphs_equal(actual, expected, model)
