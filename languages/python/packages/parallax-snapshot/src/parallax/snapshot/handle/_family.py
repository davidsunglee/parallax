"""``parallax.snapshot.handle._family`` — the shared family-descriptor leaf.

Every question of the form "what shape does this entity's FAMILY declare?"
answers here off the accepted Metamodel and its facets: the declaring root
(:func:`declaring`), the temporal axes (:func:`tx_time_axis` /
:func:`valid_time_axis`), the optimistic-lock version attribute
(:func:`version_attribute`), and the family-effective primary key
(:func:`family_primary_key`), plus the small ``Class.member`` reference split
(:func:`assignment_member`) that resolves an authored assignment against the
entity's members.

Every PHYSICAL answer instead comes from the Storage Layout Facet, entered
through :func:`entity_layout`: the row-owning Entity's canonical slot selection.
:func:`slot_column`, :func:`axis_columns`, and :func:`members` map a semantically
selected contributor identity onto that layout's slots, so no write-side module
composes a physical column sequence of its own.

This is the package's bottom leaf but one: it imports no handle module except
the dependency-free refusal leaf :mod:`parallax.snapshot.handle._errors`, so
every write-side module (`_keyed_sql`, `_write_lowering`, `_write_inputs`,
`_transaction`, `_predicate_writes`) may import it freely without any risk of a
cycle. Each helper is read from at least two of those, which is precisely why
the module exists — an inheritance participant declares its as-of axes and its
version column on the family ROOT alone (ADR 0026 / ADR 0027), so the lowering
side and the verb-input side must resolve them the SAME way or they disagree
about the shape of the row they are writing.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores
(an underscored name imported across a module boundary is a Pyright strict
``reportPrivateUsage`` error, and this leaf exists only to be imported).
Mirrors :mod:`parallax.core.entity._annotations`.
"""

from __future__ import annotations

from parallax.core import inheritance, opt_lock, storage_layout
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    TemporalDimension,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.storage_layout import ColumnContributor, EntityLayoutView
from parallax.snapshot.handle._errors import QueryTargetError

__all__ = [
    "assignment_member",
    "axis_columns",
    "declaring",
    "entity_layout",
    "entity_of",
    "family_primary_key",
    "members",
    "slot_column",
    "tx_time_axis",
    "valid_time_axis",
    "version_attribute",
]


def family_primary_key(model: Metamodel, entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """``entity``'s FAMILY-EFFECTIVE primary key (`m-inheritance` "Inherited
    members"): the primary-key Attributes of its applicable-member chain, so an
    inherited key resolves at the ancestor that declares it."""
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return ()
    return tuple(
        attribute
        for attribute in view.applicable_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def entity_of(model: Metamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a write's bare-or-canonical target spelling names.

    The write-lowering group resolves within the accepted model itself (it holds
    no descriptor record graph and no entity-scope seam): a write target is an
    unambiguous declared name, resolved by
    :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting
    bare-or-canonical rule. Raises :class:`QueryTargetError` when the connected
    model declares no such Entity — the same refusal a read's preflight answers
    with, because it is the same failure."""
    entity = entity_by_name(model, name)
    if entity is None:
        raise QueryTargetError(
            "the connected model declares no Entity for this write's target "
            "(query-target-not-in-model)"
        )
    return entity


def declaring(model: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    """The accepted Metadata that DECLARES ``entity``'s family facts — its family
    root, itself for a standalone Entity.

    Temporality, the version column, and the physical primary key are family-wide
    and root-owned (`m-inheritance` "Inherited members"), so every write-side
    family fact resolves through this rather than through a possibly-empty local
    declaration."""
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity
    root = model.entity(position.root)
    return entity if root is None else root


def tx_time_axis(declaring_entity: EntityMetadata) -> AsOfAxisMetadata:
    """``declaring_entity``'s Transaction-Time as-of axis (its start/end attribute
    references). Temporal axes are family-wide and root-owned, so resolve through
    :func:`declaring` first; raises :class:`ValueError` when the entity declares no
    Transaction-Time dimension (callers guard on a temporal declaring Entity)."""
    axis = declaring_entity.as_of_axis(TemporalDimension.TRANSACTION_TIME)
    if axis is None:  # pragma: no cover - callers guard on a temporal declaring Entity
        raise ValueError(f"{declaring_entity.identity.canonical}: no Transaction-Time axis")
    return axis


def valid_time_axis(declaring_entity: EntityMetadata) -> AsOfAxisMetadata:
    """``declaring_entity``'s Valid-Time as-of axis (its start/end attribute
    references). Family-wide and root-owned like every axis, so resolve through
    :func:`declaring` first; raises :class:`ValueError` when the entity declares no
    Valid-Time dimension (callers guard on a Bitemporal declaring Entity)."""
    axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
    if axis is None:  # pragma: no cover - callers guard on a Bitemporal declaring Entity
        raise ValueError(f"{declaring_entity.identity.canonical}: no Valid-Time axis")
    return axis


def entity_layout(model: Metamodel, entity: EntityMetadata) -> EntityLayoutView | None:
    """``entity``'s canonical selection over its physical Table Layout, or
    ``None`` when it owns no rows (an abstract family position, or an Entity the
    model maps to no Table).

    This is the write side's only physical-shape entry point: the view's slots
    already carry Table order, the applicable member set, and the derived
    table-per-hierarchy discriminator assignment, so nothing downstream
    reassembles a column sequence from declarations."""
    return storage_layout.view(model).entity(entity.identity)


def slot_column(layout: EntityLayoutView, contributor: ColumnContributor) -> str:
    """The physical Column ``contributor`` occupies in ``layout``'s Table.

    An operation selects its identities semantically — model primary key,
    version attribute, temporal bound — and maps each one here. Raises
    :class:`ValueError` when the Table Layout retains no slot for it."""
    slot = layout.layout.contribution(contributor)
    if slot is None:  # pragma: no cover - a selected contributor always has a slot
        raise ValueError(f"{layout.entity.canonical}: {contributor} occupies no physical Column")
    return slot.column.name


def axis_columns(layout: EntityLayoutView, axis: AsOfAxisMetadata) -> tuple[str, str]:
    """The physical ``(start, end)`` Columns ``axis``'s bound Attributes occupy in
    ``layout``'s Table — the interval bounds a temporal write reads and stamps.

    Temporal axes are family-wide and root-owned, so the bound Attributes are
    declared on the root while their slots live in the row-owning Entity's own
    Table."""
    return slot_column(layout, axis.start_attribute), slot_column(layout, axis.end_attribute)


def version_attribute(
    model: Metamodel, declaring_entity: EntityMetadata
) -> AttributeMetadata | None:
    """``declaring_entity``'s family version attribute, if any.

    The Optimistic Lock Facet names the version column by Identity for a family
    whose root declares one (`m-opt-lock` "The version column"; ADR 0027), and it
    is family-uniform, so resolving through the declaring root's own local lookup
    recovers the accepted Attribute Metadata."""
    key = opt_lock.view(model).key(declaring_entity.identity)
    if not isinstance(key, opt_lock.ExplicitVersion):
        return None
    return declaring_entity.attribute(key.attribute.name)


def assignment_member(attr: str) -> str:
    """The declared member name of an assignment's ``Class.member`` reference."""
    _, _, member = attr.rpartition(".")
    return member


def members(layout: EntityLayoutView) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(column, is_value_object)` over
    ``layout``'s applicable slots.

    The framework-owned discriminator slot is not a member: a write derives it
    from the layout's own discriminator assignment rather than from row data."""
    resolved: dict[str, tuple[str, bool]] = {}
    for slot in layout.columns:
        contributor = slot.contributor
        if isinstance(contributor, AttributeIdentity):
            resolved[contributor.name] = (slot.column.name, False)
        elif isinstance(contributor, ValueObjectIdentity):
            resolved[contributor.path[-1]] = (slot.column.name, True)
    return resolved
