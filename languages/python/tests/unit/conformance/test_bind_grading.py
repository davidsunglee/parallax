"""Golden bind grading at declared float positions (`m-case-format` *Canonical
literal oracles*).

A declared ``float32``/``float64`` position — a scalar Column or a Value Object
leaf — distinguishes ``-0.0`` from the canonical ``0.0``; a Json position, here a
document key the declaration does not name, keeps JSON-value equality. The
positions are read off each case's own golden statement and model.
"""

from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from parallax.conformance import case_format, engine
from parallax.core.base import FLOAT32, FLOAT64, INT64, STRING, Decimal
from tests._support.bind_positions import Document, statement_bind_positions
from tests._support.corpus import case_document, compare_binds
from tests._support.sweep_goldens import assert_wire_binds, write_golden_statements

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _golden(case_id: str, index: int = 0) -> tuple[case_format.Case, str, list[Any]]:
    case = _CASES[case_id]
    sql, binds = write_golden_statements(case)[index]
    return case, sql, binds


def _read_statement(case_id: str) -> tuple[case_format.Case, str, list[Any]]:
    """A read case's one Postgres golden statement."""
    case = _CASES[case_id]
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
    case = _CASES["m-inheritance-125"]
    model = engine.load_case_metamodel(case)
    details: list[object] = []
    for sql, binds in write_golden_statements(case):
        document = statement_bind_positions(model, sql, binds)[2]
        assert isinstance(document, Document)
        details.append(document.members["detail"])
    assert details == [STRING, Decimal(18, 2)]
