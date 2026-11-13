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
from .storage_layout import observed_table

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


def referenced_layout(case: Case, table: exp.Table) -> TableLayout | None:
    """The layout of the mapping owner the case binding places where *table*
    points, or absent where it names no table of the case's model.

    Read through :attr:`~.case.Case.state_placement`, the placement every
    dialect of the case shares.
    """
    return observed_table(case.model.storage_layout, case.state_placement, physical_table_of(table))
