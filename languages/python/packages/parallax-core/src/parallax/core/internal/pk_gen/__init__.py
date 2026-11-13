from __future__ import annotations

from parallax.core.internal.metamodel import (
    AttributeMetadata,
    CompiledEntity,
    Sequence,
)
from parallax.core.internal.pk_gen._rules import ISSUE_CODES, PK_GEN_MODULE, RULE_SET

__all__ = ["ISSUE_CODES", "PK_GEN_MODULE", "RULE_SET"]

# The two column roles of a simulated-sequence registry table (e.g. the corpus
# `PkSequence` entity): the sequence-name key and the next-value counter. The
# registry entity itself is user-declared in the model; m-pk-gen only names the
# roles it reads and advances.
REGISTRY_KEY_ROLE = "sequenceName"
REGISTRY_VALUE_ROLE = "nextValue"


def generated_key_attribute(entity: CompiledEntity) -> AttributeMetadata | None:
    """``entity``'s own primary-key Attribute whose value the framework allocates.

    A local view of ``entity``'s own declarations, so an inheritance participant
    whose key is declared on the family root answers ``None``: this scope reaches
    no family-effective view, and the seam that lowers a generated key resolves
    the declaring position before asking.
    """
    for attribute in entity.declared_attributes:
        if attribute.generated_key:
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
