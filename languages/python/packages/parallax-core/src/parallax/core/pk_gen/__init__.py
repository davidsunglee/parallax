"""``parallax.core.pk_gen`` enforcement scope (m-pk-gen).

The primary-key generation strategy model: ``none`` (caller-supplied), ``max``
(``max(col) + 1`` folded into the INSERT's SQL), and ``sequence`` (a simulated
sequence registry table hands out reserved blocks). This scope carries the pure
strategy classification and the block-allocation arithmetic; the actual DML
(the ``max`` INSERT's ``coalesce(max(...), ?) + ?`` fragment, the registry
``update ... set next_val = next_val + ?``) is lowered at the write seam
(``parallax.snapshot.handle.lower_write``, COR-3 Phase 8 increment 3) from the
neutral ``{computed: "maxPlusOne"}`` / ``{increment: n}`` DB-computed markers a
write row carries; :func:`allocate_block` is the block arithmetic the
``sequence`` strategy's registry choreography derives its ids from.
``m-pk-gen`` depends only on ``m-descriptor``.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.descriptor import Attribute, Entity, PkGenerator

__all__ = [
    "REGISTRY_KEY_ROLE",
    "REGISTRY_VALUE_ROLE",
    "SequenceConfig",
    "allocate_block",
    "generated_key_attribute",
    "generates",
    "resolve_sequence",
]

# The two column roles of a simulated-sequence registry table (e.g. the corpus
# `PkSequence` entity): the sequence-name key and the next-value counter. The
# registry entity itself is user-declared in the model; m-pk-gen only names the
# roles it reads and advances.
REGISTRY_KEY_ROLE = "sequenceName"
REGISTRY_VALUE_ROLE = "nextValue"

# SimulatedSequence defaults (Reladomo prior art) when a config omits a field.
_DEFAULT_INITIAL = 1
_DEFAULT_INCREMENT = 1
_DEFAULT_BATCH = 1


def generates(pk: PkGenerator | None) -> bool:
    """Whether ``pk`` allocates a key the caller does not supply (``max``/``sequence``)."""
    return pk is not None and pk.generates


def generated_key_attribute(entity: Entity) -> Attribute | None:
    """The single primary-key attribute whose value the framework allocates, if any."""
    for attr in entity.primary_key:
        if generates(attr.pk_generator):
            return attr
    return None


@dataclass(frozen=True, slots=True)
class SequenceConfig:
    """A resolved simulated-sequence configuration with defaults filled in."""

    sequence_name: str
    initial_value: int
    increment_size: int
    batch_size: int


def resolve_sequence(pk: PkGenerator) -> SequenceConfig:
    """Resolve a ``sequence`` strategy's config, filling omitted fields with defaults."""
    if pk.strategy != "sequence":
        raise ValueError(f"not a sequence strategy: {pk.strategy}")
    if pk.sequence_name is None:
        raise ValueError("a sequence pkGenerator requires a sequenceName")
    return SequenceConfig(
        sequence_name=pk.sequence_name,
        initial_value=pk.initial_value if pk.initial_value is not None else _DEFAULT_INITIAL,
        increment_size=pk.increment_size if pk.increment_size is not None else _DEFAULT_INCREMENT,
        batch_size=pk.batch_size if pk.batch_size is not None else _DEFAULT_BATCH,
    )


def allocate_block(config: SequenceConfig, current_next: int) -> tuple[tuple[int, ...], int]:
    """Reserve one block from the registry.

    Hands out ``batch_size`` ids starting at ``current_next`` stepping by
    ``increment_size``, and returns the block together with the registry's new
    stored next value. The registry counter advances by ``batch_size *
    increment_size`` so consecutive blocks never overlap.
    """
    ids = tuple(current_next + step * config.increment_size for step in range(config.batch_size))
    new_next = current_next + config.batch_size * config.increment_size
    return ids, new_next
