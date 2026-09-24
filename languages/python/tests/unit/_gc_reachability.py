"""Shared identity-safe reachability for retained-object proofs."""

from __future__ import annotations

import gc
from collections.abc import Sequence
from typing import NamedTuple

__all__ = ["Closure", "closure", "reachable_objects"]


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


class Closure(NamedTuple):
    """What one object holds, and which of the boundary it holds it through."""

    reached: tuple[int, ...]
    tracked: int
    references: int


def closure(start: object, boundary: Sequence[object]) -> Closure:
    """What ``start`` reaches without passing through any other member of
    ``boundary``, and which members it reaches.

    A TOTAL reading of one participant's own state, which is what a claim about
    one structure repeated in several places needs: two sums that share most of
    their terms cancel whatever they share when subtracted, and two closures do
    not.

    ``reached`` is the boundary members found, as their positions, so a caller
    states which of them one member may hold rather than how many. The walk stops
    at each of them, so a member reached through another member is not reported:
    what comes back is the boundary this one holds DIRECTLY.

    Classes end the walk and are not counted. Every instance of a kind reaches
    its own class and everything the module defining it does, which is shared
    structure no single instance can grow.

    Objects the collector does not track are followed but not counted in
    ``tracked``: whether an equal integer or an interned string is one object or
    two is the interpreter's business rather than the measured structure's.

    The reading is taken after a collection for that same reason. A tuple whose
    contents are all untracked is itself untracked only once a collection has
    visited it, so until then ``tracked`` counts how much allocation has happened
    to run since the structure was built rather than anything the structure
    holds: two identical structures reached by walks of different sizes read
    differently, the larger walk reading LOWER because it triggered the
    collections the smaller one did not. Collecting first puts every caller at
    the settled state, where tracked-ness is a property of the structure.
    """
    gc.collect()
    others = [member for member in boundary if member is not start]
    positions = {id(member): index for index, member in enumerate(boundary) if member is not start}
    reached: set[int] = set()
    tracked = 0
    references = len(gc.get_referents(start))
    for held in reachable_objects(start, boundaries=others)[1:]:
        if id(held) in positions:
            reached.add(positions[id(held)])
        elif not isinstance(held, type):
            tracked += gc.is_tracked(held)
            references += len(gc.get_referents(held))
    return Closure(tuple(sorted(reached)), tracked, references)
