"""Read Origins retained from judged, Page-owned Entity State written by hand."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout, LayoutCatalog
from parallax.core.metamodel import EntityIdentity, Leaf, MemberShape, Metamodel, Multiplicity
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._retention import (
    ObservationLedger,
    ObservedRows,
    ReadSources,
    deferred_read_sources,
)


@dataclass(frozen=True, slots=True)
class JudgedRows:
    """One Entity's laid-out, judged positional rows, one per projection."""

    layout: EntityLayout
    member_rows: tuple[tuple[object, ...], ...]


def judged_rows(
    model: Metamodel, entity: EntityIdentity, *rows: Mapping[str, object]
) -> JudgedRows:
    """``rows`` as the judged positional state a Page holds for ``entity``.

    A row is keyed by physical storage name, occurrences already decoded to their
    declared shape.
    """
    layout = LayoutCatalog(model).entity(entity)
    return JudgedRows(layout, tuple(_member_row(layout, row) for row in rows))


def retained_sources(
    model: Metamodel,
    judged: JudgedRows,
    *,
    document: object | None = None,
    ledger: ObservationLedger | None = None,
) -> ReadSources:
    """The sources a graph-form read retains for one projection per judged
    row, each admitted with its positional state; ``document`` is the raw
    Structured Column every projection carries."""
    layout, member_rows = judged.layout, judged.member_rows
    entity = layout.concrete
    observations = ObservedRows()
    for node in range(len(member_rows)):
        observations.observe_occurrence(node, entity, document)
    return deferred_read_sources(
        model,
        observations,
        lambda node: (layout, member_rows[node]),
        lambda _node: entity,
        lambda node: member_rows[node][layout.primary_key[0]],
        ledger=ledger,
        pin=Pin(),
    )


def judged_evidence(
    model: Metamodel,
    entity: EntityIdentity,
    *rows: Mapping[str, object],
    document: object | None = None,
    ledger: ObservationLedger | None = None,
) -> ReadSources:
    """The sources a graph-form read retains for one projection per ``rows``
    entry, as :func:`judged_rows` lays them out and :func:`retained_sources`
    admits them."""
    return retained_sources(
        model, judged_rows(model, entity, *rows), document=document, ledger=ledger
    )


def _member_row(layout: EntityLayout, columns: Mapping[str, object]) -> tuple[object, ...]:
    by_declared_name: dict[str, object] = {
        member.name: columns[binding.storage.name]
        for member, binding in zip(
            layout.member_selection.shape.members, layout.member_selection.bindings, strict=True
        )
        if binding.storage.name in columns
    }
    return _positional(layout.member_selection.shape, by_declared_name)


def _positional(shape: MemberShape, document: Mapping[str, object]) -> tuple[object, ...]:
    """``document`` as a Page holds it: one slot per canonical member, absent where
    the document carries no key, nested occurrences positional in turn."""
    row: list[object] = []
    for member in shape.members:
        value = document.get(member.name, ABSENT)
        if isinstance(member, Leaf) or value is None or value is ABSENT:
            row.append(value)
        elif member.multiplicity is Multiplicity.MANY:
            row.append(
                tuple(
                    _positional(member.shape, cast("Mapping[str, object]", element))
                    for element in cast("Sequence[object]", value)
                )
            )
        else:
            row.append(_positional(member.shape, cast("Mapping[str, object]", value)))
    return tuple(row)
