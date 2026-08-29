"""Ordinary eager reads through ``assert_case_read``.

The rows a script hands back are PHYSICAL: the raw discriminator column a
table-per-hierarchy golden projects, the per-branch ``family_variant`` literal a
table-per-concrete-subtype golden projects, the shared Structured Column a
Relational Document Layout golden projects. What the case authors in ``then.rows``
is the LOGICAL result. Every test here is therefore also a test that the oracle
derives the second from the first rather than passing the first through.
"""

from __future__ import annotations

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
_TPH_DOCUMENT_UNION = "m-inheritance-124-document-layout-tph-sibling-path-reuse.yaml"

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

# The shared Table `payment` carries the raw tag column `kind`; `familyVariant` is
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
    oracle renames it to `familyVariant`.
    """
    return [
        {("family_variant" if key == "familyVariant" else key): value for key, value in row.items()}
        for row in case.expected_rows
    ]


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


def test_an_abstract_target_read_materializes_family_variant_from_the_raw_tag(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TPH_ABSTRACT_ROOT)
    reads = ScriptedReads(results=[_PAYMENT_ROWS])

    assert_case_read(case, reads)


def test_a_tag_value_naming_no_concrete_subtype_fails(corpus_case: CaseLoader) -> None:
    case = corpus_case(_TPH_ABSTRACT_ROOT)
    stray = [dict(_PAYMENT_ROWS[0]) | {"kind": "cheque"}, *_PAYMENT_ROWS[1:]]
    reads = ScriptedReads(results=[stray])

    with pytest.raises(CaseFailure, match="maps to no concrete subtype"):
        assert_case_read(case, reads)


def test_an_abstract_read_dropping_the_tag_column_from_its_golden_fails(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TPH_ABSTRACT_ROOT)
    entry = case.then["statements"][0]
    entry["sql"]["postgres"] = entry["sql"]["postgres"].replace("t0.kind, ", "")
    reads = ScriptedReads(results=[_PAYMENT_ROWS])

    with pytest.raises(CaseFailure, match="does not project the tag column"):
        assert_case_read(case, reads)


def test_a_table_per_concrete_subtype_read_renames_the_branch_literal(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TPCS_ABSTRACT_ROOT)
    reads = ScriptedReads(results=[_tpcs_rows(case)])

    assert_case_read(case, reads)


def test_a_union_branch_reading_the_wrong_table_fails(damaged_case: CaseLoader) -> None:
    case = damaged_case(_TPCS_ABSTRACT_ROOT)
    for dialect, sql in case.then["statements"][0]["sql"].items():
        case.then["statements"][0]["sql"][dialect] = sql.replace("from memo t0", "from invoice t0")
    reads = ScriptedReads(results=[_tpcs_rows(case)])

    with pytest.raises(CaseFailure, match="`union all` branch 1 must read from"):
        assert_case_read(case, reads)


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


def test_a_read_stating_no_result_member_is_refused(damaged_case: CaseLoader) -> None:
    """The result form is derived from the member the case authored, never passed.

    A row-form read materializes its Attributes alone and an instance-form one
    additionally carries every applicable Value Object occurrence, so a read
    stating neither member leaves that undecided rather than defaulting.
    """
    case = damaged_case(_ORDER_BY_LIMIT)
    del case.then["rows"]
    reads = ScriptedReads(results=[_ORDER_ROWS])

    with pytest.raises(CaseFailure, match="states no result member"):
        assert_case_read(case, reads)
