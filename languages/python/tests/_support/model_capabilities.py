"""The model-bound collaborators, built directly over a Domain Model.

Production derives each of these inside ``prepare_model`` and retains them on a
Model Selection. A suite grading one collaborator on its own — the layouts, the
write preparation, the graph construction, or the Wire facts — wants that one over a model it names,
without a selection, an edition, or the composition root in reach; these build
exactly what preparation builds, from the same two accessors, and nothing else.
"""

from __future__ import annotations

from parallax.core._execution._planning import wire_model_facts
from parallax.core._execution._unit_work.preparation import WritePreparation
from parallax.core.entity import DomainModel, EntityGraphConstruction
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.metamodel import Metamodel
from parallax.core.wire._facts import WireModelFacts

__all__ = [
    "cataloged_for",
    "graph_construction_for",
    "preparation_for",
    "wire_facts_for",
]


def cataloged_for(model: DomainModel) -> CatalogedModel:
    """``model``'s accepted Metamodel paired with the layouts derived from it."""
    return CatalogedModel(model_of(model))


def graph_construction_for(model: DomainModel) -> EntityGraphConstruction:
    """A graph construction over ``model``, which must have composed Entity Classes."""
    classes = class_index(model)
    if classes is None:
        raise ValueError("a descriptor-backed Domain Model composed no class to construct with")
    return EntityGraphConstruction(cataloged_for(model), classes)


def preparation_for(model: DomainModel | Metamodel) -> WritePreparation:
    """The write preparation over ``model``'s accepted Metamodel."""
    meta = model_of(model) if isinstance(model, DomainModel) else model
    return WritePreparation(meta, absent=ABSENT)


def wire_facts_for(model: DomainModel | CatalogedModel) -> WireModelFacts:
    """The Wire facts over ``model``'s layouts."""
    return wire_model_facts(model if isinstance(model, CatalogedModel) else cataloged_for(model))
