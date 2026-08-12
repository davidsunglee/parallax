"""Model-free canonicalization of an Object Query's set-valued clauses.

Every path into an :class:`~parallax.core.object_query._nodes.ObjectQueryNode`
goes through :func:`object_query`: the fluent clause methods, ``deserialize``,
and the class-less neutral constructor. Canonicalization is idempotent, so a
clause method that rebuilds the node re-canonicalizes harmlessly.

The rules here need no model — Subtype Selection ordering and the Includes
maximal-set fixed point are decided from the document alone. Everything that
needs a model (a selection's effective set, a hop's relationship target, a
declared temporal dimension) is a preflight rule instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.object_query._nodes import (
    IncludePath,
    IncludeSegment,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
)
from parallax.core.predicate import PredicateNode, SubtypeSelection, canonical_subtype_selection

__all__ = ["canonical_includes", "object_query", "subtype_spelling"]


def subtype_spelling(subtype: type) -> str:
    """The Subtype Selection alternative an Entity Class contributes.

    Read off the class rather than resolved through the frontend's declaration
    engine: a Subtype Selection alternative is a SPELLING, and every declared
    Entity Class already answers its own canonical one. A class carrying no
    declared identity contributes its own name, which resolution then refuses at
    preflight rather than here.
    """
    identity = getattr(subtype, "identity", None)
    canonical = getattr(identity, "canonical", None)
    return canonical if isinstance(canonical, str) else subtype.__name__


def object_query(
    target: EntityIdentity,
    predicate: PredicateNode,
    *,
    narrow_to: SubtypeSelection | None = None,
    temporal: Mapping[TemporalDimension, TemporalSelection] | None = None,
    order_by: tuple[OrderKey, ...] = (),
    limit: int | None = None,
    includes: tuple[IncludePath, ...] = (),
) -> ObjectQueryNode:
    """Build the canonical Object Query for these clause values."""
    return ObjectQueryNode(
        target=target,
        predicate=predicate,
        narrow_to=None if narrow_to is None else canonical_subtype_selection(narrow_to),
        temporal=MappingProxyType(dict(temporal or {})),
        order_by=order_by,
        limit=limit,
        includes=canonical_includes(includes),
    )


def _entity_identity(spelling: str) -> EntityIdentity:
    namespace, separator, name = spelling.rpartition(".")
    return EntityIdentity(namespace if separator else None, name if separator else spelling)


def _relationship_identity(spelling: str) -> RelationshipIdentity:
    entity, _, relationship = spelling.rpartition(".")
    return RelationshipIdentity(_entity_identity(entity), relationship)


def _selection_key(selection: SubtypeSelection | None) -> tuple[int, tuple[tuple[str, str], ...]]:
    if selection is None:
        return (0, ())
    return (1, tuple(_entity_identity(spelling).sort_key for spelling in selection))


def _segment_key(
    segment: IncludeSegment,
) -> tuple[tuple[str, str], str, tuple[int, tuple[tuple[str, str], ...]]]:
    relationship = _relationship_identity(segment.rel)
    return (
        relationship.source_entity.sort_key,
        relationship.name,
        _selection_key(segment.narrow_to if segment.narrow_to else None),
    )


def _path_key(
    path: IncludePath,
) -> tuple[
    tuple[tuple[tuple[str, str], str, tuple[int, tuple[tuple[str, str], ...]]], ...],
    tuple[int, tuple[tuple[str, str], ...]],
]:
    return tuple(_segment_key(segment) for segment in path.segments), _selection_key(
        path.applies_to
    )


def _is_redundant_prefix(path: IncludePath, extension: IncludePath) -> bool:
    return (
        path.applies_to == extension.applies_to
        and len(path.segments) < len(extension.segments)
        and extension.segments[: len(path.segments)] == path.segments
    )


def canonical_includes(paths: tuple[IncludePath, ...]) -> tuple[IncludePath, ...]:
    """Return the maximal, deduplicated Include Path set in canonical order."""
    unique = frozenset(paths)
    maximal = (
        path
        for path in unique
        if not any(_is_redundant_prefix(path, extension) for extension in unique)
    )
    return tuple(sorted(maximal, key=_path_key))
