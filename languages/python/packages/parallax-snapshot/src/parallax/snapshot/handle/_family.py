from __future__ import annotations

from parallax.core import inheritance, opt_lock, storage_layout, temporal_read
from parallax.core.document_codec import MemberShape
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.temporal_read import TemporalShape
from parallax.snapshot.handle._errors import QueryTargetError

__all__ = [
    "assignment_member",
    "comparison_shape",
    "declaring",
    "entity_layout",
    "entity_of",
    "family_primary_key",
    "family_view",
    "is_temporal",
    "members",
    "temporal_shape",
    "tx_time_axis",
    "version_attribute",
]


def family_view(model: Metamodel, entity: EntityMetadata) -> InheritanceEntityView:
    """``entity``'s compiled Inheritance view: its family root's identity, the
    family key, and its applicable members."""
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise RuntimeError(f"{entity.identity.canonical}: no Inheritance Facet view")
    return view


def temporal_shape(model: Metamodel, entity: EntityMetadata) -> TemporalShape:
    """``entity``'s family Temporal Shape, compiled once for the whole family."""
    shape = temporal_read.view(model).shape(entity.identity)
    if shape is None:  # pragma: no cover - the facet covers every accepted Entity
        raise RuntimeError(f"{entity.identity.canonical}: no Temporal Facet shape")
    return shape


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


def is_temporal(declaring_entity: EntityMetadata) -> bool:
    """Whether ``declaring_entity``'s family is TEMPORAL — whether it declares
    any As-Of Axis at all.

    Temporality is family-wide and root-owned (ADR 0026), so resolve through
    :func:`declaring` first: a descendant declares no axis of its own, and asking
    one directly would answer for a temporal family as though it were not. This
    is the guard the two axis accessors have none of their own — both raise when
    their axis is absent, and a caller that must not raise asks this first."""
    return bool(declaring_entity.declared_as_of_axes)


def tx_time_axis(declaring_entity: EntityMetadata) -> AsOfAxisMetadata:
    """``declaring_entity``'s Transaction-Time as-of axis (its start/end attribute
    references). Temporal axes are family-wide and root-owned, so resolve through
    :func:`declaring` first; raises :class:`ValueError` when the entity declares no
    Transaction-Time dimension (callers guard on a temporal declaring Entity)."""
    axis = declaring_entity.as_of_axis(TemporalDimension.TRANSACTION_TIME)
    if axis is None:  # pragma: no cover - callers guard on a temporal declaring Entity
        raise ValueError(f"{declaring_entity.identity.canonical}: no Transaction-Time axis")
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


def comparison_shape(model: Metamodel, entity: EntityMetadata) -> MemberShape:
    """``entity``'s applicable members as one document shape, for the codec's
    effective-change comparison.

    Every applicable logical member regardless of where its Table puts it: the
    comparison asks what an assignment says about a member's logical value, which
    a Storage Layout cannot change. The Inheritance view retains the one shape
    formed from those members, and returning that exact object keeps both write
    surfaces on one member set without reconstructing it for each comparison.
    """
    return family_view(model, entity).applicable_document_shape


def members(layout: EntityLayoutView) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(row key, is_value_object)`.

    The row key is the name a resolved row carries that member's value under,
    which is the member's own Column name under either layout: a direct
    placement selects that Column, and a document-mapped read fans the shared
    Structured Column back out under the same name (`m-sql`), so one logical
    member is read the same way whichever place the layout put it.

    Membership is ``layout``'s own: every applicable logical member of the
    row-owning Entity, and nothing else. The framework-owned discriminator is
    not a member — a write derives it from the layout's own discriminator
    assignment rather than from row data."""
    return {
        binding.identity.name
        if isinstance(binding, AttributeMetadata)
        else binding.identity.path[-1]: (
            binding.storage.name,
            not isinstance(binding, AttributeMetadata),
        )
        for binding in layout.member_selection.bindings
    }
