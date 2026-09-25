from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol, cast

from parallax.core import temporal_read
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.temporal_read import (
    Edge,
    NonTemporal,
    TemporalFacet,
    TemporalReadError,
    milestone_edge,
)
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._invalid import InvalidData, StoredDataIssue
from parallax.snapshot.materialize._page import (
    ABSENT,
    InvalidRootInput,
    StoredDataIssueCode,
    StoredDataIssueInput,
)
from parallax.snapshot.materialize._root import RootView

__all__ = [
    "ClassifiedRoot",
    "ConformingRoot",
    "RootClassifications",
    "VersionAttributes",
    "classify_roots",
    "hydrates",
]


class VersionAttributes(Protocol):
    """Where an Entity's explicit optimistic-lock version Attribute is named.

    Answers ``None`` for a family that carries no explicit version, a temporal
    one included. The runtime composing a read supplies the policy that owns
    that fact, so publishing an observed version needs no Metadata scan here.
    """

    def version_attribute(
        self, model: Metamodel, entity: EntityIdentity
    ) -> AttributeIdentity | None: ...


NON_HYDRATING_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-leaf-undecodable",
        "stored-data-attribute-null",
        "stored-data-family-tag-unknown",
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
    }
)
"""The codes for which no conforming value exists to hydrate (`m-snapshot-read`).

Their complement — a required member absent or stored null, and a wrong-kind
occurrence — is exactly the set the normative absence collapse already answers,
so a root carrying only those hydrates completely.
"""


def hydrates(issues: Iterable[StoredDataIssueInput]) -> bool:
    """Whether a node carrying ``issues`` still publishes a value.

    The question every consumer of a classified node asks before treating it as
    ordinary data: a hydratable node's collapse produced legal member values, so
    it is an Entity a caller reads and a row a later write settles against, while
    a non-hydrating one has no conforming value to be either.
    """
    return not any(issue.code in NON_HYDRATING_CODES for issue in issues)


_UNIDENTIFIED_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
        "stored-data-family-tag-unknown",
    }
)
"""The codes that leave a node with no trustworthy Object Key of its own: its
identity did not decode, or the Entity that identity would name is unresolved."""


@dataclass(frozen=True, slots=True)
class ConformingRoot:
    """A root whose whole requested include tree conforms; it publishes as itself."""

    node: int


@dataclass(frozen=True, slots=True)
class ClassifiedRoot:
    """A root some stored state contradicted; it publishes as :class:`InvalidData`.

    ``node`` is the allocation index hydration constructs ``data`` from, and is
    absent exactly where no value could be produced without inventing one.
    """

    ordinal: int
    issues: frozenset[StoredDataIssue]
    object_key: ObjectKey | None
    version: int | None
    edge: Edge | None
    node: int | None

    def published(self, data: object | None) -> InvalidData[object]:
        """This root's public record, carrying ``data`` when hydration produced one."""
        return InvalidData(
            issues=self.issues,
            data=data,
            object_key=self.object_key,
            version=self.version,
            edge=self.edge,
            ordinal=self.ordinal,
        )


type RootClassification = ConformingRoot | ClassifiedRoot
"""One result root's verdict, in the position the result orders it at."""


@dataclass(frozen=True, slots=True)
class RootClassifications:
    """One Root View's verdicts and the construction scope they imply.

    ``excluded`` names the allocation indices construction leaves out. ``roots``
    is one verdict per result position, in result order, including the
    non-hydrating roots no allocation index stands behind.
    """

    roots: tuple[RootClassification, ...]
    excluded: frozenset[int] = frozenset()
    conforming: bool = False


def classify_roots(
    root_view: RootView,
    model: Metamodel,
    versions: VersionAttributes,
    *,
    ordinal_offset: int = 0,
) -> RootClassifications:
    """``root_view``'s per-root verdicts, attributed over each root's reachable tree.

    ``versions`` names the explicit version Attribute a record publishes its
    observed version from. ``ordinal_offset`` is where this Page's roots start
    in the ordered result a Snapshot publishes.
    """
    if not root_view.has_issues:
        return RootClassifications(
            roots=tuple(ConformingRoot(index) for index in root_view.roots if index is not None),
            conforming=True,
        )
    count = len(root_view.order)
    carried = tuple(root_view.issues(index) for index in range(count))
    children = tuple(_children(root_view, index) for index in range(count))
    keys = tuple(_object_key(root_view, index) for index in range(count))
    diagnoses = tuple(
        frozenset(_diagnosis(issue, key) for issue in issues)
        for issues, key in zip(carried, keys, strict=True)
    )
    blocking = tuple(not hydrates(issues) for issues in carried)

    roots: list[RootClassification] = []
    reached_by_published: set[int] = set()
    temporal = temporal_read.view(model)
    keyless_roots = iter(root_view.invalid_roots)
    for position, index in enumerate(root_view.roots):
        ordinal = ordinal_offset + position
        if index is None:
            roots.append(_keyless_root(next(keyless_roots), ordinal))
            continue
        reachable = _reachable(children, index)
        issues = frozenset(issue for node in reachable for issue in diagnoses[node])
        if not issues:
            roots.append(ConformingRoot(index))
            reached_by_published |= reachable
            continue
        hydrating = not any(blocking[node] for node in reachable)
        roots.append(
            ClassifiedRoot(
                ordinal=ordinal,
                issues=issues,
                object_key=keys[index],
                version=_version(model, versions, root_view, index),
                edge=_edge(temporal, root_view, index),
                node=index if hydrating else None,
            )
        )
        if hydrating:
            reached_by_published |= reachable
    return RootClassifications(
        roots=tuple(roots),
        excluded=frozenset(range(count)) - reached_by_published,
    )


def _keyless_root(record: InvalidRootInput, ordinal: int) -> ClassifiedRoot:
    """One result root whose own identity never decoded.

    It has no converted node behind it, so it reaches nothing, hydrates nothing,
    and locates itself by result position alone — the ordinal is the only fact
    about it that survived.
    """
    return ClassifiedRoot(
        ordinal=ordinal,
        issues=frozenset(_diagnosis(issue, None) for issue in record.issues),
        object_key=None,
        version=None,
        edge=None,
        node=None,
    )


def _diagnosis(issue: StoredDataIssueInput, key: ObjectKey | None) -> StoredDataIssue:
    """One internal issue as its public diagnosis, attributed to ``key``.

    Attribution is the whole of what classification adds: the path and the
    evidence are carried by reference exactly as conversion froze them.
    """
    return StoredDataIssue(
        issue.code,
        issue.entity,
        issue.member,
        key,
        path=issue.path,
        stored_value=issue.stored_value,
    )


def _children(root_view: RootView, node: int) -> tuple[int, ...]:
    """The allocation indices ``node``'s loaded relationship views reach.

    Every populated slot, broad and narrowed alike: the include tree a root
    requested is exactly what the Root View layout enumerates, so a slot's
    position is all this walk needs of it.
    """
    reached: dict[int, None] = {}
    for slot in range(len(root_view.view_layout(node).slots)):
        value = root_view.view(node, slot)
        if isinstance(value, tuple):
            reached.update(dict.fromkeys(cast("tuple[int, ...]", value)))
        elif value is not None and value is not ABSENT:
            reached[cast("int", value)] = None
    return tuple(reached)


def _reachable(children: tuple[tuple[int, ...], ...], root: int) -> frozenset[int]:
    """Every allocation index reachable from ``root``, including itself.

    The Root View is the requested include tree already realized: a view
    exists exactly where a level loaded one, so following views is following the
    includes. Cycles terminate on the visited set rather than on a depth bound.
    """
    seen = {root}
    pending = [root]
    while pending:
        for child in children[pending.pop()]:
            if child not in seen:
                seen.add(child)
                pending.append(child)
    return frozenset(seen)


def _object_key(root_view: RootView, node: int) -> ObjectKey | None:
    """``node``'s object identity, or absence where nothing trustworthy decoded.

    Derived exactly as a keyed write derives its own: the row's OWN resolved
    concrete Entity, never family-normalized, paired with the family key's
    ``(name, value)`` pair read at the layout's key position (`m-unit-work`).
    """
    layout = root_view.layout(node)
    if any(issue.code in _UNIDENTIFIED_CODES for issue in root_view.issues(node)):
        return None
    position = layout.primary_key[0]
    value = root_view.member_values(node)[position]
    return ObjectKey(
        layout.concrete,
        (
            (
                cast("AttributeIdentity", layout.members[position]).name,
                None if value is ABSENT else value,
            ),
        ),
    )


def _version(
    model: Metamodel, versions: VersionAttributes, root_view: RootView, node: int
) -> int | None:
    """``node``'s observed explicit version, or absence for every other shape."""
    layout = root_view.layout(node)
    attribute = versions.version_attribute(model, layout.concrete)
    if attribute is None:
        return None
    value = _member(layout, root_view.member_values(node), attribute)
    return value if isinstance(value, int) else None


def _edge(temporal: TemporalFacet, root_view: RootView, node: int) -> Edge | None:
    """``node``'s observed milestone, or absence where no temporal edge decoded."""
    shape = temporal.shape(root_view.layout(node).concrete)
    if shape is None or isinstance(shape, NonTemporal):
        return None
    try:
        return milestone_edge(shape, root_view, node)
    except TemporalReadError:
        return None


def _member(layout: EntityLayout, values: tuple[object, ...], member: AttributeIdentity) -> object:
    """One member's value by position, with an absent one answering ``None``.

    A locator reads what the row carries, and a position this read did not carry
    is a position it observed nothing at — the same answer a stored null gives,
    which is all a key or a version can say about a member that is not there.
    """
    position = layout.index_of.get(member)
    if position is None:  # pragma: no cover - a family locator is family-effective
        return None
    value = values[position]
    return None if value is ABSENT else value
