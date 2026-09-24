"""Retained-state proofs for eager Typed-to-Wire projection (`cost` class)."""

from __future__ import annotations

import gc
import sys
import weakref
from collections import Counter
from collections.abc import Callable
from typing import Any, cast

from parallax.core.deep_fetch._include_tree import build_include_tree
from parallax.core.temporal_read import Pin
from parallax.snapshot import Snapshot
from parallax.snapshot.materialize import WireEntity
from parallax.snapshot.materialize import _wire as wire_materialize
from tests._support.model_capabilities import cataloged_for
from tests.unit._gc_reachability import reachable_objects
from tests.unit._instance_state_support import COMPACT, SCENARIOS, Scenario
from tests.unit.memory_instruments import (
    in_a_child_interpreter,
    serve_one_measurement,
    survivors,
    warmed,
)


def _snapshot(scenario: Scenario, count: int = 1) -> Snapshot[Any]:
    model = cataloged_for(scenario.model)
    includes = build_include_tree(
        queried=scenario.entity,
        root=(scenario.entity,),
        positions=(),
    )
    roots = COMPACT.graph(scenario, count)
    return Snapshot(cast("tuple[Any, ...]", roots), Pin(), "retention", includes, model)


@in_a_child_interpreter
def test_eager_projection_retains_only_the_returned_wire_envelope() -> None:
    source = _snapshot(SCENARIOS[2])
    returned: list[Snapshot[WireEntity]] = []

    def projection(sample: Callable[[], None]) -> None:
        returned[:] = [source.wire()]
        sample()

    alive = survivors(warmed(projection))
    assert returned
    expected = {
        id(cast("object", value))
        for value in reachable_objects(returned[0])
        if isinstance(value, (Snapshot, WireEntity, dict, list, tuple))
    }
    assert {id(value) for value in alive} <= expected
    inventory = Counter(
        "snapshot"
        if isinstance(value, Snapshot)
        else "entity"
        if isinstance(value, WireEntity)
        else "mapping"
        if isinstance(value, dict)
        else "sequence"
        if isinstance(value, list)
        else "roots"
        for value in alive
    )
    assert inventory == {
        "snapshot": 1,
        "entity": 1,
        "mapping": 4,
        "sequence": 1,
        "roots": 1,
    }


@in_a_child_interpreter
def test_projected_output_does_not_retain_the_typed_graph() -> None:
    source = _snapshot(SCENARIOS[2])
    typed = source.result()
    typed_ref = weakref.ref(typed)
    projected = source.wire()

    del source, typed
    gc.collect()
    gc.collect()

    assert typed_ref() is None
    assert projected.result() is not None


@in_a_child_interpreter
def test_failed_eager_projection_releases_all_projection_scaffolding() -> None:
    source = _snapshot(SCENARIOS[0], count=2)
    position = cast(
        "Callable[[wire_materialize.WireWalk[object], object, int], WireEntity]",
        wire_materialize.WireWalk[object].position,
    )

    def fail_after_render(
        walk: wire_materialize.WireWalk[object], node: object, requested: int
    ) -> WireEntity:
        position(walk, node, requested)
        raise RuntimeError("projection failed after rendering")

    cast("Any", wire_materialize.WireWalk).position = fail_after_render
    try:

        def failed(sample: Callable[[], None]) -> None:
            try:
                source.wire()
            except RuntimeError as error:
                assert str(error) == "projection failed after rendering"
            sample()

        alive = survivors(warmed(failed))
    finally:
        cast("Any", wire_materialize.WireWalk).position = position

    assert alive == []


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
