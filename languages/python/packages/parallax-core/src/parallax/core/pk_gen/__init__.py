"""``parallax.core.pk_gen`` enforcement scope (m-pk-gen).

The primary-key generation strategy model: application-assigned (caller-supplied),
``max`` (``max(col) + 1`` folded into the INSERT's SQL), and ``sequence`` (a
simulated sequence registry table hands out reserved blocks). This scope carries
the pure strategy classification and the block-allocation arithmetic; the actual
DML (the ``max`` INSERT's ``coalesce(max(...), ?) + ?`` fragment, the registry
``update ... set next_val = next_val + ?``) is lowered at the write seam
(``parallax.snapshot.handle``) from the
neutral ``{computed: "maxPlusOne"}`` / ``{increment: n}`` DB-computed markers a
write row carries; :func:`allocate_block` is the block arithmetic the
``sequence`` strategy's registry choreography derives its ids from.
``m-pk-gen`` depends on ``m-metamodel``.

Generation is reachable only through an Attribute's primary-key branch, and a
:class:`~parallax.core.metamodel.Sequence` reaches this scope with every sizing
parameter already resolved to its semantic default, so nothing here re-fills one.
"""

from __future__ import annotations

from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Max,
    PkGeneration,
    PrimaryKey,
    Sequence,
)

__all__ = [
    "REGISTRY_KEY_ROLE",
    "REGISTRY_VALUE_ROLE",
    "allocate_block",
    "generated_key_attribute",
    "generates",
]

# The two column roles of a simulated-sequence registry table (e.g. the corpus
# `PkSequence` entity): the sequence-name key and the next-value counter. The
# registry entity itself is user-declared in the model; m-pk-gen only names the
# roles it reads and advances.
REGISTRY_KEY_ROLE = "sequenceName"
REGISTRY_VALUE_ROLE = "nextValue"


def generates(generation: PkGeneration) -> bool:
    """Whether ``generation`` allocates a key the caller does not supply.

    ``max`` and ``sequence`` do; an application-assigned key is the caller's.
    """
    return isinstance(generation, (Max, Sequence))


def generated_key_attribute(entity: EntityMetadata) -> AttributeMetadata | None:
    """``entity``'s own primary-key Attribute whose value the framework allocates.

    A local view of ``entity``'s own declarations, so an inheritance participant
    whose key is declared on the family root answers ``None``: this scope reaches
    no family-effective view, and the seam that lowers a generated key resolves
    the declaring position before asking.
    """
    for attribute in entity.declared_attributes:
        key = attribute.primary_key
        if isinstance(key, PrimaryKey) and generates(key.generation):
            return attribute
    return None


def allocate_block(sequence: Sequence, current_next: int) -> tuple[tuple[int, ...], int]:
    """Reserve one block from the registry.

    Hands out ``batch_size`` ids starting at ``current_next`` stepping by
    ``increment_size``, and returns the block together with the registry's new
    stored next value. The registry counter advances by ``batch_size *
    increment_size`` so consecutive blocks never overlap.
    """
    ids = tuple(
        current_next + step * sequence.increment_size for step in range(sequence.batch_size)
    )
    new_next = current_next + sequence.batch_size * sequence.increment_size
    return ids, new_next
