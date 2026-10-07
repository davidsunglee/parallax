from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from parallax.core import temporal_read
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import (
    ABSENT,
    InvalidData,
    InvalidRootInput,
    StoredDataIssue,
    VersionAttributes,
    diagnosis,
    hydrates,
    observed_edge,
    observed_object_key,
    observed_version,
)
from parallax.core.temporal_read import Edge
from parallax.core.write_plan import ObjectKey
from parallax.snapshot.materialize._root import RootView

__all__ = [
    "ClassifiedRoot",
    "ConformingRoot",
    "RootClassifications",
    "classify_roots",
]


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
    keys = tuple(
        observed_object_key(root_view.layout(index), root_view.member_values(index), issues)
        for index, issues in enumerate(carried)
    )
    diagnoses = tuple(
        frozenset(diagnosis(issue, key) for issue in issues)
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
                version=observed_version(
                    model, versions, root_view.layout(index), root_view.member_values(index)
                ),
                edge=observed_edge(
                    temporal, root_view.layout(index), root_view.member_values(index)
                ),
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
        issues=frozenset(diagnosis(issue, None) for issue in record.issues),
        object_key=None,
        version=None,
        edge=None,
        node=None,
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
