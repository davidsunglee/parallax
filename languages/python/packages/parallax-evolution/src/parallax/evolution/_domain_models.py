from __future__ import annotations

from typing import Final, overload

from parallax.core.internal.base import UsageError
from parallax.core.internal.database_binding import (
    REQUIRED,
    DatabaseBinding,
    ResolvedBinding,
    require_binding,
)
from parallax.core.internal.entity._model import DomainModel, model_of
from parallax.evolution.internal.model_evolution import (
    Absent,
    Evolution,
    UnilateralEvolution,
    evolve_resolved,
)

__all__ = ["EVOLUTION_BINDING_UNEXPECTED", "evolve"]

EVOLUTION_BINDING_UNEXPECTED: Final = "evolution-binding-unexpected"
"""An earlier binding accompanied an absent earlier model, which places nothing."""


@overload
def evolve(
    earlier: Absent, later: DomainModel, *, later_binding: DatabaseBinding
) -> UnilateralEvolution: ...


@overload
def evolve(
    earlier: DomainModel,
    later: DomainModel,
    *,
    earlier_binding: DatabaseBinding,
    later_binding: DatabaseBinding,
) -> Evolution: ...


def evolve(
    earlier: DomainModel | Absent,
    later: DomainModel,
    *,
    earlier_binding: object = REQUIRED,
    later_binding: object = REQUIRED,
) -> Evolution:
    """Describe every difference between two Domain Models, each under its binding.

    Each endpoint is resolved under its own binding, so a binding-only move of
    a surviving table or sequence is a coordinated relocation rather than an
    empty change, and a declared table-name change a binding masks moves
    nothing. Provisioning is unilateral by TYPE: passing :data:`ABSENT` for
    ``earlier``, as for an empty database, narrows the result, and takes no
    ``earlier_binding``. Equal endpoints return an empty
    :class:`UnilateralEvolution`. Either model argument that is not a Domain
    Model, other than an ``ABSENT`` ``earlier``, raises :class:`TypeError`;
    endpoints bound for different backends raise ``evolution-backend-mismatch``.
    """
    later_resolved = ResolvedBinding(model_of(later), require_binding(later_binding, "evolve"))
    if isinstance(earlier, Absent):
        if earlier_binding is not REQUIRED:
            raise UsageError(
                EVOLUTION_BINDING_UNEXPECTED,
                "an absent earlier model places nothing; evolve(ABSENT, ...) takes no "
                "earlier_binding=",
            )
        return evolve_resolved(earlier, later_resolved)
    return evolve_resolved(
        ResolvedBinding(model_of(earlier), require_binding(earlier_binding, "evolve")),
        later_resolved,
    )
