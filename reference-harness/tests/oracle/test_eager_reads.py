"""Ordinary eager reads through ``assert_case_read``.

The rows a script hands back are PHYSICAL: the raw discriminator column a
table-per-hierarchy golden projects, the per-branch ``family_variant`` literal a
table-per-concrete-subtype golden projects, the shared Structured Column a
Relational Document Layout golden projects. What the case authors in ``then.rows``
is the LOGICAL result. Every test here is therefore also a test that the oracle
derives the second from the first rather than passing the first through.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.object_query_oracle import assert_case_read

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_ORDER_BY_LIMIT = "m-object-query-001-order-by-limit.yaml"
_DOCUMENT_LAYOUT = "m-storage-layout-017-document-layout-provisioned-read.yaml"
_TPH_ABSTRACT_ROOT = "m-inheritance-003-tph-abstract-root-read.yaml"
_TPCS_ABSTRACT_ROOT = "m-inheritance-050-tpcs-abstract-root-read.yaml"
_TPCS_NO_DOCUMENT_SLOT = "m-inheritance-052-tpcs-narrow-to-abstract-subtype.yaml"
_TPH_DOCUMENT_UNION = "m-inheritance-124-document-layout-tph-sibling-path-reuse.yaml"
_PARTIAL_TPH_ROOT = "m-inheritance-147-partial-tph-root-read-unknown-tag.yaml"
_LOCKED_TPH_DOCUMENT = "m-concurrency-054-document-layout-tph-partitioned.yaml"
_BYTES_CELL = "m-core-011-bytes-cell-spelling-hex-letters.yaml"

_BEASTS: list[dict[str, Any]] = [
    {"id": 1, "kind": "wolf", "name": "Akela", "keeper_id": 10, "howl": "aroo"},
    {"id": 2, "kind": "bear", "name": "Baloo", "keeper_id": 11, "howl": None},
    {"id": 3, "kind": "wolf", "name": "Raksha", "keeper_id": 10, "howl": "yip"},
]

# `m-object-query-001` projects plain Columns of a non-inheritance entity, so its
# physical row and its logical row are the same document.
_ORDER_ROWS: list[dict[str, Any]] = [
    {
        "id": 5,
        "name": "Alan",
        "sku": "C_50%",
        "qty": 25,
        "price": Decimal("50.75"),
        "active": False,
        "ordered_on": "2024-05-25",
    },
    {
        "id": 42,
        "name": "Grace",
        "sku": "A-999",
        "qty": 30,
        "price": Decimal("99.99"),
        "active": True,
        "ordered_on": "2024-06-30",
    },
]

# The shared Table `payment` carries the raw tag column `kind`; `_type` is
# derived from the tag metadata map and never projected.
_PAYMENT_ROWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "kind": "card",
        "amount": Decimal("100.00"),
        "card_network": "Visa",
        "tendered": None,
    },
    {
        "id": 2,
        "kind": "card",
        "amount": Decimal("50.00"),
        "card_network": "Amex",
        "tendered": None,
    },
    {
        "id": 3,
        "kind": "cash",
        "amount": Decimal("20.00"),
        "card_network": None,
        "tendered": Decimal("25.00"),
    },
]

# One `traveler` row is its primary key plus the shared Structured Column holding
# every other member. Row 2 omits `note`; row 3 stores an explicit JSON null.
_TRAVELER_ROWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "payload": {
            "displayName": "Ada",
            "score": 7,
            "joinedOn": "2026-01-15",
            "note": "north wing",
            "address": {"city": "Oslo"},
            "tags": [],
        },
    },
    {
        "id": 2,
        "payload": {
            "displayName": "Bo",
            "score": 30,
            "joinedOn": "2025-12-31",
            "address": {"city": "Bergen"},
            "tags": [],
        },
    },
    {
        "id": 3,
        "payload": {
            "displayName": "Cyd",
            "score": None,
            "joinedOn": None,
            "note": None,
            "address": None,
            "tags": [],
        },
    },
]

_PAYMENT_DOCUMENT_ROWS: list[dict[str, Any]] = [
    {"id": 1, "kind": "card", "payload": {"detail": "visa-4242", "authorizationCode": "AUTH-7"}},
    {"id": 2, "kind": "cash", "payload": {"detail": "12.50"}},
]


def _tpcs_rows(case: Case) -> list[dict[str, Any]]:
    """The authored rows as the `union all` physically projects them.

    A table-per-concrete-subtype position has no tag column: each branch projects
    the concrete subtype NAME as a literal aliased to `family_variant`, and the
    oracle resolves it to `_type`.
    """
    return [
        {
            **{key: value for key, value in row.items() if key != "_type"},
            "family_variant": row["_type"].rpartition(".")[2],
        }
        for row in case.expected_rows
    ]


def test_a_golden_stating_a_type_on_a_row_outside_a_family_fails(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_ORDER_BY_LIMIT)
    case.then["rows"][0]["_type"] = "parallax.compatibility.Order"

    with pytest.raises(CaseFailure, match="rows != then.rows"):
        assert_case_read(case, ScriptedReads(results=[_ORDER_ROWS, _ORDER_ROWS]))


def test_a_read_whose_golden_returns_the_authored_rows_passes(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    reads = ScriptedReads(results=[_ORDER_ROWS, _ORDER_ROWS])

    assert_case_read(case, reads)

    assert len(reads.calls) == 2


def test_the_golden_statement_reaches_the_executor_with_its_authored_binds(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    reads = ScriptedReads(results=[_ORDER_ROWS, _ORDER_ROWS])

    assert_case_read(case, reads)

    assert reads.calls[0] == (case.golden_statements("postgres")[0], (2,))


def test_the_independent_reference_oracle_runs_on_the_same_executor(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    reads = ScriptedReads(results=[_ORDER_ROWS, _ORDER_ROWS])

    assert_case_read(case, reads)

    assert reads.calls[1] == (case.reference_sql_for("postgres"), ())


def test_a_read_authoring_no_reference_sql_runs_one_statement(corpus_case: CaseLoader) -> None:
    case = corpus_case(_TPH_ABSTRACT_ROOT)
    reads = ScriptedReads(results=[_PAYMENT_ROWS])

    assert_case_read(case, reads)

    assert len(reads.calls) == 1


def test_row_comparison_is_order_insensitive(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    shuffled = list(reversed(_ORDER_ROWS))
    reads = ScriptedReads(results=[shuffled, shuffled])

    assert_case_read(case, reads)


def test_a_golden_row_the_case_did_not_author_fails(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    wrong = [dict(_ORDER_ROWS[0]) | {"qty": 24}, _ORDER_ROWS[1]]
    reads = ScriptedReads(results=[wrong])

    with pytest.raises(CaseFailure, match="then.statements .postgres. rows != then.rows"):
        assert_case_read(case, reads)


def test_a_reference_oracle_disagreeing_with_the_golden_fails(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    reads = ScriptedReads(results=[_ORDER_ROWS, _ORDER_ROWS[:1]])

    with pytest.raises(CaseFailure, match="referenceSql rows != then.rows"):
        assert_case_read(case, reads)


def test_numeric_comparison_stays_exact_without_a_declared_tolerance(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDER_BY_LIMIT)
    drifted = [dict(_ORDER_ROWS[0]) | {"price": Decimal("50.7500001")}, _ORDER_ROWS[1]]
    reads = ScriptedReads(results=[drifted])

    with pytest.raises(CaseFailure):
        assert_case_read(case, reads)


def test_a_declared_tolerance_admits_an_inexact_numeric(damaged_case: CaseLoader) -> None:
    case = damaged_case(_ORDER_BY_LIMIT)
    case.then["tolerance"] = 1e-6
    drifted = [dict(_ORDER_ROWS[0]) | {"price": Decimal("50.7500001")}, _ORDER_ROWS[1]]
    reads = ScriptedReads(results=[drifted, drifted])

    assert_case_read(case, reads)


@pytest.mark.parametrize("cell", ["0a1b", "0A1B", "0a1B"])
def test_a_bytes_cell_grades_in_either_case(corpus_case: CaseLoader, cell: str) -> None:
    case = corpus_case(_BYTES_CELL)

    assert_case_read(case, ScriptedReads("mariadb", [[{"id": 1, "payload_hex": cell}]]))


def test_a_bytes_cell_spelling_other_octets_fails(corpus_case: CaseLoader) -> None:
    case = corpus_case(_BYTES_CELL)
    reads = ScriptedReads("mariadb", [[{"id": 1, "payload_hex": "0A1C"}]])

    with pytest.raises(CaseFailure, match="then.statements .mariadb. rows != then.rows"):
        assert_case_read(case, reads)


def test_a_bytes_cell_a_case_authors_uppercase_fails(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BYTES_CELL)
    case.then["rows"] = [{"id": 1, "payload_hex": "0A1B"}]
    reads = ScriptedReads("mariadb", [[{"id": 1, "payload_hex": "0A1B"}]])

    with pytest.raises(CaseFailure, match="then.statements .mariadb. rows != then.rows"):
        assert_case_read(case, reads)


def test_a_bytes_cell_a_wrapped_union_carries_grades_in_either_case(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_BYTES_CELL)
    arm = "select t0.id, hex(t0.payload) payload_hex from px.bytes_cell t0"
    case.then["statements"][0]["sql"]["mariadb"] = (
        f"select u.id, u.payload_hex from (({arm} where t0.id = 1) union all ({arm})) u"
    )

    assert_case_read(case, ScriptedReads("mariadb", [[{"id": 1, "payload_hex": "0A1B"}]]))


def test_a_string_column_spelled_like_a_bytes_cell_compares_exactly(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_BYTES_CELL)
    case.model.descriptor["entities"] = [
        {
            "name": "TextCell",
            "namespace": "parallax.compatibility",
            "table": "text_cell",
            "persistence": "read-only",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "payload_hex", "type": "string"},
            ],
        },
        case.model.descriptor.pop("entity"),
    ]
    case.when["objectQuery"]["target"] = "parallax.compatibility.TextCell"
    case.then["statements"][0]["sql"]["mariadb"] = "select t0.id, t0.payload_hex from text_cell t0"
    case.then["rows"] = [{"id": 1, "payload_hex": "abc"}]
    reads = ScriptedReads("mariadb", [[{"id": 1, "payload_hex": "ABC"}]])

    with pytest.raises(CaseFailure, match="then.statements .mariadb. rows != then.rows"):
        assert_case_read(case, reads)


def test_an_abstract_target_read_materializes_the_type_from_the_raw_tag(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TPH_ABSTRACT_ROOT)
    reads = ScriptedReads(results=[_PAYMENT_ROWS])

    assert_case_read(case, reads)


def test_a_tag_value_naming_no_composed_subtype_publishes_an_unavailable_root(
    corpus_case: CaseLoader,
) -> None:
    # The provisioning model composes Bear, the reader does not: the stored tag is
    # classified against the reader alone, so the position is null and diagnosed.
    case = corpus_case(_PARTIAL_TPH_ROOT)
    assert case.setup_model.entity("Bear").canonical_name == "parallax.compatibility.Bear"

    assert_case_read(case, ScriptedReads(results=[_BEASTS, _BEASTS]))


def test_an_unknown_tag_left_undiagnosed_fails(damaged_case: CaseLoader) -> None:
    case = damaged_case(_PARTIAL_TPH_ROOT)
    del case.then["storedDataIssues"]

    with pytest.raises(CaseFailure, match="stored-data-family-tag-unknown diagnoses"):
        assert_case_read(case, ScriptedReads(results=[_BEASTS, _BEASTS]))


def test_an_unknown_tag_diagnosed_at_a_member_fails(damaged_case: CaseLoader) -> None:
    case = damaged_case(_PARTIAL_TPH_ROOT)
    case.then["storedDataIssues"][0]["issues"][0]["member"] = "parallax.compatibility.Beast.name"

    with pytest.raises(CaseFailure, match="stored-data-family-tag-unknown diagnoses"):
        assert_case_read(case, ScriptedReads(results=[_BEASTS, _BEASTS]))


def test_an_unknown_tag_diagnosis_authored_where_none_is_stored_fails(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_PARTIAL_TPH_ROOT)
    wolves = [_BEASTS[0], dict(_BEASTS[1]) | {"kind": "wolf", "howl": None}, _BEASTS[2]]

    with pytest.raises(CaseFailure, match="materialized graph"):
        assert_case_read(case, ScriptedReads(results=[wolves, wolves]))


def test_an_abstract_read_dropping_the_tag_column_from_its_golden_fails(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TPH_ABSTRACT_ROOT)
    entry = case.then["statements"][0]
    entry["sql"]["postgres"] = entry["sql"]["postgres"].replace("t0.kind, ", "")
    reads = ScriptedReads(results=[_PAYMENT_ROWS])

    with pytest.raises(CaseFailure, match="does not project the tag column"):
        assert_case_read(case, reads)


def test_a_table_per_concrete_subtype_read_resolves_the_branch_literal(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TPCS_ABSTRACT_ROOT)
    reads = ScriptedReads(results=[_tpcs_rows(case)])

    assert_case_read(case, reads)


def test_a_union_branch_reading_the_wrong_table_fails(damaged_case: CaseLoader) -> None:
    case = damaged_case(_TPCS_NO_DOCUMENT_SLOT)
    for dialect, sql in case.then["statements"][0]["sql"].items():
        case.then["statements"][0]["sql"][dialect] = sql.replace(
            "from px.receipt t0", "from px.invoice t0"
        )
    reads = ScriptedReads(results=[_tpcs_rows(case)])

    with pytest.raises(CaseFailure, match="`union all` branch 1 must read from"):
        assert_case_read(case, reads)


_VALUE_OBJECT_ROWS = "m-value-object-001-nested-eq.yaml"
_DOCUMENT_RESIDENT_VALUE_OBJECTS = "m-storage-layout-017-document-layout-provisioned-read.yaml"
_ORDERED_TPCS_VALUE_OBJECT = "m-inheritance-134-tpcs-union-ordered.yaml"

_ADA = {"id": 1, "name": "Ada", "address": {"city": "Oslo"}}
_LINUS = {"id": 2, "name": "Linus", "address": {"city": "Oslo"}}


def test_a_flat_assertion_omits_a_value_object_from_the_golden_and_the_reference(
    corpus_case: CaseLoader,
) -> None:
    """`then.rows` states scalars, whichever statement carried the Document slot."""
    assert_case_read(
        corpus_case(_VALUE_OBJECT_ROWS), ScriptedReads(results=[[_ADA, _LINUS], [_ADA, _LINUS]])
    )


def test_a_flat_assertion_omits_a_document_resident_value_object(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_DOCUMENT_RESIDENT_VALUE_OBJECTS)
    stored = [
        {
            "id": row["id"],
            "payload": {
                "displayName": row["display_name"],
                "score": row["score"],
                "joinedOn": row["joined_on"],
                "note": row["note"],
                "address": {"city": "Oslo"},
                "tags": [{"label": "one"}],
            },
        }
        for row in case.expected_rows
    ]

    assert_case_read(case, ScriptedReads(results=[stored]))


def test_a_flat_assertion_omits_every_branch_of_a_union_value_object(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDERED_TPCS_VALUE_OBJECT)
    stored = [
        row | {"annotation": {"note": "kept"} if row["family_variant"] == "Memo" else None}
        for row in _tpcs_rows(case)
    ]

    assert_case_read(case, ScriptedReads(results=[stored, stored]))


@pytest.mark.parametrize(
    "results",
    [
        pytest.param([[_ADA | {"surprise": 1}, _LINUS], [_ADA, _LINUS]], id="golden"),
        pytest.param([[_ADA, _LINUS], [_ADA | {"surprise": 1}, _LINUS]], id="reference"),
    ],
)
def test_a_flat_assertion_keeps_an_unexpected_scalar_column(
    corpus_case: CaseLoader, results: list[list[dict[str, Any]]]
) -> None:
    with pytest.raises(CaseFailure, match=r"rows != then\.rows"):
        assert_case_read(corpus_case(_VALUE_OBJECT_ROWS), ScriptedReads(results=results))


def test_a_flat_assertion_cannot_state_a_value_object(damaged_case: CaseLoader) -> None:
    case = damaged_case(_VALUE_OBJECT_ROWS)
    case.then["rows"][0]["address"] = _ADA["address"]

    with pytest.raises(CaseFailure, match=r"rows != then\.rows"):
        assert_case_read(case, ScriptedReads(results=[[_ADA, _LINUS]]))


def test_a_document_layout_read_fans_the_structured_column_into_its_members(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_DOCUMENT_LAYOUT)
    reads = ScriptedReads(results=[_TRAVELER_ROWS])

    assert_case_read(case, reads)


def test_the_document_presence_cell_is_aliased_for_execution_and_never_compared(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_DOCUMENT_LAYOUT)
    presence = "__parallax_document_presence_1"
    reads = ScriptedReads(results=[[row | {presence: True} for row in _TRAVELER_ROWS]])

    assert_case_read(case, reads)

    assert presence in reads.statements[0]
    assert presence not in case.golden_statements("postgres")[0]


def test_a_document_member_the_case_did_not_author_fails(corpus_case: CaseLoader) -> None:
    case = corpus_case(_DOCUMENT_LAYOUT)
    wrong = [
        _TRAVELER_ROWS[0] | {"payload": _TRAVELER_ROWS[0]["payload"] | {"score": 8}},
        *_TRAVELER_ROWS[1:],
    ]
    reads = ScriptedReads(results=[wrong])

    with pytest.raises(CaseFailure, match="rows != then.rows"):
        assert_case_read(case, reads)


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_partitioned_document_read_is_observed_on_both_dialects(
    corpus_case: CaseLoader, dialect: str
) -> None:
    case = corpus_case(_TPH_DOCUMENT_UNION)
    reads = ScriptedReads(dialect, results=[_PAYMENT_DOCUMENT_ROWS, _PAYMENT_DOCUMENT_ROWS])

    assert_case_read(case, reads)

    assert reads.calls[0][1] == tuple(case.statement_binds(0, dialect))
    assert reads.calls[1] == (case.reference_sql_for(dialect), ())


def _renamed(case: Case) -> Case:
    """The same case under a file name that names no locking family."""
    return dataclasses.replace(case, path=case.path.with_name("m-sql-999-renamed.yaml"))


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_locked_partitioned_document_read_joins_its_outer_base_table(
    corpus_case: CaseLoader, dialect: str
) -> None:
    case = _renamed(corpus_case(_LOCKED_TPH_DOCUMENT))
    reads = ScriptedReads(dialect, results=[_PAYMENT_DOCUMENT_ROWS, _PAYMENT_DOCUMENT_ROWS])

    assert_case_read(case, reads)

    assert reads.calls[0][1] == tuple(case.statement_binds(0, dialect))


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_locked_partitioned_document_read_without_its_outer_base_join_fails(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = _renamed(damaged_case(_LOCKED_TPH_DOCUMENT))
    entry = case.then["statements"][0]
    entry["sql"][dialect] = (
        entry["sql"][dialect]
        .replace("from px.payment_document t0 join (", "from (", 1)
        .replace(") u on u.id = t0.id", ") t0", 1)
    )

    with pytest.raises(CaseFailure, match="locking TPH partition must join one outer base Table"):
        assert_case_read(case, ScriptedReads(dialect))


# --- what a read must state before its rows can be materialized ---------------


def test_a_case_that_is_not_read_shaped_is_refused(damaged_case: CaseLoader) -> None:
    """Rows are materialized against the READ they belong to, and nothing else.

    The target, the ``narrowTo``, the golden the projection shape is asserted
    from, and the result member the form is read off all come from one case, so a
    case of another shape would answer them from members that mean something else.
    """
    case = damaged_case(_ORDER_BY_LIMIT)
    case.raw["shape"] = "boundary"
    reads = ScriptedReads(results=[_ORDER_ROWS])

    with pytest.raises(CaseFailure, match="this case's shape is 'boundary'"):
        assert_case_read(case, reads)


_DORMANT_TPH_ROOT = "m-inheritance-154-dormant-tph-root-read-layout-twin-columns.yaml"
_DORMANT_TPCS_ROWS = "m-inheritance-157-dormant-tpcs-root-row-read-layout-twin-document.yaml"


@pytest.mark.parametrize("name", [_DORMANT_TPH_ROOT, _DORMANT_TPCS_ROWS])
def test_a_position_with_no_concrete_is_graded_without_a_statement(
    corpus_case: CaseLoader, name: str
) -> None:
    reads = ScriptedReads()

    assert_case_read(corpus_case(name), reads)

    assert reads.calls == []


def test_a_position_with_no_concrete_returns_no_row(damaged_case: CaseLoader) -> None:
    case = damaged_case(_DORMANT_TPCS_ROWS)
    case.then["rows"] = [{"id": 1}]

    with pytest.raises(CaseFailure, match="returns no row"):
        assert_case_read(case, ScriptedReads())


def test_a_position_with_no_concrete_delivers_no_root(damaged_case: CaseLoader) -> None:
    case = damaged_case(_DORMANT_TPH_ROOT)
    case.then["graph"] = {"Prototype": [None]}

    with pytest.raises(CaseFailure, match="delivers no root"):
        assert_case_read(case, ScriptedReads())
