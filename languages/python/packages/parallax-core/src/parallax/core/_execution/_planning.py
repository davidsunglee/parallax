from __future__ import annotations

from collections.abc import Mapping
from typing import overload

from parallax.core._execution._publication import ModelSelection, check_edition, select_model
from parallax.core._execution._unit_work.preparation import WritePreparation
from parallax.core._execution._unit_work.strategy import NO_AUDIT
from parallax.core._execution._unit_work.write_planner import WritePlanner
from parallax.core.internal.database_binding import (
    REQUIRED,
    DatabaseBinding,
    ResolvedBinding,
    require_binding,
)
from parallax.core.internal.entity import DomainModel, EntityGraphConstruction
from parallax.core.internal.entity._layout import CatalogedModel, EntityLayout
from parallax.core.internal.entity._model import class_index, model_of
from parallax.core.internal.metamodel import (
    EntityIdentity,
    MemberShape,
    Metamodel,
    Multiplicity,
    ScalarDefinition,
)
from parallax.core.internal.read_delivery._page import ABSENT
from parallax.core.internal.read_planning import narrowed_view_keys
from parallax.core.internal.wire._facts import (
    OCCURRENCE,
    WireEntityFacts,
    WireModelFacts,
    WireOccurrenceFacts,
    scalar_encoding,
)
from parallax.core.internal.write_payload import LayoutPayloadPreparer

__all__ = ["build_write_planner", "build_write_preparation", "prepare_model", "wire_model_facts"]


@overload
def prepare_model(  # pyright: ignore[reportInconsistentOverload] - the one overload hides the sentinel default, so omitting binding is a type error
    model: DomainModel, *, binding: DatabaseBinding, edition: str
) -> ModelSelection: ...


def prepare_model(
    model: DomainModel, *, binding: object = REQUIRED, edition: str
) -> ModelSelection:
    """Prepare one complete immutable model selection under ``binding``, without
    database I/O.

    Resolving the binding is structural: it checks no schema, grant, or
    object's existence, and refuses an omitted, invalid, or unplaceable binding
    with :class:`~parallax.core.BindingError` before anything is served.
    """
    placement = require_binding(binding, "prepare_model")
    check_edition(edition)
    catalog = CatalogedModel(model_of(model), placement)
    classes = class_index(model)
    if classes is None:
        construction = None
        positional = None
    else:
        construction = EntityGraphConstruction(catalog, classes)
        positional = _proven_classes(classes.by_identity, construction)
    return select_model(
        model,
        edition=edition,
        catalog=catalog,
        classes=classes,
        construction=construction,
        wire=wire_model_facts(catalog),
        narrowed_view_keys=narrowed_view_keys(catalog.meta),
        preparation=build_write_preparation(catalog.meta, positional=positional),
        planner=build_write_planner(catalog.resolved),
    )


def wire_model_facts(catalog: CatalogedModel) -> WireModelFacts:
    """How every Entity ``catalog`` lays out renders as Wire, class-backed or
    not: the facts each Wire reader of the prepared model renders through.

    A Value Object shape several occurrences share is prepared once."""
    shared: dict[tuple[int, bool], WireOccurrenceFacts] = {}
    return WireModelFacts(
        {
            entity.identity: _wire_entity_facts(catalog.layouts.entity(entity.identity), shared)
            for entity in catalog.meta.entities
        }
    )


def _wire_entity_facts(
    layout: EntityLayout, shared: dict[tuple[int, bool], WireOccurrenceFacts]
) -> WireEntityFacts:
    attributes = layout.attributes
    return WireEntityFacts(
        attribute_keys=tuple(attribute.identity.name for attribute in attributes),
        attribute_encodings=tuple(
            scalar_encoding(attribute.type, many=attribute.multiplicity is Multiplicity.MANY)
            for attribute in attributes
        ),
        attribute_types=tuple(attribute.type for attribute in attributes),
        wire_type=layout.wire_type,
        occurrences=tuple(
            (
                occurrence.identity.path[-1],
                _wire_occurrence_facts(
                    occurrence.document_shape,
                    occurrence.multiplicity is Multiplicity.MANY,
                    shared,
                ),
            )
            for occurrence in layout.occurrences
        ),
    )


def _wire_occurrence_facts(
    shape: MemberShape, many: bool, shared: dict[tuple[int, bool], WireOccurrenceFacts]
) -> WireOccurrenceFacts:
    held = shared.get((id(shape), many))
    if held is not None:
        return held
    members = shape.members
    facts = WireOccurrenceFacts(
        many=many,
        keys=tuple(member.name for member in members),
        encodings=tuple(
            scalar_encoding(member.type, many=member.multiplicity is Multiplicity.MANY)
            if isinstance(member, ScalarDefinition)
            else OCCURRENCE
            for member in members
        ),
        details=tuple(
            member.type
            if isinstance(member, ScalarDefinition)
            else _wire_occurrence_facts(
                member.shape, member.multiplicity is Multiplicity.MANY, shared
            )
            for member in members
        ),
    )
    shared[id(shape), many] = facts
    return facts


def _proven_classes(
    classes: Mapping[EntityIdentity, type], construction: EntityGraphConstruction
) -> dict[EntityIdentity, type]:
    """Each Entity's class whose member order ``construction`` proved equal to
    its Entity's own."""
    return {
        identity: cls for identity, cls in classes.items() if construction.proves(cls, identity)
    }


def build_write_preparation(
    model: Metamodel, *, positional: Mapping[EntityIdentity, type] | None = None
) -> WritePreparation:
    """The one ``WritePreparation`` every write of ``model`` is admitted
    against, its rows marking an omitted member as accepted Entity State does.

    ``positional`` names the Entity Classes whose correspondence with their
    Entity's member order the caller has proven, so their instances are read
    by position.

    Called once per prepared model selection (:func:`prepare_model`) and
    identically by the conformance engine's case lanes, so both lanes judge
    and represent a write through the same preparation.
    """
    return WritePreparation(model, absent=ABSENT, positional=positional)


def build_write_planner(resolved: ResolvedBinding) -> WritePlanner:
    """One ``WritePlanner`` for ``resolved``'s model, wired with production
    strategies and the payload preparer of the model under its binding, which
    every flush it plans is lowered through.

    Called once per prepared model selection (:func:`prepare_model`) and
    identically by the conformance engine's compile lane, so the two lanes plan
    and prepare through the same deterministic computation.
    """
    return WritePlanner._wired(  # pyright: ignore[reportPrivateUsage] - the composition root calls the planner's own private constructor
        resolved.meta,
        audit=NO_AUDIT,
        payloads=LayoutPayloadPreparer(resolved),
    )
