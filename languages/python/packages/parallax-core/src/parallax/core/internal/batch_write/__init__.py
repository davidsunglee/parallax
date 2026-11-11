from __future__ import annotations

from typing import Final

from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.base import UsageError
from parallax.core.internal.metamodel import CompiledEntity, Metamodel

__all__ = ["SET_BASED_WRITE_TARGET_UNSUPPORTED", "judge_readless_target"]

SET_BASED_WRITE_TARGET_UNSUPPORTED: Final = "set-based-write-target-unsupported"


def judge_readless_target(
    model: Metamodel,
    entity: CompiledEntity,
    position: inheritance.InheritanceEntityView,
    mutation: str,
) -> None:
    """Refuse a predicate write whose target cannot be written by one readless
    statement (`m-batch-write`).

    Each selected object of a versioned or temporal family needs its own
    observation before it is written, so the write needs its caller to read
    first; the refusal names the verbs that write through such a read or a
    revision the caller holds."""
    shape = temporal_read.temporal_facet_of(model).shape(entity.identity)
    versioned = any(attribute.optimistic_locking for attribute in position.applicable_attributes)
    temporal = isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)
    if versioned or temporal:
        raise UsageError(
            SET_BASED_WRITE_TARGET_UNSUPPORTED,
            _readless_target_advice(entity, versioned, temporal, mutation),
        )


def _readless_target_advice(
    entity: CompiledEntity,
    versioned: bool,
    temporal: bool,
    mutation: str,
) -> str:
    # A deletion's keyed sibling is the destructive verb the target's kind admits.
    sibling = mutation if mutation != "delete" else "terminate" if temporal else "delete"
    revision = "version" if versioned else "tx_start"
    return (
        f"{entity.identity.name} is {'temporal' if temporal else 'versioned'}, so "
        f"{mutation}_where cannot change it without reading it. Read it (find / stream) and "
        f"{sibling} each object, or use {sibling}_if with the {revision} you hold."
    )
