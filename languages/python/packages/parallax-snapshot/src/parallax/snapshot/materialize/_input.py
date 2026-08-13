"""Snapshot Graph Input: the immutable carriers a read converts its rows into.

The whole vocabulary between the read driver and Entity graph construction. A
:class:`SnapshotNodeInput` is **one projection of one row** — never a merged
logical node: two projections of the same logical row are two entries whose
merge belongs to :mod:`parallax.snapshot.materialize._merge`. References rather
than recursively embedded records are what make a shared or cyclic graph
constructible without a mutable carrier.

Order semantics are fixed here and nowhere else: ``roots`` order and the tuple
inside a loaded-many relationship view are semantic; ``nodes`` order is not, nor
is the entry order inside a node's member and view tuples, which are indexed by
structured identity.

The scalar and Value Object carriers are Entity's own
(:mod:`parallax.core.entity._graph_input`) rather than copies: Snapshot Graph
Input and Entity Graph Construction share one exact recursive immutable algebra,
and defining it twice would let the two drift.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from parallax.core.document_codec import DocumentPathSegment
from parallax.core.entity._graph_input import (
    EntityAttributeInput,
    ValueObjectOccurrenceInput,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    PrimaryKey,
    RelationshipIdentity,
    TablePerConcreteSubtype,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Pin

__all__ = [
    "InvalidRootInput",
    "LogicalKey",
    "RelationshipViewKey",
    "SnapshotGraphInput",
    "SnapshotNodeInput",
    "SnapshotNodeRef",
    "SnapshotRelationshipViewInput",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "attribute_value",
    "has_invalid_key",
    "logical_key",
    "validate_graph_input",
]


type StoredDataIssueCode = Literal[
    "stored-data-required-member-absent",
    "stored-data-required-member-null",
    "stored-data-one-wrong-kind",
    "stored-data-many-wrong-kind",
    "stored-data-leaf-undecodable",
    "stored-data-attribute-null",
    "stored-data-family-tag-unknown",
    "stored-data-primary-key-null",
    "stored-data-primary-key-undecodable",
]
"""The closed internal stored-data issue vocabulary for snapshot reads."""


@dataclass(frozen=True, slots=True)
class StoredDataIssueInput:
    """One classified stored-state contradiction with logical provenance.

    ``path`` keeps declared member names distinct from integer array positions.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity | None = None
    path: tuple[DocumentPathSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotNodeRef:
    """An immutable reference to an entry in :attr:`SnapshotGraphInput.nodes`.

    ``node_index`` is an exact nonnegative built-in ``int``. It is not the later
    deterministic allocation index and has no public meaning: it names one
    projection, and several may name projections of one logical node.
    """

    node_index: int


@dataclass(frozen=True, slots=True)
class InvalidRootInput:
    """One non-hydrating result root with no constructible node behind it."""

    ordinal: int
    issues: tuple[StoredDataIssueInput, ...]

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("an invalid root ordinal is nonnegative")
        if not self.issues:
            raise ValueError("an invalid root carries at least one stored-data issue")


@dataclass(frozen=True, slots=True)
class RelationshipViewKey:
    """One relationship view a projection loaded.

    ``relationship`` is the declared direction. ``narrowed_view`` is the derived
    ``<rel>[<Concrete>,<Concrete>]`` key of a narrowed polymorphic hop, or
    ``None`` for the broad view — the two are distinct views of one direction and
    never merge into each other. The derived key is the plan's own canonical
    spelling of the hop's effective concrete-identity set; deriving a second one
    here would duplicate a decision deep-fetch planning already made.
    """

    relationship: RelationshipIdentity
    narrowed_view: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotRelationshipViewInput:
    """One relationship view entry: ``None`` is loaded-null, a reference is a
    loaded to-one, and a tuple is a loaded to-many whose order is semantic and
    whose emptiness is loaded-empty. Omitting the entry is what means unloaded."""

    view: RelationshipViewKey
    value: SnapshotNodeRef | tuple[SnapshotNodeRef, ...] | None


@dataclass(frozen=True, slots=True)
class SnapshotNodeInput:
    """One projection of one row, keyed entirely by structured identity.

    The member categories stay apart so a Value Object storage key can equal
    a relationship name without either overwriting the other, and
    ``concrete_entity`` is the exact Entity the compiled read resolved this row
    to — not the position it was reached through. ``issues`` carries every
    physical finding classified for this projection, without deduplication.
    """

    concrete_entity: EntityIdentity
    attributes: tuple[EntityAttributeInput, ...] = ()
    value_objects: tuple[ValueObjectOccurrenceInput, ...] = ()
    relationship_views: tuple[SnapshotRelationshipViewInput, ...] = ()
    issues: tuple[StoredDataIssueInput, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotGraphInput:
    """One materialization's whole graph input: every projection, the roots in
    result order, and the whole-graph pin every node was read at.

    A root with an invalid primary key is an :class:`InvalidRootInput`, retaining
    its result ordinal without claiming a constructible node. ``has_issues`` is
    set by the builder whenever any node carries classified stored-data issues.
    """

    nodes: tuple[SnapshotNodeInput, ...]
    roots: tuple[SnapshotNodeRef | InvalidRootInput, ...]
    pin: Pin
    has_issues: bool = False


type LogicalKey = tuple[EntityIdentity, tuple[object, ...]]
"""One logical node's graph-local identity: family-normalized name plus primary key."""


def attribute_value(node: SnapshotNodeInput, identity: AttributeIdentity) -> object | None:
    """``node``'s value for ``identity``, or ``None`` when it carries no entry.

    Absent and loaded-null answer alike, which is what every caller here needs: a
    gathered correlation key skips both, and a fan-back bucket neither key
    matches is the same bucket.
    """
    for entry in node.attributes:
        if entry.identity == identity:
            return entry.value
    return None


def logical_key(model: Metamodel, node: SnapshotNodeInput) -> LogicalKey | None:
    """``node``'s graph-local identity key: ``(family-normalized name, primary-key
    tuple)``.

    Family-normalized — an inheritance participant's identity is keyed to its
    family ROOT, never the position a particular projection reached it
    through — so two projections of one physical row answer one key. Answers
    ``None`` only where the family root declares no primary key at all
    (defensive; the accepted Metamodel requires one).

    TABLE-PER-CONCRETE-SUBTYPE is the one exception: each concrete owns its own
    physical table with its own independent primary-key namespace, so
    normalizing to the family root would conflate two different rows that merely
    share a key value. Identity there is the row's own resolved concrete.

    The coordinate component the identity triple names is deliberately omitted:
    within one materialization every node stands at the same whole-graph pin, so
    it can distinguish nothing.
    """
    view = inheritance_view(model).entity(node.concrete_entity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return None
    declaring = model.entity(view.root)
    if declaring is None:  # pragma: no cover - a family root is always accepted
        return None
    pk = tuple(
        attribute
        for attribute in declaring.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    if not pk:  # pragma: no cover - formation refuses a primary-key-less Entity
        return None
    identity = (
        node.concrete_entity
        if isinstance(view.strategy, TablePerConcreteSubtype)
        else declaring.identity
    )
    return identity, tuple(attribute_value(node, attribute.identity) for attribute in pk)


def has_invalid_key(node: SnapshotNodeInput) -> bool:
    """Whether ``node`` has no usable graph identity because its key is invalid."""
    return any(
        issue.code in {"stored-data-primary-key-null", "stored-data-primary-key-undecodable"}
        for issue in node.issues
    )


def validate_graph_input(graph: SnapshotGraphInput) -> None:
    """Reject a graph input no merge could read, before any merging happens.

    Two faults, both structural: a node reference outside ``nodes``, and two
    entries for one member or view identity within a single node. Neither is
    reachable through a public Snapshot read — the read driver builds this graph
    itself — so this guards the first-party seam rather than a caller's input.
    """
    count = len(graph.nodes)
    for ordinal, root in enumerate(graph.roots):
        if isinstance(root, InvalidRootInput):
            if root.ordinal != ordinal:
                raise ValueError(
                    f"invalid root at result position {ordinal} carries ordinal {root.ordinal}"
                )
        else:
            _require_in_range(root, count, "a root")
    for index, node in enumerate(graph.nodes):
        _require_unique(
            (entry.identity for entry in node.attributes), index, node, "Attribute entries"
        )
        _require_unique(
            (entry.identity for entry in node.value_objects),
            index,
            node,
            "Value Object occurrence entries",
        )
        _require_unique(
            (entry.view for entry in node.relationship_views),
            index,
            node,
            "relationship view entries",
        )
        for entry in node.relationship_views:
            for ref in view_refs(entry.value):
                _require_in_range(ref, count, f"node {index}")


def view_refs(
    value: SnapshotNodeRef | tuple[SnapshotNodeRef, ...] | None,
) -> tuple[SnapshotNodeRef, ...]:
    """The references one relationship view entry reaches, in order."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return (value,)


def _require_in_range(ref: SnapshotNodeRef, count: int, holder: str) -> None:
    if not 0 <= ref.node_index < count:
        raise ValueError(
            f"{holder} references node index {ref.node_index}, "
            f"outside this graph input's {count} nodes"
        )


def _require_unique(
    identities: Iterable[object], index: int, node: SnapshotNodeInput, kind: str
) -> None:
    seen: set[object] = set()
    for identity in identities:
        if identity in seen:
            raise ValueError(
                f"node {index} ({node.concrete_entity.canonical}) carries two "
                f"{kind} for {identity!r}"
            )
        seen.add(identity)
