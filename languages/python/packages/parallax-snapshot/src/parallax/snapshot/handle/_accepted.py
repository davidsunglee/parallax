"""The accepted model behind a handle's descriptor record graph.

Every handle threads the record graph the Entity frontend hands it, while the
SQL compiler types against the accepted Metamodel and one Entity's Metadata.
This module is the seam between the two: it forms the graph a handle already
holds and resolves the Entity a caller already named, so no handle carries a
second model parameter for the compiler's sake.

It exists only because the Entity frontend still returns a descriptor-backed
model. A frontend that returns an accepted model hands one to the handle
directly, and this module has nothing left to do.
"""

from __future__ import annotations

from parallax.core._formation_profile import form_metamodel
from parallax.core.descriptor import Metamodel
from parallax.core.descriptor.unresolved import unresolved_metamodel
from parallax.core.metamodel import EntityIdentity, EntityMetadata
from parallax.core.metamodel import Metamodel as AcceptedMetamodel

__all__ = ["accepted_entity", "accepted_model", "accepted_target"]


def accepted_model(meta: Metamodel) -> AcceptedMetamodel:
    """``meta`` as an accepted model.

    Forming is not free, so a caller that resolves several Entities of one graph
    forms once and resolves each through :func:`accepted_entity` rather than
    calling :func:`accepted_target` repeatedly.

    Raises :class:`~parallax.core.model_formation.MetamodelValidationError` when
    the graph does not form.
    """
    return form_metamodel(unresolved_metamodel(meta))


def accepted_entity(model: AcceptedMetamodel, meta: Metamodel, target: str) -> EntityMetadata:
    """``target``'s accepted Metadata in ``model``, which ``meta`` formed into.

    ``target`` is resolved through the record graph's own Entity lookup first, so
    a bare and a namespace-qualified spelling reach the same Entity here as they
    do everywhere else a handle names one.

    Raises :class:`KeyError` when the graph declares no such Entity — the same
    failure the record graph's own lookup already produces.
    """
    entity = meta.entity(target)
    metadata = model.entity(EntityIdentity(entity.namespace, entity.name))
    if metadata is None:  # pragma: no cover - both views come from one record graph
        raise KeyError(entity.canonical_name)
    return metadata


def accepted_target(meta: Metamodel, target: str) -> tuple[AcceptedMetamodel, EntityMetadata]:
    """``meta`` as an accepted model, paired with ``target``'s accepted Metadata."""
    model = accepted_model(meta)
    return model, accepted_entity(model, meta, target)
