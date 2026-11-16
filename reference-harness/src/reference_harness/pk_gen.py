"""Independent primary-key generation oracles (m-pk-gen).

Every ``sequence`` key declaration names a model-wide logical allocator.
Declarations sharing a key must agree on the batch size, initial value,
increment size (each with its schema default filled), and the key's declared
type. Only each Entity's own authored attributes are read, so a family key
declared once on its ancestor counts once however many positions inherit it.

A ``key-sequence`` allocator is read off its declaration the same way, so the
harness provisions its native sequence and derives the keys and the position its
reservations reach from the declaration alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .value_object_resolve import RejectionError

PK_GEN_SEQUENCE_CONFLICT = "pk-gen-sequence-conflict"
MODEL_REJECTED_RULES: frozenset[str] = frozenset({PK_GEN_SEQUENCE_CONFLICT})

_SEQUENCE_DEFAULTS = (("batchSize", 1), ("initialValue", 1), ("incrementSize", 1))


def _canonical_order(definition: Mapping[str, Any]) -> tuple[str, str]:
    return (definition.get("namespace") or "", definition["name"])


def validate_shared_allocators(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Reject the first declaration disagreeing with its allocator key's first declaration."""
    first: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for definition in sorted(entity_defs, key=_canonical_order):
        namespace, name = _canonical_order(definition)
        owner = f"{namespace}.{name}" if namespace else name
        for attribute in definition.get("attributes", []) or []:
            generation = attribute.get("pkGeneration") if isinstance(attribute, dict) else None
            if not isinstance(generation, dict) or generation.get("strategy") != "sequence":
                continue
            terms = (
                *(generation.get(key, default) for key, default in _SEQUENCE_DEFAULTS),
                attribute.get("type"),
            )
            declared = f"{owner}.{attribute['name']}"
            earlier = first.setdefault(generation["name"], (declared, terms))
            if earlier[1] != terms:
                raise RejectionError(
                    PK_GEN_SEQUENCE_CONFLICT,
                    f"{declared} declares Sequence {generation['name']!r} with "
                    f"(batchSize, initialValue, incrementSize, type) {terms}, but "
                    f"{earlier[0]} declares {earlier[1]}",
                )


KEY_SEQUENCE = "key-sequence"

_SEQUENCE_BOUNDS: Mapping[str, tuple[int, int]] = {
    "postgres": (-(2**63), 2**63 - 1),
    "mariadb": (-(2**63) + 1, 2**63 - 2),
}
"""The values each dialect's native sequences hold (m-dialect *Native sequences*)."""

_KEY_BOUNDS: Mapping[str, tuple[int, int]] = {
    "int32": (-(2**31), 2**31 - 1),
    "int64": (-(2**63), 2**63 - 1),
}


@dataclass(frozen=True, slots=True)
class NativeSequence:
    """One ``key-sequence`` allocator as its declaration states it (m-pk-gen
    *Native key sequences*), with the schema defaults filled."""

    allocator: str
    data_type: str
    batch_size: int
    initial_value: int
    increment_size: int

    @property
    def step(self) -> int:
        """The native increment: one reserved block per step."""
        return self.batch_size * self.increment_size

    def key_range(self, dialect: str) -> tuple[int, int]:
        """The key type's values within *dialect*'s sequence bounds."""
        key_low, key_high = _KEY_BOUNDS[self.data_type]
        low, high = _SEQUENCE_BOUNDS[dialect]
        return max(key_low, low), min(key_high, high)

    def block_start(self, reservations: int) -> int:
        """The first key the reservation after *reservations* earlier ones answers."""
        return self.initial_value + reservations * self.step

    def block(self, first: int, dialect: str) -> list[int]:
        """The keys a block reserved at *first* hands out, clipped to the key range."""
        high = self.key_range(dialect)[1]
        return [
            key
            for key in (first + offset * self.increment_size for offset in range(self.batch_size))
            if key <= high
        ]


def native_sequences(entity_defs: Sequence[Mapping[str, Any]]) -> dict[str, NativeSequence]:
    """Every ``key-sequence`` allocator the raw *entity_defs* declare, by key, read
    off its first declaration in canonical Entity order (formation makes every
    declaration of one key agree)."""
    sequences: dict[str, NativeSequence] = {}
    for definition in sorted(entity_defs, key=_canonical_order):
        for attribute in definition.get("attributes", []) or []:
            generation = attribute.get("pkGeneration") if isinstance(attribute, dict) else None
            if isinstance(generation, dict) and generation.get("strategy") == KEY_SEQUENCE:
                sequences.setdefault(generation["name"], native_sequence(attribute))
    return sequences


def native_sequence(attribute: Mapping[str, Any]) -> NativeSequence:
    """The allocator a ``key-sequence`` key *attribute* declares."""
    generation = attribute["pkGeneration"]
    return NativeSequence(
        allocator=generation["name"],
        data_type=str(attribute["type"]),
        batch_size=generation.get("batchSize", 100),
        initial_value=generation.get("initialValue", 1),
        increment_size=generation.get("incrementSize", 1),
    )
