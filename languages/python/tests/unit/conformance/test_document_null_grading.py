"""Golden ``null`` grading at whole document Columns (`m-value-object`): such a
``null`` states SQL NULL, so a bind of the literal JSON null document fails
there, while a document path assignment's JSON null is not a whole Column."""

from __future__ import annotations

from typing import Any

import pytest

from parallax.conformance import case_format, engine
from parallax.core.base import INT64, JSON, STRING
from parallax.core.db_port import JSON_NULL, ArrayBind, JsonDocument
from tests._support.bind_positions import assert_document_nulls, whole_document_binds
from tests._support.case_corpus import case as corpus_case
from tests._support.sweep_goldens import write_golden_statements

_ROW_302: dict[str, object] = {"street": "2 Birch Rd", "city": None, "geo": None, "phones": []}


def _golden(case_id: str, index: int) -> tuple[case_format.Case, str, list[Any]]:
    case = corpus_case(case_id)
    sql, binds = write_golden_statements(case)[index]
    return case, sql, binds


def _grade(case: case_format.Case, sql: str, golden: list[Any], observed: list[Any]) -> None:
    assert_document_nulls(engine.load_case_metamodel(case), sql, observed, golden)


def test_a_single_row_insert_of_a_null_value_object_binds_sql_null() -> None:
    case, sql, golden = _golden("m-value-object-076", 0)
    assert golden == [300, "Ari", None]
    _grade(case, sql, golden, [300, "Ari", None])
    with pytest.raises(AssertionError, match=r"^bind 2: "):
        _grade(case, sql, golden, [300, "Ari", JsonDocument(None)])


def test_an_amend_to_a_null_value_object_binds_sql_null() -> None:
    case, sql, golden = _golden("m-value-object-078", 1)
    assert golden == [None, 304]
    _grade(case, sql, golden, [None, 304])
    with pytest.raises(AssertionError, match=r"^bind 0: "):
        _grade(case, sql, golden, [JsonDocument(None), 304])


def test_a_column_array_holds_sql_null_for_each_null_value_object() -> None:
    case, sql, golden = _golden("m-value-object-077", 0)
    ids = ArrayBind(INT64, [301, 302, 303])
    names = ArrayBind(STRING, ["Bea", "Cai", "Dag"])
    _grade(case, sql, golden, [ids, names, ArrayBind(JSON, [None, _ROW_302, None])])
    for row in (0, 2):
        values: list[object] = [None, _ROW_302, None]
        values[row] = JSON_NULL
        with pytest.raises(AssertionError, match=rf"^bind 2\[{row}\]: "):
            _grade(case, sql, golden, [ids, names, ArrayBind(JSON, values)])


def test_a_document_path_assignment_of_json_null_is_not_a_whole_column() -> None:
    case, sql, golden = _golden("m-batch-write-054", 0)
    assert whole_document_binds(engine.load_case_metamodel(case), sql) == {}
    _grade(case, sql, golden, [*golden[:5], "null", *golden[6:]])


def test_a_shared_structured_column_insert_writes_its_whole_document() -> None:
    case, sql, _golden_binds = _golden("m-storage-layout-022", 0)
    assert whole_document_binds(engine.load_case_metamodel(case), sql) == {1: False}
