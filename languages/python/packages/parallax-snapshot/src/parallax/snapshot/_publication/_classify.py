from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core import temporal_read
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import (
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
from parallax.snapshot._publication._root import RootView

__all__ = [
    "CONFORMING_ROOT",
    "ConformingRoot",
    "NonConformingRoot",
    "classify_root",
]


@dataclass(frozen=True, slots=True)
class ConformingRoot:
    """A root whose whole requested include tree conforms; it publishes as itself."""

    node: int


@dataclass(frozen=True, slots=True)
class NonConformingRoot:
    """A root some stored state contradicted; it publishes as :class:`InvalidData`.

    ``node`` is the Root View node hydration constructs ``data`` from, and is
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


CONFORMING_ROOT: Final = ConformingRoot(0)
"""The verdict of every root whose whole publication segment conforms."""


def classify_root(
    root: RootView,
    model: Metamodel,
    versions: VersionAttributes,
    *,
    ordinal: int,
) -> ConformingRoot | NonConformingRoot:
    """``root``'s verdict, attributed over its finalized publication segment.

    A root publishing no finding answers :data:`CONFORMING_ROOT` without reading
    a node. ``versions`` names the explicit version Attribute a record publishes
    its observed version from, and ``ordinal`` is the root's position in the
    ordered result a Snapshot publishes.
    """
    if not root.has_issues:
        return CONFORMING_ROOT
    invalid = root.invalid_root
    if invalid is not None:
        return _keyless_root(invalid, ordinal)
    issues: set[StoredDataIssue] = set()
    hydrating = True
    for node in range(len(root)):
        carried = root.issues(node)
        if not carried:
            continue
        key = observed_object_key(root.layout(node), root.member_values(node), carried)
        issues.update(diagnosis(issue, key) for issue in carried)
        hydrating = hydrating and hydrates(carried)
    layout = root.layout(0)
    member_values = root.member_values(0)
    return NonConformingRoot(
        ordinal=ordinal,
        issues=frozenset(issues),
        object_key=observed_object_key(layout, member_values, root.issues(0)),
        version=observed_version(model, versions, layout, member_values),
        edge=observed_edge(temporal_read.view(model), layout, member_values),
        node=0 if hydrating else None,
    )


def _keyless_root(record: InvalidRootInput, ordinal: int) -> NonConformingRoot:
    """One result root whose own identity never decoded.

    It has no converted node behind it, so it reaches nothing, hydrates nothing,
    and locates itself by result position alone — the ordinal is the only fact
    about it that survived.
    """
    return NonConformingRoot(
        ordinal=ordinal,
        issues=frozenset(diagnosis(issue, None) for issue in record.issues),
        object_key=None,
        version=None,
        edge=None,
        node=None,
    )
