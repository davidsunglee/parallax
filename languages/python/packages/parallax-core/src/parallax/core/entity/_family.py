"""The entity scope's own raw-descriptor inheritance-family reads.

Two production seams still need to answer an inheritance-family question
directly from a compiled descriptor record graph, before (or without) it
forms into an accepted Metamodel: class-definition-time family-root
resolution (:func:`~parallax.core.entity.base._derive_inheritance`, deriving
a family subclass's own inherited storage shape) and the narrow-position
fallback a registry chain that cannot form still needs
(:func:`~parallax.core.entity.graph_state._narrow_position`). Both compose
with the descriptor scope's own structural walks rather than re-deriving
them, so this scope and the conformance engine's raw-descriptor seams can
never answer the same structural question differently.
"""

from __future__ import annotations

from parallax.core.descriptor import Entity, Metamodel, concrete_descendant_names, family_root_name

__all__ = ["effective_concrete_subtypes", "family_root"]


def family_root(meta: Metamodel, entity: Entity) -> Entity:
    """The abstract root of ``entity``'s inheritance family.

    Raises :class:`ValueError` if ``entity`` does not participate, or its
    ancestry does not resolve to a root (a malformed family; the corpus-facing
    raw-descriptor validator, ``parallax.conformance._descriptor_family.validate``,
    is the authority on rejecting those — a class-defined family can never
    reach this malformed shape, since role/parent are derived from the live
    Python class hierarchy rather than separately authored).
    """
    root_name = family_root_name(meta, entity)
    if root_name is None:
        raise ValueError(f"{entity.name}: no resolvable inheritance root (m-inheritance)")
    return meta.entity(root_name)


def effective_concrete_subtypes(meta: Metamodel, position: str) -> tuple[str, ...]:
    """The alphabetically-ordered effective concrete-subtype set for ``position``.

    Every concrete node at or below the position (`m-inheritance`), so a
    concrete subtype resolves to itself plus any concrete node declared below
    it; a plain non-participant is its own trivial set. Agrees by construction
    with the Inheritance Facet's ``concrete_subtypes`` for the same position —
    a narrowed relationship view is keyed by this set, and a read that keys it
    through the facet must derive the same key this fallback does.
    """
    entity = meta.entity(position)
    if entity.inheritance is None:
        return (position,)
    return tuple(sorted(concrete_descendant_names(meta, entity.name)))
