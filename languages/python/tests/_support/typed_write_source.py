"""What one model's Typed writes read off an Entity value, by member name.

Production reads a value's source hooks in its resolved Entity's member order and
hands the positions to preparation; a suite asking what a value answers reads
the same hooks through this and compares by name.
"""

from __future__ import annotations

from typing import Any

from parallax.core.entity import DomainModel, Entity
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._model import model_of
from tests._support.write_preparation import write_preparation_of

__all__ = ["TypedWriteSource"]


class TypedWriteSource:
    """What one model's Typed writes read off a value, by member name."""

    def __init__(self, model: DomainModel) -> None:
        self._preparation = write_preparation_of(model_of(model))

    def _against(self, value: Entity) -> tuple[Any, Any, int]:
        entry = self._preparation.entity(type(value).identity)
        return entry.selection.members.shape, type(value).identity, entry.key

    def row(self, value: Entity) -> dict[str, object]:
        """What a write reads as stated: every member the value holds but the
        framework's own, which the write's preparation reads as unstated."""
        shape, identity, _key = self._against(value)
        owned = self._preparation.entity(identity).framework_owned
        values = value.__parallax_row_values__(shape, identity)
        return {
            member.name: held
            for position, (member, held) in enumerate(zip(shape.members, values, strict=True))
            if held is not ABSENT and not owned >> position & 1
        }

    def identity(self, value: Entity) -> dict[str, object]:
        shape, identity, key = self._against(value)
        return self._named(shape, value.__parallax_identity_pairs__(shape, identity, key))

    def authored(self, value: Entity) -> dict[str, object] | None:
        shape, identity, key = self._against(value)
        pairs = value.__parallax_authored_pairs__(shape, identity, key)
        return None if pairs is None else self._named(shape, pairs)

    @staticmethod
    def _named(shape: Any, pairs: tuple[tuple[int, object], ...]) -> dict[str, object]:
        return {shape.members[position].name: held for position, held in pairs}
