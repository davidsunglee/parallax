"""The physical table a parsed SQL table reference names.

Golden and naive SQL name every table as the case binding places it, so a
grading seam reading a statement's tables compares the reference's qualifier
and local name with a resolved :class:`~.database_binding.PhysicalTable`
rather than with a declared name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlglot import exp

from .database_binding import PhysicalTable

if TYPE_CHECKING:
    from .case import Case
    from .storage_layout import TableLayout

__all__ = ["physical_table_of", "referenced_layout"]


def _component(identifier: Any) -> str:
    if isinstance(identifier, exp.Identifier):
        return identifier.name if identifier.quoted else identifier.name.lower()
    return str(identifier.name).lower()


def physical_table_of(table: exp.Table) -> PhysicalTable:
    """The qualifier components and local name *table* spells, an unquoted
    component folded to lowercase."""
    qualifier = tuple(
        _component(part) for part in (table.args.get("catalog"), table.args.get("db")) if part
    )
    return PhysicalTable(qualifier, _component(table.this))


def referenced_layout(case: Case, table: exp.Table, dialect: str) -> TableLayout | None:
    """The layout of the mapping owner *dialect*'s case binding places where
    *table* points, or absent where it names no table of the case's model."""
    return case.placed_layout(physical_table_of(table), dialect)
