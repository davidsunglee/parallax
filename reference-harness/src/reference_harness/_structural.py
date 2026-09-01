"""Exact structural-container recognition shared by harness graders."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeGuard


def is_structural_sequence(value: object) -> TypeGuard[Sequence[Any]]:
    """Whether ``value`` is a positional container, excluding text and binary scalars."""
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    )
