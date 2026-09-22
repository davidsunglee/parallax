"""Shared identity-safe reachability for retained-object proofs."""

from __future__ import annotations

import gc
from collections.abc import Sequence

__all__ = ["reachable_objects"]


def reachable_objects(value: object, *, boundaries: Sequence[object] = ()) -> tuple[object, ...]:
    """Objects reachable from value, stopping at classes and boundaries."""
    boundary_ids = {id(boundary) for boundary in boundaries}
    seen: set[int] = set()
    reached: list[object] = []
    pending = [value]
    while pending:
        held = pending.pop()
        identity = id(held)
        if identity in seen:
            continue
        seen.add(identity)
        reached.append(held)
        if identity in boundary_ids or isinstance(held, type):
            continue
        pending.extend(gc.get_referents(held))
    return tuple(reached)
