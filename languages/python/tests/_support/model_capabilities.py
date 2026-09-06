"""The model-bound collaborators, built directly over a Domain Model.

Production derives all three inside ``prepare_model`` and retains them on a
Model Selection. A suite grading one collaborator on its own — the layouts, the
row codec, or the graph construction — wants that one over a model it names,
without a selection, an edition, or the composition root in reach; these build
exactly what preparation builds, from the same two accessors, and nothing else.
"""

from __future__ import annotations

from parallax.core.entity import DomainModel, EntityGraphConstruction, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of

__all__ = ["cataloged_for", "graph_construction_for", "row_codec_for"]


def cataloged_for(model: DomainModel) -> CatalogedModel:
    """``model``'s accepted Metamodel paired with the layouts derived from it."""
    return CatalogedModel(model_of(model))


def row_codec_for(model: DomainModel) -> EntityRowCodec:
    """A row codec over ``model``'s accepted Metamodel."""
    return EntityRowCodec(model_of(model))


def graph_construction_for(model: DomainModel) -> EntityGraphConstruction:
    """A graph construction over ``model``, which must have composed Entity Classes."""
    classes = class_index(model)
    if classes is None:
        raise ValueError("a descriptor-backed Domain Model composed no class to construct with")
    cataloged = cataloged_for(model)
    return EntityGraphConstruction(cataloged.meta, classes, cataloged.layouts)
