"""Golden bind grading (`m-case-format` *Canonical literal oracles*): each
comparator on its own, and both at declared float positions.

A declared ``float32``/``float64`` position — a scalar Column or a Value Object
leaf — distinguishes ``-0.0`` from the canonical ``0.0``; a Json position, here a
document key the declaration does not name, keeps JSON-value equality. The
positions are read off each case's own golden statement and model.
"""

from __future__ import annotations

import copy
import decimal
from typing import Any, cast

import pytest

from parallax.conformance import case_format, engine
from parallax.core.base import FLOAT32, FLOAT64, INT64, STRING, Decimal
from parallax.core.db_port import JSON_NULL, ArrayBind, StructuredDocument
from tests._support.bind_positions import (
    Document,
    EachElement,
    Elements,
    statement_bind_positions,
)
from tests._support.case_corpus import case as corpus_case
from tests._support.corpus import case_document, compare_binds
from tests._support.sweep_goldens import assert_wire_binds, write_golden_statements


def _golden(case_id: str, index: int = 0) -> tuple[case_format.Case, str, list[Any]]:
    case = corpus_case(case_id)
    sql, binds = write_golden_statements(case)[index]
    return case, sql, binds


def _read_statement(case_id: str) -> tuple[case_format.Case, str, list[Any]]:
    """A read case's one Postgres golden statement."""
    case = corpus_case(case_id)
    (entry,) = cast("list[dict[str, Any]]", case_document(case)["then"]["statements"])
    sql = cast("str", entry["sql"] if isinstance(entry["sql"], str) else entry["sql"]["postgres"])
    binds = entry.get("binds", [])
    return case, sql, cast("list[Any]", binds["postgres"] if isinstance(binds, dict) else binds)


def _grade(case: case_format.Case, sql: str, golden: list[Any], observed: list[Any]) -> None:
    model = engine.load_case_metamodel(case)
    positions = statement_bind_positions(model, sql, golden)
    compare_binds(observed, golden, positions)
    assert_wire_binds(model, sql, golden, observed)


def test_a_declared_float_column_refuses_negative_zero() -> None:
    case, sql, golden = _golden("m-core-010")
    _grade(case, sql, golden, [1, 0.0, 0.0])
    for column in (1, 2):
        observed = list(golden)
        observed[column] = -0.0
        with pytest.raises(AssertionError, match=rf"^bind {column}: "):
            _grade(case, sql, golden, observed)


def test_a_declared_float_keeps_numeric_equality_away_from_zero() -> None:
    case, sql, _golden_binds = _golden("m-core-010")
    _grade(case, sql, [1, 20, 0], [1, 20.0, 0.0])


def test_a_declared_float_leaf_refuses_negative_zero_beside_a_json_key() -> None:
    case, sql, golden = _golden("m-document-codec-016")
    golden = copy.deepcopy(golden)
    cast("dict[str, Any]", golden[2])["extension"] = 0.0

    extension_negative = copy.deepcopy(golden)
    cast("dict[str, Any]", extension_negative[2])["extension"] = -0.0
    _grade(case, sql, golden, extension_negative)

    leaf_negative = copy.deepcopy(golden)
    cast("dict[str, Any]", leaf_negative[2])["measure"] = -0.0
    with pytest.raises(AssertionError, match=r"^bind 2: "):
        _grade(case, sql, golden, leaf_negative)


def test_a_casting_extraction_types_its_compared_bind() -> None:
    case, sql, binds = _read_statement("m-document-codec-005")
    positions = statement_bind_positions(engine.load_case_metamodel(case), sql, binds)
    assert positions == {1: FLOAT32}


def test_a_text_extraction_leaves_its_compared_bind_untyped() -> None:
    case, sql, binds = _read_statement("m-document-codec-008")
    assert statement_bind_positions(engine.load_case_metamodel(case), sql, binds) == {}


def test_a_nested_casting_extraction_resolves_through_the_occurrence() -> None:
    case, sql, binds = _read_statement("m-value-object-011")
    positions = statement_bind_positions(engine.load_case_metamodel(case), sql, binds)
    assert positions == {3: FLOAT64}


def test_a_document_path_assignment_types_each_value_bind() -> None:
    case, sql, binds = _golden("m-storage-layout-023", 1)
    positions = statement_bind_positions(engine.load_case_metamodel(case), sql, binds)
    assert positions == {1: STRING, 3: INT64, 4: INT64}


def test_a_shared_document_is_typed_by_the_owner_its_row_tags() -> None:
    case = corpus_case("m-inheritance-125")
    model = engine.load_case_metamodel(case)
    details: list[object] = []
    for sql, binds in write_golden_statements(case):
        document = statement_bind_positions(model, sql, binds)[2]
        assert isinstance(document, Document)
        details.append(document.members["detail"])
    assert details == [STRING, Decimal(18, 2)]


_CASH_DETAIL = "cast(jsonb_extract_path_text(p.payload, ?) as numeric) = ?"


@pytest.mark.parametrize(
    ("where", "binds", "expected"),
    [
        pytest.param(
            f"p.kind = ? and {_CASH_DETAIL} and exists "
            "(select 1 from payment_document q where q.kind = ?)",
            ["cash", "detail", 25, "card"],
            {2: Decimal(18, 2)},
            id="its-own-scope-tags-the-owner",
        ),
        pytest.param(
            f"{_CASH_DETAIL} and exists (select 1 from payment_document q where q.kind = ?)",
            ["detail", 25, "cash"],
            {},
            id="a-nested-scope-tags-another-row",
        ),
        pytest.param(
            f"p.kind = ? or {_CASH_DETAIL}",
            ["cash", "detail", 25],
            {},
            id="a-disjunct-pins-nothing",
        ),
    ],
)
def test_a_shared_document_is_typed_only_by_a_tag_its_own_row_is_pinned_to(
    where: str, binds: list[object], expected: dict[int, object]
) -> None:
    model = engine.load_case_metamodel(corpus_case("m-inheritance-125"))
    sql = f"select p.id from payment_document p where {where}"
    assert statement_bind_positions(model, sql, binds) == expected


_FLOAT_ARRAYS = (
    "insert into writable_scalars(id, f32, f64) select * from "
    "unnest(cast(? as bigint[]), cast(? as real[]), cast(? as double precision[]))"
)


def test_a_declared_float_column_array_refuses_negative_zero_at_any_element() -> None:
    case = corpus_case("m-core-010")
    golden: list[Any] = [[1, 2], [0.0, 1.5], [2.5, 0.0]]
    assert statement_bind_positions(engine.load_case_metamodel(case), _FLOAT_ARRAYS, golden) == {
        0: Elements(INT64),
        1: Elements(FLOAT32),
        2: Elements(FLOAT64),
    }
    _grade(case, _FLOAT_ARRAYS, golden, copy.deepcopy(golden))
    for column, row in ((1, 0), (2, 1)):
        observed = copy.deepcopy(golden)
        observed[column][row] = -0.0
        with pytest.raises(AssertionError, match=rf"^bind {column}: "):
            _grade(case, _FLOAT_ARRAYS, golden, observed)


def test_a_document_column_array_refuses_a_negative_zero_leaf_in_any_row() -> None:
    case = corpus_case("m-document-codec-016")
    sql = (
        "insert into sample(id, label, profile) select * from "
        "unnest(cast(? as bigint[]), cast(? as text[]), cast(? as jsonb[]))"
    )
    golden: list[Any] = [
        [160, 161],
        ["SignedZero", "Other"],
        [{"ratio": 0.0, "measure": 0.0}, {"ratio": 1.0, "measure": 0.0, "extension": 0.0}],
    ]
    extension_negative = copy.deepcopy(golden)
    extension_negative[2][1]["extension"] = -0.0
    _grade(case, sql, golden, extension_negative)

    leaf_negative = copy.deepcopy(golden)
    leaf_negative[2][1]["measure"] = -0.0
    with pytest.raises(AssertionError, match=r"^bind 2: "):
        _grade(case, sql, golden, leaf_negative)


def test_a_shared_document_column_array_types_each_row_by_its_own_tag() -> None:
    model = engine.load_case_metamodel(corpus_case("m-inheritance-125"))
    sql = (
        "insert into payment_document(id, kind, payload) select * from "
        "unnest(cast(? as bigint[]), cast(? as text[]), cast(? as jsonb[]))"
    )
    binds: list[object] = [
        [10, 11, 12],
        ["card", "cash", "card"],
        [{"detail": "a"}, {"detail": "25.00"}, {"detail": "b"}],
    ]
    documents = statement_bind_positions(model, sql, binds)[2]
    assert isinstance(documents, EachElement)
    assert [cast("Document", document).members["detail"] for document in documents.elements] == [
        STRING,
        Decimal(18, 2),
        STRING,
    ]


@pytest.mark.parametrize(
    ("observed", "golden"),
    [
        pytest.param([1, "a"], [1, "b"], id="a-changed-value"),
        pytest.param(["b", "a"], ["a", "b"], id="binds-reordered"),
        pytest.param([1], [1, 2], id="a-missing-bind"),
        pytest.param([1, 2, 3], [1, 2], id="an-invented-bind"),
        pytest.param([ArrayBind(INT64, [1, 3])], [[1, 2]], id="a-changed-element"),
        pytest.param([ArrayBind(INT64, [1])], [[1, 2]], id="a-missing-element"),
        pytest.param([ArrayBind(INT64, [1])], [1], id="an-array-against-a-scalar"),
    ],
)
def test_compare_binds_alone_refuses_a_bind_the_golden_does_not_state(
    observed: list[object], golden: list[object]
) -> None:
    with pytest.raises(AssertionError):
        compare_binds(observed, golden)


@pytest.mark.parametrize(
    ("observed", "golden"),
    [
        pytest.param([decimal.Decimal("5.00")], [5.00], id="a-decimal-against-its-literal"),
        pytest.param([StructuredDocument({"a": 1})], [{"a": 1}], id="a-document-unwrapped"),
        pytest.param([ArrayBind(INT64, [1, 2])], [[1, 2]], id="an-array-element-by-element"),
        pytest.param(
            [ArrayBind(STRING, ["a", JSON_NULL])], [["a", None]], id="a-json-null-element"
        ),
    ],
)
def test_compare_binds_alone_accepts_an_admitted_second_spelling(
    observed: list[object], golden: list[object]
) -> None:
    compare_binds(observed, golden)


def test_compare_binds_alone_refuses_negative_zero_at_a_declared_float() -> None:
    case, sql, golden = _golden("m-core-010")
    positions = statement_bind_positions(engine.load_case_metamodel(case), sql, golden)
    compare_binds([1, 0.0, 0.0], golden, positions)
    with pytest.raises(AssertionError, match=r"^bind 1: "):
        compare_binds([1, -0.0, 0.0], golden, positions)


def test_assert_wire_binds_alone_refuses_a_changed_value() -> None:
    case, sql, golden = _golden("m-core-010")
    model = engine.load_case_metamodel(case)
    assert_wire_binds(model, sql, golden, list(golden))
    with pytest.raises(AssertionError):
        assert_wire_binds(model, sql, golden, [2, *golden[1:]])


def test_assert_wire_binds_alone_refuses_negative_zero_at_a_declared_float() -> None:
    case, sql, golden = _golden("m-core-010")
    with pytest.raises(AssertionError, match=r"^bind 1: "):
        assert_wire_binds(engine.load_case_metamodel(case), sql, golden, [1, -0.0, 0.0])


def test_assert_wire_binds_refuses_the_other_scale_compare_binds_reconciles() -> None:
    case, sql, golden = _golden("m-temporal-write-002")
    assert golden[2] == "100.00"
    observed: list[object] = [*golden[:2], "100.0", *golden[3:]]
    compare_binds(observed, golden)
    with pytest.raises(AssertionError):
        assert_wire_binds(engine.load_case_metamodel(case), sql, golden, observed)
