"""Formation inputs and probes for the compilers that own family-wide facts.

Formation enumerates Entities canonically, so whether a family's root precedes
its descendants depends on their names. ``DescendantsFirst`` fixes the order
that would expose a compiler reading a root's answer before deriving it, and
``record_root_derivations`` counts how often a compiler derives an answer, which
object identity alone cannot show: a discarded duplicate derivation leaves every
published entry identical.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from parallax.core.metamodel import (
    AbstractRoot,
    CompiledMetadata,
    EntityIdentity,
    EntityMetadata,
)

__all__ = ["DescendantsFirst", "family_roots", "record_root_derivations"]


def _is_root(entity: EntityMetadata) -> bool:
    return entity.inheritance is None or isinstance(entity.inheritance, AbstractRoot)


def family_roots(metadata: CompiledMetadata) -> list[EntityIdentity]:
    """Every family root in ``metadata``, a standalone Entity counting as its own."""
    return [entity.identity for entity in metadata.entities if _is_root(entity)]


class DescendantsFirst:
    """``metadata`` enumerating every family root after every descendant."""

    def __init__(self, metadata: CompiledMetadata) -> None:
        self._metadata = metadata
        self.entities: Sequence[EntityMetadata] = tuple(sorted(metadata.entities, key=_is_root))

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self._metadata.entity(identity)


def record_root_derivations(
    monkeypatch: pytest.MonkeyPatch, module: object, name: str
) -> list[EntityIdentity]:
    """The root of every call ``module.name`` receives, in call order.

    The derivation still answers, so the compiler publishes what it would have.
    """
    derive: Callable[..., object] = getattr(module, name)
    derived: list[EntityIdentity] = []

    def recording(root: EntityMetadata, *rest: object) -> object:
        derived.append(root.identity)
        return derive(root, *rest)

    monkeypatch.setattr(module, name, recording)
    return derived
