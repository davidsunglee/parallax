"""The canonical physical column order of an Entity's table (m-inheritance).

Column order is a declaration fact — the Metamodel already carries every column
an Attribute or Value Object contributes — but the order a physical table
actually has is FAMILY-EFFECTIVE, because an inheritance participant declares
only its local members while its table also carries every ancestor's. Stating
the law therefore requires the family-effective chain, which is this module's
scope alone.

This scope is also the only one that contributes a physical column the Metamodel
does not otherwise carry: the table-per-hierarchy tag, a bare string on the
strategy with no Attribute behind it. Should a future feature ever synthesize a
physical column that is likewise backed by no declared Attribute, that feature's
owner becomes a co-owner of this law and the single-owner answer needs
revisiting.
"""

from __future__ import annotations

from parallax.core.inheritance._facet import InheritanceFacet
from parallax.core.metamodel import EntityMetadata, PrimaryKey

__all__ = ["column_order"]


def column_order(entity: EntityMetadata, facet: InheritanceFacet) -> tuple[str, ...]:
    """``entity``'s physical columns in canonical order.

    Primary-key columns first, then the table-per-hierarchy tag column (the
    framework-owned tag is slotted immediately after the primary key), then the
    remaining scalar columns in declaration order, and finally each value
    object's single backing document column in declaration order
    (`m-value-object`: the document column is positional, after the scalars).

    The order is taken from the position's applicable member chain — root first,
    each contributor's members in declaration order — so an inherited member,
    the primary key among them, appears at the ancestor's position rather than
    the participant's. A standalone Entity's chain is itself alone, so the two
    cases need no separate spellings.
    """
    view = facet.entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    keys: list[str] = []
    rest: list[str] = []
    for attribute in view.applicable_attributes:
        target = keys if isinstance(attribute.primary_key, PrimaryKey) else rest
        target.append(attribute.storage.name)
    tag = [] if view.tag_column is None else [view.tag_column]
    documents = [member.storage.name for member in view.applicable_value_objects]
    return (*keys, *tag, *rest, *documents)
