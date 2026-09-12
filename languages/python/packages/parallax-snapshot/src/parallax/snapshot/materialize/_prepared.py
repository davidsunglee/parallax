"""One compiled read's prepared half: every level its rows can convert under,
derived once where the read was compiled.

A read lane hands rows here and receives projections. What a row converts under
— the exact Entity's member layout, the position's document contributors, and
the statement's own Attribute contracts — is fixed by the model and the compiled
read together, so it is derived at :func:`bind` and shared by every row of that
read. Nothing about a row decides it; a row only names which of the prepared
levels answers it.

Every Entity the read can resolve gets its level at bind
(``CompiledRead.resolvable``), including the ones no row may ever name: a family
root an unrecognized tag falls back to, and a sibling outside a narrow whose tag
the position still maps. Preparing them all at once is what keeps this state a
property of the compiled read rather than of the rows that arrived — a level
derived on first reach would be a lazy, data-keyed cache whose cost no
preparation figure reports and whose contents depend on which rows came back.

The reference direction is one-way and load-bearing. A prepared read holds its
levels, which hold the catalog's layouts and the statement's contracts; nothing
prepared holds a row, a builder, or a graph, so a read's prepared state outlives
its rows without retaining any of them and one execution's graphs cannot be
reached from the next one's preparation.

This scope may not import `m-sql`, so what a compiled read publishes is read
structurally: :class:`_CompiledRead` is the four members a prepared read needs,
and the row type travels through it rather than being named here, which is what
lets a lane get its own materialized row back from :meth:`PreparedRead.materialize`
without this module knowing the carrier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from parallax.core.base import UnknownFamilyTag
from parallax.core.db_port import Row
from parallax.core.document_codec import DocumentFinding
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity, ValueObjectMetadata
from parallax.snapshot.materialize._convert import (
    AttributeReadContract,
    LevelContext,
    convert_row,
)
from parallax.snapshot.materialize._convert import observable_columns as observed_columns
from parallax.snapshot.materialize._graph import GraphBuilder
from parallax.snapshot.materialize._views import SourceLevel

__all__ = ["PreparedRead", "bind"]


class _MaterializedRow(Protocol):
    """One row a compiled read materialized, as conversion reads it.

    The values it transformed, the exact Entity it resolved, and the provenance
    of what it already judged — which is the whole of what a prepared read needs
    from a row.
    """

    @property
    def values(self) -> dict[str, object]: ...

    @property
    def resolved_entity(self) -> EntityIdentity: ...

    @property
    def findings(self) -> tuple[DocumentFinding, ...]: ...

    @property
    def unknown_family_tag(self) -> UnknownFamilyTag | None: ...

    @property
    def classified_members(self) -> frozenset[str]: ...


class _CompiledRead[RowT: _MaterializedRow](Protocol):
    """What a prepared read reads off the compiled read it is bound to."""

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]: ...

    @property
    def projected_documents(self) -> tuple[ValueObjectMetadata, ...]: ...

    def attribute_reads(self, entity: EntityIdentity) -> tuple[AttributeReadContract, ...]: ...

    def materialize_row(self, row: Row | Mapping[str, object]) -> RowT: ...


@dataclass(frozen=True, slots=True)
class PreparedRead[RowT: _MaterializedRow]:
    """One compiled read together with the levels its rows convert under.

    The whole of what a read lane needs to turn driver rows into projections:
    materialize a row, convert it, and observe it, with no level, contract,
    classified-member set, or finding crossing the call. A lane that named any
    of those would be coordinating a shape it does not own, and would be the
    second place the pairing of a row with its own level could go wrong.

    Both halves it is built from are private for that reason: the level table is
    reachable only through the three methods, so nothing outside can read a level,
    replace one, or hold the compiled read apart from the levels bound with it.
    """

    _compiled: _CompiledRead[RowT]
    _levels: Mapping[EntityIdentity, LevelContext]

    def materialize(self, row: Row | Mapping[str, object]) -> RowT:
        """Resolve one driver row through the read that returned it.

        Kept here rather than left to the compiled read so materializing and
        converting are one interface: the rows a lane converts are the rows this
        prepared read materialized, and no lane holds a compiled read beside a
        prepared one to cross them.
        """
        return self._compiled.materialize_row(row)

    def convert(self, row: RowT, builder: GraphBuilder, *, source: SourceLevel) -> int:
        """Convert one materialized row into ``builder``'s next projection at
        ``source``, answering the projection index the builder assigned."""
        return convert_row(
            row.values,
            self._level(row),
            builder,
            source=source,
            findings=row.findings,
            unknown_family_tag=row.unknown_family_tag,
            classified_members=row.classified_members,
        )

    def observable_columns(self, row: RowT) -> dict[str, object]:
        """One materialized row's observable state, keyed by physical column."""
        return observed_columns(
            row.values, self._level(row), classified_members=row.classified_members
        )

    def _level(self, row: RowT) -> LevelContext:
        """The level ``row``'s own resolved Entity converts under.

        One mapping lookup, and it cannot miss: ``resolvable`` closes the set of
        Entities a row of this read can name, and :func:`bind` derives a level
        for every member of it.
        """
        return self._levels[row.resolved_entity]


def bind[RowT: _MaterializedRow](
    model: CatalogedModel, compiled: _CompiledRead[RowT]
) -> PreparedRead[RowT]:
    """Prepare ``compiled`` against ``model``: one level per Entity it can resolve.

    Paid once per compiled read, which is where the state belongs — the member
    layouts are the model's and the projected documents and Attribute contracts
    are this statement's, and no row of the read can change either.
    """
    return PreparedRead(
        compiled,
        {
            identity: LevelContext(
                model.layouts.entity(identity),
                compiled.projected_documents,
                compiled.attribute_reads(identity),
            )
            for identity in compiled.resolvable
        },
    )
