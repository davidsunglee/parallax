"""Reading a model's physical rows back, and grading them against an authored
``then.tableState``.

Every shape that asserts stored state reads it the same way: the whole physical
row of each table, every slot of its compiled layout in order, normalized per
slot so both dialects collapse to the value a case authors. The comparison is
order-insensitive and honours the case's numeric tolerance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._declared_contributor import DeclaredContributor
from .case import Case
from .case_assertions import CaseFailure, rows_equal
from .ddl_builder import declared_contributors, quote_identifier
from .document_codec import decode_stored
from .providers import DatabaseProvider
from .storage_layout import ColumnContributor, ColumnTier, TableLayout

__all__ = ["assert_table_state", "read_table", "read_tables", "table_layout"]


def table_layout(case: Case, table: str) -> TableLayout:
    """The compiled layout of one physical *table* an observation reads back."""
    layout = case.model.storage_layout.table(table)
    if layout is None:
        raise CaseFailure(
            f"{case.path.name}: an observation names table {table!r} "
            f"which the model does not declare."
        )
    return layout


def read_table(
    db: DatabaseProvider,
    layout: TableLayout,
    declarations: Mapping[ColumnContributor, DeclaredContributor],
) -> list[dict[str, Any]]:
    """Read the full state of *layout*'s table, projecting every slot in order.

    The layout is the whole physical row, so a table-per-hierarchy shared table
    reports a sibling-only column as ``null`` rather than omitting it. Each
    slot's own provenance decides its normalization: a document slot is decoded
    to a Python structure (m-value-object), because Postgres returns its
    ``jsonb`` already parsed while MariaDB returns raw JSON text, and both
    dialects must collapse to the same ``dict`` / ``list`` / ``None`` a
    ``then.tableState`` document row is authored as. A ``bytes`` contributor
    reads back as raw driver bytes (Postgres ``memoryview`` / MariaDB
    ``bytes``); it renders to lowercase hex text so a write round-trip compares
    dialect-agnostically to the authored hex string.
    """
    projection = ", ".join(
        f"t0.{quote_identifier(slot.column, db.dialect)}" for slot in layout.columns
    )
    rows = db.query(f"select {projection} from {quote_identifier(layout.table, db.dialect)} t0")
    for row in rows:
        for slot in layout.columns:
            value = row.get(slot.column)
            if slot.tier is ColumnTier.DOCUMENT:
                row[slot.column] = decode_stored(value)
                continue
            declared = declarations.get(slot.contributor)
            if declared is not None:
                row[slot.column] = declared.observed_wire(value)
    return rows


def read_tables(
    case: Case, db: DatabaseProvider, tables: tuple[str, ...]
) -> dict[str, list[dict[str, Any]]]:
    """Every row of each of *tables*, by table name."""
    declarations = declared_contributors(case.model)
    return {table: read_table(db, table_layout(case, table), declarations) for table in tables}


def assert_table_state(case: Case, db: DatabaseProvider, *, after: str) -> None:
    """Assert each table named in ``then.tableState`` holds exactly its rows.

    *after* names what produced the state, for the failure.
    """
    expected = case.expected_table_state
    if not expected:
        return
    actual = read_tables(case, db, tuple(expected))
    for table, expected_rows in expected.items():
        if not rows_equal(actual[table], expected_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: table {table!r} state after {after} "
                f"!= then.tableState.\n"
                f"  actual:   {actual[table]!r}\n"
                f"  expected: {expected_rows!r}"
            )
