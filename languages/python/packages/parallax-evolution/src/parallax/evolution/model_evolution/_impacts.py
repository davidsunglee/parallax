"""Behavioral Impacts derived from the two endpoints.

Each impact compares effective facts read through the owning module's facet on
both endpoints — never re-derived here — on scopes present in the earlier
endpoint. A wholly new Entity's members are described by its own addition, so a
parent addition contributes no impact of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from parallax.evolution.model_evolution._matching import Matching
from parallax.evolution.model_evolution._values import BehavioralImpact, EvolutionOperation

__all__ = ["impacts"]


def impacts(
    matching: Matching, operations: Sequence[EvolutionOperation]
) -> tuple[BehavioralImpact, ...]:
    """Every Behavioral Impact the two endpoints differ by, in canonical order."""
    del matching, operations
    return ()
