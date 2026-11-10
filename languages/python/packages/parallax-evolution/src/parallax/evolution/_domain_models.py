from __future__ import annotations

from typing import overload

from parallax.core.entity._model import DomainModel, model_of
from parallax.evolution.model_evolution import (
    Absent,
    Evolution,
    UnilateralEvolution,
    evolve_metamodels,
)

__all__ = ["evolve"]


@overload
def evolve(earlier: Absent, later: DomainModel) -> UnilateralEvolution: ...


@overload
def evolve(earlier: DomainModel, later: DomainModel) -> Evolution: ...


def evolve(earlier: DomainModel | Absent, later: DomainModel) -> Evolution:
    """Describe every difference between two Domain Models.

    Provisioning is unilateral by TYPE: passing :data:`ABSENT` for ``earlier``,
    as for an empty database, narrows the result, so the schema generator needs
    no runtime check on that path. Equal endpoints return an empty
    :class:`UnilateralEvolution`. Either argument that is not a Domain Model,
    other than an ``ABSENT`` ``earlier``, raises :class:`TypeError`.
    """
    return evolve_metamodels(
        earlier if isinstance(earlier, Absent) else model_of(earlier), model_of(later)
    )
