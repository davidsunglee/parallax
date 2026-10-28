from __future__ import annotations

from parallax.core._execution._planning import build_write_preparation
from parallax.core._execution._unit_work.preparation import WritePreparation
from parallax.core.metamodel import Metamodel

__all__ = ["write_preparation_of"]

_PREPARED: dict[int, tuple[Metamodel, WritePreparation]] = {}


def write_preparation_of(model: Metamodel) -> WritePreparation:
    """The write preparation production derives for ``model``, derived once per
    model object, so every write a test prepares against one model shares its
    row selections as production's do."""
    held = _PREPARED.get(id(model))
    if held is not None and held[0] is model:
        return held[1]
    preparation = build_write_preparation(model)
    _PREPARED[id(model)] = (model, preparation)
    return preparation
