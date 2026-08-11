"""Canonical builders for composed Predicate values."""

from __future__ import annotations

from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.predicate._nodes import NavigationPath, PathSegment, SubtypeSelection

__all__ = ["_canonical_includes"]


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
    segment: PathSegment,
) -> tuple[tuple[str, str], str, tuple[int, tuple[tuple[str, str], ...]]]:
    relationship = _relationship_identity(segment.rel)
    return (
        relationship.source_entity.sort_key,
        relationship.name,
        _selection_key(segment.narrow if segment.narrow else None),
    )


def _path_key(
    path: NavigationPath,
) -> tuple[
    tuple[tuple[tuple[str, str], str, tuple[int, tuple[tuple[str, str], ...]]], ...],
    tuple[int, tuple[tuple[str, str], ...]],
]:
    return tuple(_segment_key(segment) for segment in path.segments), _selection_key(path.narrow)


def _is_redundant_prefix(path: NavigationPath, extension: NavigationPath) -> bool:
    return (
        path.narrow == extension.narrow
        and len(path.segments) < len(extension.segments)
        and extension.segments[: len(path.segments)] == path.segments
    )


def _canonical_includes(paths: tuple[NavigationPath, ...]) -> tuple[NavigationPath, ...]:
    """Return the maximal, deduplicated include-path set in canonical order."""
    unique = frozenset(paths)
    maximal = (
        path
        for path in unique
        if not any(_is_redundant_prefix(path, extension) for extension in unique)
    )
    return tuple(sorted(maximal, key=_path_key))
