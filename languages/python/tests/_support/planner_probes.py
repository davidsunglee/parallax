"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    BufferItem,
    KeyedWrite,
    ObjectKey,
    ObservedKeyedWrite,
    SubjectIdentity,
    WriteObservation,
    object_key,
)

__all__ = ["TEST_SUBJECT_IDENTITY", "observed_buffer"]

# An arbitrary nonempty Subject Identity: `m-unit-work` requires one on every
# Planning Request and guarantees it is never inspected, so any value serves
# every suite here identically.
TEST_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity("test-subject")


def observed_buffer(
    buffer: Sequence[BufferItem],
    model: Metamodel,
    observations: Mapping[ObjectKey, WriteObservation] | None,
) -> list[BufferItem]:
    """``buffer`` with every item ``observations`` names wrapped in its carrier.

    A planner-level suite states which objects the transaction observed, which
    is the readable way to author the scenario; the verb that would do the
    resolving is not in play. This turns that statement into what a verb
    buffers — the instruction travelling with its own observation.
    """
    if not observations:
        return list(buffer)
    resolved: list[BufferItem] = []
    for item in buffer:
        if not isinstance(item, KeyedWrite):
            resolved.append(item)
            continue
        key = object_key(item, model)
        observation = None if key is None else observations.get(key)
        resolved.append(
            item
            if observation is None
            else ObservedKeyedWrite(instruction=item, observation=observation)
        )
    return resolved
