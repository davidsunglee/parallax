"""Each root of a sealed Page, inspected through the production publication pass.

A Root View exists only inside the pass that re-points it, so a suite reaches
one the way production does: through ``publish_roots`` with an inspecting
callback. The callback must copy what it asserts on, because the view it
receives answers for the next root once the callback returns;
:func:`observed` is that copy.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.read_delivery._page import (
    InvalidRootInput,
    Page,
    RootViewLayout,
    StoredDataIssueInput,
)
from parallax.core.temporal_read import Pin, TemporalShape
from parallax.snapshot._publication._root import RootView
from parallax.snapshot._publication._root_publication import publish_roots

__all__ = ["RootObservation", "each_root", "observed", "observed_roots"]


def each_root[T](
    page: Page,
    model: Metamodel,
    inspect: Callable[[RootView, int], T],
    *,
    atomic: bool = False,
    milestones: TemporalShape | None = None,
    read_evidence: Mapping[int, object] = MappingProxyType({}),
) -> list[T]:
    """What ``inspect`` answers for each of ``page``'s roots, given the Root View
    and result ordinal the pass hands that root's publisher."""
    return list(
        publish_roots(
            page,
            lambda root, ordinal: (inspect(root, ordinal),),
            model,
            atomic=atomic,
            milestones=milestones,
            read_evidence=cast("Mapping[int, Any]", read_evidence),
        )
    )


@dataclass(frozen=True, slots=True)
class RootObservation:
    """One root's Root View, copied while the pass still pointed at it.

    Each tuple is indexed by node, node 0 being the root. ``views`` holds each
    node's carried slot values and ``reached`` the Page projections the root
    reached.
    """

    layouts: tuple[EntityLayout, ...]
    member_values: tuple[tuple[object, ...], ...]
    issues: tuple[tuple[StoredDataIssueInput, ...], ...]
    view_layouts: tuple[RootViewLayout, ...]
    views: tuple[tuple[object, ...], ...]
    read_evidence: tuple[object, ...]
    invalid_root: InvalidRootInput | None
    has_issues: bool
    pin: Pin
    reached: tuple[int, ...]

    @property
    def concretes(self) -> tuple[EntityIdentity, ...]:
        """Each node's resolved concrete Entity."""
        return tuple(layout.concrete for layout in self.layouts)

    @property
    def names(self) -> list[str]:
        """Each node's concrete Entity name."""
        return [concrete.name for concrete in self.concretes]

    def view(self, node: int, slot: int) -> object:
        return self.views[node][slot]


def observed(root: RootView, _ordinal: int = 0) -> RootObservation:
    """A detached copy of everything ``root`` answers for its current root."""
    nodes = range(len(root))
    return RootObservation(
        layouts=tuple(root.layout(node) for node in nodes),
        member_values=tuple(root.member_values(node) for node in nodes),
        issues=tuple(root.issues(node) for node in nodes),
        view_layouts=tuple(root.view_layout(node) for node in nodes),
        views=tuple(
            tuple(root.view(node, slot) for slot in range(len(root.view_layout(node).slots)))
            for node in nodes
        ),
        read_evidence=tuple(root.read_evidence(node) for node in nodes),
        invalid_root=root.invalid_root,
        has_issues=root.has_issues,
        pin=root.pin,
        reached=tuple(root.reached),
    )


def observed_roots(
    page: Page,
    model: Metamodel,
    *,
    atomic: bool = False,
    milestones: TemporalShape | None = None,
    read_evidence: Mapping[int, object] = MappingProxyType({}),
) -> list[RootObservation]:
    """Every root of ``page``, observed in result order."""
    return each_root(
        page, model, observed, atomic=atomic, milestones=milestones, read_evidence=read_evidence
    )
