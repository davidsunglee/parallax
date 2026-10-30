"""DB-free tests for how the harness reads a PostgreSQL grouped effect.

A grouped effect (`m-sql` *Grouped effects*) is one ``update … from unnest(…) with
ordinality v(…) … returning v.ord`` or ``delete … using unnest(…) …`` statement
applying one keyed effect per source row. These tests pin, without a database,
that the harness reads such a golden back as the lone statements it applies,
types each source array by the column or document path it reaches, refuses a
malformed source or result, binds each document path value as JSON, and leaves
every other statement alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from reference_harness._grouped_effects import (
    GroupedEffectShapeError,
    sourced_path_value_indices,
    ungrouped_effect,
)
from reference_harness._sql_placeholders import array_bind_indices
from reference_harness._statement_bind_inference import (
    array_cast_mismatches,
    infer_statement_bind_targets,
)
from reference_harness.case import Case, load_model
from reference_harness.providers.postgres import _statement_binds as postgres_statement_binds
from reference_harness.storage_layout import DocumentMember

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"

_WALLET = (
    "update wallet t set balance = v.c2 from unnest(cast(? as bigint[]), cast(? as decimal[])) "
    "with ordinality v(c1, c2, ord) where t.id = v.c1 returning v.ord"
)
_DOCUMENT = (
    "update tag_ledger t set payload = jsonb_set(jsonb_set(t.payload, ?, v.c4), ?, v.c5), "
    "version = v.c3 from unnest(cast(? as bigint[]), cast(? as int[]), cast(? as int[]), "
    "cast(? as jsonb[]), cast(? as jsonb[])) with ordinality v(c1, c2, c3, c4, c5, ord) "
    "where t.id = v.c1 and t.version = v.c2 returning v.ord"
)
_DOCUMENT_BINDS: list[object] = [
    "{label}",
    "{tags}",
    [1, 2],
    [1, 4],
    [2, 5],
    ["a", None],
    [["c"], []],
]


def _case(model: str) -> Case:
    return Case(
        Path("synthetic.yaml"),
        {"model": f"models/{model}.yaml", "shape": "writeSequence"},
        load_model(_COMPATIBILITY_ROOT, f"models/{model}.yaml"),
    )


def test_a_grouped_effect_reads_back_as_the_lone_updates_it_applies() -> None:
    assert ungrouped_effect(_WALLET, [[1, 2], ["111.00", "222.00"]]) == [
        ("update wallet set balance = ? where id = ?", ["111.00", 1]),
        ("update wallet set balance = ? where id = ?", ["222.00", 2]),
    ]


def test_document_paths_keep_their_shared_binds_beside_each_rows_values() -> None:
    lone = (
        "update tag_ledger set payload = jsonb_set(jsonb_set(payload, ?, cast(? as jsonb)), "
        "?, cast(? as jsonb)), version = ? where id = ? and version = ?"
    )
    assert ungrouped_effect(_DOCUMENT, _DOCUMENT_BINDS) == [
        (lone, ["{label}", "a", "{tags}", ["c"], 2, 1, 1]),
        (lone, ["{label}", None, "{tags}", [], 5, 2, 4]),
    ]


_CLOSE = (
    "update coverage_span t set out_z = v.c3 from unnest(cast(? as bigint[]), "
    "cast(? as timestamptz[]), cast(? as timestamptz[])) with ordinality v(c1, c2, c3, ord) "
    "where t.id = v.c1 and t.thru_z = v.c2 and t.out_z = ? returning v.ord"
)
_CLOSE_BINDS: list[object] = [
    [1, 2],
    ["2024-06-01T00:00:00.000000Z", "infinity"],
    ["2024-10-01T00:00:00.000000Z", "2024-10-01T00:00:00.000000Z"],
    "infinity",
]


def test_a_grouped_delete_reads_back_as_the_lone_deletes_it_applies() -> None:
    statement = (
        "delete from account t using unnest(cast(? as bigint[]), cast(? as int[])) with "
        "ordinality v(c1, c2, ord) where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    assert ungrouped_effect(statement, [[1, 2], [1, 4]]) == [
        ("delete from account where id = ? and version = ?", [1, 1]),
        ("delete from account where id = ? and version = ?", [2, 4]),
    ]


def test_a_grouped_close_reads_back_as_each_milestones_lone_close() -> None:
    lone = "update coverage_span set out_z = ? where id = ? and thru_z = ? and out_z = ?"
    assert ungrouped_effect(_CLOSE, _CLOSE_BINDS) == [
        (lone, ["2024-10-01T00:00:00.000000Z", 1, "2024-06-01T00:00:00.000000Z", "infinity"]),
        (lone, ["2024-10-01T00:00:00.000000Z", 2, "infinity", "infinity"]),
    ]


def test_a_grouped_guard_reads_back_as_its_self_assigning_lone_guard() -> None:
    statement = (
        "update balance t set in_z = t.in_z from unnest(cast(? as bigint[]), "
        "cast(? as timestamptz[])) with ordinality v(c1, c2, ord) where t.bal_id = v.c1 "
        "and t.out_z = ? and t.in_z = v.c2 returning v.ord"
    )
    rows = ungrouped_effect(statement, [[1], ["2024-01-01T00:00:00.000000Z"], "infinity"])
    assert rows == [
        (
            "update balance set in_z = in_z where bal_id = ? and out_z = ? and in_z = ?",
            [1, "infinity", "2024-01-01T00:00:00.000000Z"],
        )
    ]


def test_each_milestone_source_array_is_typed_by_the_column_it_addresses() -> None:
    case = _case("shared-coverage-layout-twin-columns")
    targets = infer_statement_bind_targets(case, _CLOSE, _CLOSE_BINDS, "postgres")
    assert {index: getattr(targets[index], "column", None) for index in (0, 1, 2)} == {
        0: "id",
        1: "thru_z",
        2: "out_z",
    }
    assert array_cast_mismatches(case, _CLOSE, _CLOSE_BINDS) == ()
    narrowed = _CLOSE.replace(
        "cast(? as timestamptz[]), cast(? as timestamptz[])",
        "cast(? as timestamptz[]), cast(? as date[])",
    )
    (mismatch,) = array_cast_mismatches(case, narrowed, _CLOSE_BINDS)
    assert (mismatch.index, mismatch.expected, mismatch.column) == (2, "timestamptz", "out_z")


def test_a_grouped_delete_source_is_typed_by_the_column_it_compares() -> None:
    case = _case("account")
    statement = (
        "delete from account t using unnest(cast(? as int[]), cast(? as int[])) with "
        "ordinality v(c1, c2, ord) where t.id = v.c1 and t.version = v.c2 returning v.ord"
    )
    (mismatch,) = array_cast_mismatches(case, statement, [[1, 2], [1, 4]])
    assert (mismatch.index, mismatch.expected, mismatch.column) == (0, "bigint", "id")


def test_a_shared_tag_guard_binds_once_for_every_row() -> None:
    statement = (
        "update payment t set amount = v.c2 from unnest(cast(? as bigint[]), "
        "cast(? as decimal[])) with ordinality v(c1, c2, ord) where t.id = v.c1 "
        "and t.kind = ? returning v.ord"
    )
    rows = ungrouped_effect(statement, [[1, 2], ["5.00", "6.00"], "card"])
    assert rows is not None
    assert [binds for _, binds in rows] == [["5.00", 1, "card"], ["6.00", 2, "card"]]
    assert rows[0][0] == "update payment set amount = ? where id = ? and kind = ?"


@pytest.mark.parametrize(
    "statement",
    [
        "update wallet set balance = ? where id = ?",
        "insert into wallet(id) select * from unnest(cast(? as bigint[]))",
        "delete from wallet where id in (?, ?)",
        "delete from wallet where id = ?",
    ],
)
def test_any_other_statement_is_left_alone(statement: str) -> None:
    assert ungrouped_effect(statement, [1, 2]) is None
    assert sourced_path_value_indices(statement) == frozenset()


@pytest.mark.parametrize(
    ("statement", "binds", "problem"),
    [
        pytest.param(_WALLET, [[1, 2], ["1.00"]], "unequal lengths", id="unequal-arrays"),
        pytest.param(_WALLET, [[1, 2], "1.00"], "no array", id="scalar-source"),
        pytest.param(
            _WALLET.replace("returning v.ord", "returning t.id"),
            [[1], ["1.00"]],
            "returns something other",
            id="returns-a-key",
        ),
        pytest.param(
            _WALLET.replace(" with ordinality", ""),
            [[1], ["1.00"]],
            "without an alias and ordinality",
            id="no-ordinality",
        ),
    ],
)
def test_a_malformed_grouped_effect_is_refused(
    statement: str, binds: list[object], problem: str
) -> None:
    with pytest.raises(GroupedEffectShapeError, match=problem):
        ungrouped_effect(statement, binds)


def test_each_source_array_is_typed_by_the_column_or_path_it_reaches() -> None:
    case = _case("scalar-collection-lifecycle-layout-twin-document")
    targets = infer_statement_bind_targets(case, _DOCUMENT, _DOCUMENT_BINDS, "postgres")
    assert sorted(array_bind_indices(_DOCUMENT)) == [2, 3, 4, 5, 6]
    assert {index: getattr(targets[index], "column", None) for index in (2, 3, 4)} == {
        2: "id",
        3: "version",
        4: "version",
    }
    assert [targets[index] for index in (5, 6)] == [
        member
        for member in case.model.storage_layout.document("parallax.compatibility.TagLedger").members
        if member.path in (("label",), ("tags",))
    ]
    assert all(isinstance(targets[index], DocumentMember) for index in (5, 6))
    assert array_cast_mismatches(case, _DOCUMENT, _DOCUMENT_BINDS) == ()


def test_a_source_array_cast_to_another_type_than_its_column_is_refused() -> None:
    case = _case("wallet")
    narrowed = _WALLET.replace("cast(? as bigint[])", "cast(? as int[])")
    (mismatch,) = array_cast_mismatches(case, narrowed, [[1, 2], ["1.00", "2.00"]])
    assert (mismatch.index, mismatch.cast, mismatch.expected, mismatch.column) == (
        0,
        "int",
        "bigint",
        "id",
    )


def test_a_path_value_array_binds_every_element_as_json_null_included() -> None:
    assert sourced_path_value_indices(_DOCUMENT) == frozenset({5, 6})
    bound = postgres_statement_binds(_DOCUMENT, _DOCUMENT_BINDS)
    for index in (5, 6):
        elements = bound[index]
        assert isinstance(elements, list)
        assert all(isinstance(element, Jsonb) for element in elements)
    assert [element.obj for element in bound[5]] == ["a", None]
