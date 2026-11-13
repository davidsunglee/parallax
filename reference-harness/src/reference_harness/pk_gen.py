"""Independent shared-allocator oracle (m-pk-gen logical allocators).

Every ``sequence`` key declaration names a model-wide logical allocator.
Declarations sharing a key must agree on the batch size, initial value,
increment size (each with its schema default filled), and the key's declared
type. Only each Entity's own authored attributes are read, so a family key
declared once on its ancestor counts once however many positions inherit it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
