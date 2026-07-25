"""The entity scope's own raw-descriptor inheritance-family walk.

Two production seams still need to answer an inheritance-family question
directly from a compiled descriptor record graph, before (or without) it
forms into an accepted Metamodel: class-definition-time family-root
resolution (:func:`~parallax.core.entity.base._derive_inheritance`, deriving
a family subclass's own inherited storage shape) and the narrow-position
fallback a registry chain that cannot form still needs
(:func:`~parallax.core.entity.graph_state._narrow_position`). Kept private
and entity-scope-local rather than shared with the conformance-owned
descriptor-family surface (``parallax.conformance._descriptor_family``),
which the entity support scope may not depend on.
"""

from __future__ import annotations

from parallax.core.descriptor import Entity, Metamodel
from parallax.core.descriptor import declaring_entity as _declaring_entity

__all__ = ["effective_concrete_subtypes", "family_root"]


def _root_name(meta: Metamodel, entity: Entity) -> str | None:
    """The name of ``entity``'s family root, or ``None`` if unresolvable.

    Composes with the shared descriptor-scope ancestry walk
    (:func:`~parallax.core.descriptor.declaring_entity`) rather than
    re-deriving it: the descriptor-level resolver already "resolves to what
    it can reach" for a malformed (cyclic/unresolvable) ancestry, falling
    back to ``entity`` itself, which is never a root — so this only needs to
    check the resolved entity's own role, never re-walk ``parent`` links
    itself.
    """
    if entity.inheritance is None:
        return None
    resolved = _declaring_entity(meta, entity)
    if resolved.inheritance is None or resolved.inheritance.role != "root":
        return None
    return resolved.name


def family_root(meta: Metamodel, entity: Entity) -> Entity:
    """The abstract root of ``entity``'s inheritance family.

    Raises :class:`ValueError` if ``entity`` does not participate, or its
    ancestry does not resolve to a root (a malformed family; the corpus-facing
    raw-descriptor validator, ``parallax.conformance._descriptor_family.validate``,
    is the authority on rejecting those — a class-defined family can never
    reach this malformed shape, since role/parent are derived from the live
    Python class hierarchy rather than separately authored).
    """
    root_name = _root_name(meta, entity)
    if root_name is None:
        raise ValueError(f"{entity.name}: no resolvable inheritance root (m-inheritance)")
    return meta.entity(root_name)


def effective_concrete_subtypes(meta: Metamodel, position: str) -> tuple[str, ...]:
    """The alphabetically-ordered effective concrete-subtype set for ``position``.

    A concrete subtype resolves to itself; an abstract root or subtype
    resolves to all concrete descendants; a plain (non-participant) entity is
    its own trivial set. The order is alphabetical (the corpus's
    effective-set ordering).
    """
    entity = meta.entity(position)
    if entity.inheritance is None:
        return (position,)
    if entity.inheritance.role == "concrete-subtype":
        return (entity.name,)
    return tuple(sorted(_concrete_descendants(meta, entity.name)))


def _concrete_descendants(meta: Metamodel, name: str) -> frozenset[str]:
    """Every concrete-subtype name at or under the family position ``name``,
    walking the compiled parent/child inheritance links."""
    by_name: dict[str, Entity] = {}
    children: dict[str, list[Entity]] = {}
    for candidate in meta.entities:
        if candidate.inheritance is None:
            continue
        by_name[candidate.name] = candidate
        parent = candidate.inheritance.parent
        if parent is not None:
            children.setdefault(parent, []).append(candidate)
    result: set[str] = set()
    stack = [name]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        candidate = by_name.get(current)
        if (
            candidate is not None
            and candidate.inheritance is not None
            and candidate.inheritance.role == "concrete-subtype"
        ):
            result.add(current)
        stack.extend(child.name for child in children.get(current, []))
    return frozenset(result)
