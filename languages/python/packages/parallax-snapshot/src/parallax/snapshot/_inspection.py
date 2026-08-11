"""The Snapshot lifecycle's own node-inspection surface (spec §3).

``is_view_loaded`` / ``view`` / ``pin_of`` / ``edge_of`` answer questions about a
node **this lifecycle produced**, which is why they live here rather than on the
package owning the lifecycle-neutral :class:`~parallax.core.temporal_read.Pin`
and :class:`~parallax.core.temporal_read.Edge` values. Every one of them first
requires the private :class:`SnapshotNodeState` the materializer's state factory
attached: a plain instance, or one a different lifecycle produced, is refused as
``snapshot-node-required`` before any path, relationship, or temporal validation,
so a wrong-lifecycle argument never answers ``False`` and never surfaces as an
unrelated failure. An Edited Copy of such a node answers here exactly as the node
does, because an edit preserves the state this module reads; provenance, not
editedness, is what these operations turn on.

The two relationship operations take only a class-derived Relationship Path. A
bare name string is not accepted: the path is what carries the starting owner the
node must satisfy and the per-segment narrowing that selects a distinct view, and
neither survives a string.

``SnapshotNodeState`` is the whole of what the Snapshot slice attaches to a node,
and Entity never interprets it — it occupies the one opaque lifecycle slot that
:func:`~parallax.core.entity.lifecycle_state_of` reads back.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core.entity import UNLOADED, RelationshipPath, UnloadedRelationshipError
from parallax.core.entity import lifecycle_state_of as _lifecycle_state_of
from parallax.core.entity import relationship_value_of as _relationship_value_of
from parallax.core.entity._declaration import declaration_of, is_entity_class, members_of
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.predicate import PathSegment
from parallax.core.temporal_read import Edge, Pin

__all__ = [
    "SNAPSHOT_INSPECTION_CODES",
    "SnapshotInspectionError",
    "SnapshotNodeState",
    "edge_of",
    "is_view_loaded",
    "pin_of",
    "snapshot_state_of",
    "view",
]

SNAPSHOT_INSPECTION_CODES: Final[frozenset[str]] = frozenset(
    {
        "snapshot-node-required",
        "snapshot-view-owner-mismatch",
        "snapshot-pin-unavailable",
        "snapshot-edge-unavailable",
    }
)
"""The complete Snapshot-inspection refusal vocabulary."""


class SnapshotInspectionError(RuntimeError):
    """An inspection operation was asked something this node cannot answer.

    A ``RuntimeError`` because every code reports that the *node* — or the pairing
    of node and path — makes the question unanswerable, never that an argument's
    value was rejected. ``operation`` names the inspection function and ``entity``
    the node's own concrete Entity Identity where one is known. Neither the node
    nor its private state is retained or exposed.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        operation: str,
        entity: EntityIdentity | None = None,
    ) -> None:
        if code not in SNAPSHOT_INSPECTION_CODES:
            raise ValueError(f"{code!r} is not a snapshot inspection code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.operation = operation
        self.entity = entity


@dataclass(frozen=True, slots=True)
class SnapshotNodeState:
    """One materialized node's whole Snapshot-lifecycle state.

    ``views`` holds the narrowed views the read requested, keyed by the derived
    view key (relationship name plus effective concrete-subtype set); a broad
    view's loaded state lives in the relationship slot itself, since installing
    the unloaded sentinel there is what makes ordinary attribute access raise.
    ``pin`` and ``edge`` are present exactly for a node whose family declares
    as-of axes.
    """

    entity: EntityIdentity
    views: Mapping[str, object]
    pin: Pin | None = None
    edge: Edge | None = None


def snapshot_state_of(node: object) -> SnapshotNodeState | None:
    """``node``'s Snapshot state, or ``None`` for anything this lifecycle did not
    materialize — a fresh instance, an edit of a fresh instance, or another
    lifecycle's node.

    An edited copy of a node this lifecycle DID materialize answers that node's
    own state, because an edit preserves every kind of instance state outside the
    declared members. What this answers is therefore a value's provenance, not
    its editedness."""
    state = _lifecycle_state_of(node)
    return state if isinstance(state, SnapshotNodeState) else None


def pin_of(node: object) -> Pin:
    """The as-of coordinates ``node`` was read at (spec §3).

    Every node of one ``find`` shares the whole-graph pin; a milestone-set read's
    roots each carry their own milestone-derived pin instead.
    """
    state = _required_state(node, "pin_of")
    if state.pin is None:
        raise SnapshotInspectionError(
            code="snapshot-pin-unavailable",
            message=f"{state.entity.canonical} declares no as-of axis, so it was read at no pin",
            operation="pin_of",
            entity=state.entity,
        )
    return state.pin


def edge_of(node: object) -> Edge:
    """``node``'s own milestone :class:`~parallax.core.temporal_read.Edge` — the
    finite from-instant on every axis its family declares (spec §3)."""
    state = _required_state(node, "edge_of")
    if state.edge is None:
        raise SnapshotInspectionError(
            code="snapshot-edge-unavailable",
            message=f"{state.entity.canonical} is not temporal, so it stands on no milestone",
            operation="edge_of",
            entity=state.entity,
        )
    return state.edge


def is_view_loaded(node: object, path: RelationshipPath[Any, Any]) -> bool:
    """Whether every relationship view ``path`` traverses, on every branch it
    reaches, was loaded by the read that produced ``node`` (spec §3).

    Never issues SQL and never raises for an unloaded view — that is the whole
    question it answers. The uninstantiated suffix of a null or empty branch is
    vacuously loaded, so a path continuing past a loaded-null hop is loaded. It
    still raises for a node this lifecycle did not produce and for a path whose
    starting owner does not apply to it: answering ``False`` there would report
    "not fetched" for a question that was never askable.
    """
    _required_state(node, "is_view_loaded")
    checked = _require_path(node, path, "is_view_loaded")
    _, _, loaded = _traverse(node, checked, "is_view_loaded", raising=False)
    return loaded


def view(node: object, path: RelationshipPath[Any, Any]) -> object:
    """The value ``path`` reaches from ``node``, using only loaded state (spec §3).

    A path whose every traversed segment is to-one answers the terminal Entity or
    ``None``. A path traversing any to-many segment fans out and answers one flat
    tuple of non-null terminal values in traversal order, duplicates preserved; a
    null or empty intermediate branch contributes none. A narrowed segment
    traverses that narrowed view rather than the broad relationship, so
    ``view(owner, Owner.pets.narrow(Dog).doghouse)`` reaches only the dogs'
    doghouses.

    Raises :class:`~parallax.core.entity.UnloadedRelationshipError` for the first
    unloaded view in path-segment order and, within a fan-out, source-tuple order.
    """
    _required_state(node, "view")
    checked = _require_path(node, path, "view")
    terminals, fanned, _ = _traverse(node, checked, "view", raising=True)
    if fanned:
        return tuple(terminals)
    return terminals[0] if terminals else None


# --------------------------------------------------------------------------- #
# Traversal                                                                    #
# --------------------------------------------------------------------------- #


class _UnloadedMarker:
    """The private answer ``is_view_loaded`` reads where ``view`` raises."""

    __slots__ = ()


_UNLOADED_MARKER: Final = _UnloadedMarker()


def _traverse(
    node: object, path: RelationshipPath[Any, Any], operation: str, *, raising: bool
) -> tuple[list[object], bool, bool]:
    """Walk ``path`` from ``node``, answering its terminals, whether it fanned out,
    and whether every view it reached was loaded.

    One traversal serves both operations because they differ only in what an
    unloaded view means: ``view`` raises at the first one, in path-segment order
    and then source-tuple order, while ``is_view_loaded`` reports it. Fan-out is
    read off the values actually traversed, so a loaded-empty to-many segment
    still answers the empty tuple rather than a null terminal.
    """
    frontier: list[object] = [node]
    fanned = False
    for segment in path.segments:
        reached: list[object] = []
        for source in frontier:
            value = _segment_value(source, segment, operation, raising=raising)
            if value is _UNLOADED_MARKER:
                return [], fanned, False
            if isinstance(value, tuple):
                fanned = True
                reached.extend(
                    item for item in cast("tuple[object, ...]", value) if item is not None
                )
            elif value is not None:
                reached.append(value)
        frontier = reached
        if not frontier:
            return [], fanned, True
    return frontier, fanned, True


def _segment_value(
    source: object, segment: PathSegment, operation: str, *, raising: bool
) -> object:
    """One segment's already-loaded value at ``source``.

    A narrowed segment reads the distinct narrowed view the read populated; a
    broad segment reads the relationship slot itself, where the unloaded sentinel
    is what an unrequested include left behind.
    """
    key = _view_key(segment)
    if segment.narrow:
        state = snapshot_state_of(source)
        views: Mapping[str, object] = {} if state is None else state.views
        if key not in views:
            if raising:
                raise UnloadedRelationshipError(key)
            return _UNLOADED_MARKER
        return views[key]
    owner = _segment_owner(source, segment)
    if owner is None:
        raise _owner_mismatch(source, segment, operation)
    value = _relationship_value_of(source, owner)
    if value is UNLOADED:
        if raising:
            raise UnloadedRelationshipError(key)
        return _UNLOADED_MARKER
    return value


def _required_state(node: object, operation: str) -> SnapshotNodeState:
    state = snapshot_state_of(node)
    if state is None:
        raise SnapshotInspectionError(
            code="snapshot-node-required",
            message=(
                f"{operation} inspects a node a Snapshot read materialized; "
                f"{type(node).__name__} carries no Snapshot state"
            ),
            operation=operation,
        )
    return state


def _require_path(node: object, path: object, operation: str) -> RelationshipPath[Any, Any]:
    """``path`` as a Relationship Path whose starting owner applies to ``node``.

    Refuses anything else, including the bare relationship-name string an
    untyped caller may still reach here with. A relationship an accepted ancestor
    declares applies to every concrete subtype, which is exactly what walking the
    class's own ancestry answers.
    """
    if not isinstance(path, RelationshipPath) or not path.segments:
        raise SnapshotInspectionError(
            code="snapshot-view-owner-mismatch",
            message=(
                f"{operation} takes a class-derived Relationship Path "
                "(`Owner.items`, `Owner.pets.narrow(Dog)`), never a bare relationship name"
            ),
            operation=operation,
            entity=_entity_of(node),
        )
    typed = cast("RelationshipPath[Any, Any]", path)
    first = typed.segments[0]
    if _segment_owner(node, first) is None:
        raise _owner_mismatch(node, first, operation)
    return typed


def _owner_mismatch(node: object, segment: PathSegment, operation: str) -> SnapshotInspectionError:
    entity = _entity_of(node)
    reached = "an Entity this path cannot address" if entity is None else entity.canonical
    return SnapshotInspectionError(
        code="snapshot-view-owner-mismatch",
        message=f"{segment.rel} names no relationship applying to {reached}",
        operation=operation,
        entity=entity,
    )


def _segment_owner(node: object, segment: PathSegment) -> RelationshipIdentity | None:
    """The Relationship Identity ``segment`` names for ``node``'s concrete class,
    or ``None`` when no accepted ancestor of that class declares it.

    A segment spells its owner exactly, so the answer is the ancestry position
    carrying that Identity and declaring that relationship — which is how an
    ancestor's declaration applies to a concrete subtype while a disjoint
    sibling's identically named one does not.
    """
    owner, _, name = segment.rel.rpartition(".")
    for ancestor in type(node).__mro__:
        if not is_entity_class(ancestor):
            continue
        identity = declaration_of(ancestor).identity
        if identity.canonical == owner and name in members_of(ancestor).relationship_py:
            return RelationshipIdentity(identity, name)
    return None


def _entity_of(node: object) -> EntityIdentity | None:
    cls = type(node)
    return declaration_of(cls).identity if is_entity_class(cls) else None


def _view_key(segment: PathSegment) -> str:
    """The private per-segment view key: the relationship's local name, plus the
    variant spellings of the concrete subtypes a narrowed segment names.

    A view key is RESULT vocabulary while the segment's own ``rel`` and ``narrow``
    are addressing references, so both halves shed their namespace here — the
    same local spelling deep-fetch planning derived through
    ``inheritance.family_variant_name`` when it keyed the view it populated.
    """
    local = _local(segment.rel)
    if not segment.narrow:
        return local
    return f"{local}[{','.join(sorted(_local(name) for name in segment.narrow))}]"


def _local(spelling: str) -> str:
    return spelling.rpartition(".")[2]
