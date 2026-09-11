"""The facts a conformance lane reads off a case's MODEL: which descriptor it
names, the accepted Metamodel and Domain Model that descriptor forms into, the
Serving Model a Handle adopts from, and the Entity positions a case's spellings
resolve to.

One place a case's model is loaded and prepared, so every lane preparing one
derives the same edition from the same fact about the case, and one place a
case's authored Entity spelling is adjudicated, so a case's reference resolves
the way every validator and lowering site resolves one. The default-target
conventions a case naming no explicit target falls back on — the model's single
family root, else its own first declared entity — are model facts too, and
live here so the lanes that resolve a default share one reading. So is what a
case's Object Query means against its model: :func:`canonicalize_read` is the
one place a read is preflighted and planned, so every lane that compiles one
consumes the same validated execution token production's own reads do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from parallax.conformance import case_format, models
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core import deep_fetch, inheritance
from parallax.core.deep_fetch import ValidatedEntityQuery
from parallax.core.entity import DomainModel
from parallax.core.metamodel import EntityMetadata, entity_by_name
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.snapshot.handle import ServingModel, prepare_model
from parallax.snapshot.handle._preflight import preflight

__all__ = [
    "canonicalize_read",
    "case_edition",
    "case_entity",
    "case_serving_model",
    "declaring_metadata",
    "default_family_root",
    "family_declarer",
    "first_declared_entity",
    "load_case_domain_model",
    "load_case_metamodel",
    "model_path",
]


def _case_model_path(case: case_format.Case) -> Path:
    model_ref = case.document.get("model")
    if not isinstance(model_ref, str):
        raise EngineError(f"{case.path.name}: `model` must be a string path")
    return model_path(model_ref)


def model_path(model_ref: str) -> Path:
    """The descriptor file a case's ``model`` reference names, under the corpus."""
    return case_format.find_repo_root() / "core" / "compatibility" / model_ref


def load_case_metamodel(case: case_format.Case) -> AcceptedMetamodel:
    """The accepted Metamodel the case's model descriptor forms into."""
    return models.load_model(_case_model_path(case))


def load_case_domain_model(case: case_format.Case) -> DomainModel:
    """The Domain Model the case's model descriptor forms into.

    A Snapshot connection takes the Domain Model rather than the accepted
    Metamodel underneath it, so a lane that connects loads this and reads the
    accepted model back out through
    :func:`~parallax.conformance.models.accepted_model_of` — one formation
    serving the connection and every neutral surface beside it.
    """
    return models.load_domain_model(_case_model_path(case))


def case_edition(case: case_format.Case) -> str:
    """The Model Edition a case's model is prepared under: the model
    descriptor's file stem, ``"account"`` for ``models/account.yaml``.

    One rule, so every lane preparing a case's model derives the same literal
    from the same fact about the case.
    """
    return _case_model_path(case).stem


def case_serving_model(case: case_format.Case) -> ServingModel:
    """The Serving Model a case's Handles adopt from: its Domain Model prepared
    explicitly under :func:`case_edition`, and never published to again.

    The one place a case's model is prepared, so every Handle a lane builds
    over one case serves the same literal edition, which is what the case's
    lifecycle oracle asserts (`m-conformance-adapter`).
    """
    return ServingModel(prepare_model(load_case_domain_model(case), edition=case_edition(case)))


def case_entity(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata ``name`` denotes in ``model``.

    A case names an Entity by the spelling its own model authored — bare when
    that is unambiguous, canonical otherwise — which is exactly the QUERY
    REFERENCE rule :func:`~parallax.core.metamodel.entity_by_name` adjudicates,
    so a case's spelling resolves here the way every validator and lowering site
    resolves one.

    A miss is a ``KeyError``: it is a lookup that found nothing, and every lane
    already translates one into an :class:`EngineError` naming the case file, so
    a corpus defect reports the case rather than an engine frame.
    """
    metadata = entity_by_name(model, name)
    if metadata is None:
        raise KeyError(f"{name!r} names no entity the accepted model declares")
    return metadata


def declaring_metadata(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata of the position that DECLARES ``name``'s family
    facts — its family root, itself for a standalone Entity.

    Temporality is family-wide and root-owned (`m-inheritance` "Inherited
    members"), so a read's pin resolves through the root rather than through a
    concrete descendant's own (locally empty) declaration.
    """
    return family_declarer(model, case_entity(model, name))


def family_declarer(model: AcceptedMetamodel, entity: EntityMetadata) -> EntityMetadata:
    """``entity``'s family root, which owns the family-wide declarations.

    A standalone Entity is its own root, so this is the identity there rather
    than a second code path.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise EngineError(f"{entity.identity.canonical!r} names no entity the model declares")
    root = model.entity(view.root)
    if root is None:  # pragma: no cover - a family root is an accepted Entity
        raise EngineError(f"{view.root.canonical!r} names no entity the model declares")
    return root


def default_family_root(model: AcceptedMetamodel) -> EntityMetadata | None:
    """The family root the default-target conventions resolve through.

    ``None`` when the model declares no inheritance family at all, so a caller
    falls back to the model document's own first entity
    (:func:`first_declared_entity`). A model declaring SEVERAL families
    has no single root to name, and picking one of them would silently target an
    entity the case never asked for, so it is refused: the conventions all
    say "the family root", singular, and a case over such a model must name its
    target explicitly.

    A family is read off the Inheritance Facet: every participant's view carries
    the root's own strategy, and a standalone Entity carries none, so the
    strategy-bearing views' distinct roots ARE the model's families.
    """
    facet = inheritance.view(model)
    roots = {
        entity.identity: view.root
        for entity in model.entities
        if (view := facet.entity(entity.identity)) is not None and view.strategy is not None
    }
    distinct = set(roots.values())
    if not distinct:
        return None
    if len(distinct) > 1:
        raise EngineError(
            "the case's model declares no single inheritance family root; a case whose "
            "`when` names no explicit target has no default to resolve against a model "
            "carrying several families"
        )
    root = model.entity(next(iter(distinct)))
    if root is None:  # pragma: no cover - a family root is an accepted Entity
        raise EngineError("the case's model names a family root it does not declare")
    return root


def first_declared_entity(case: case_format.Case) -> str:
    """The canonical spelling of the Entity a case's model document declares
    FIRST.

    `m-case-format` fixes the default target of a case naming none as the
    family root, "else — when it declares no family at all — its own first
    entity". That is the DOCUMENT's order: the accepted model enumerates its
    Entities canonically, so the authored order survives nowhere else. Of the
    cases that reach this convention, one resolves to a different Entity under
    each reading — ``m-predicate-048`` over ``shared-local-name`` — and it is
    refused by the same rule either way, so no case grades the difference.

    The ORDER is the document's; the SPELLING is canonical
    (:func:`~parallax.conformance.models.declared_entity_spellings`), because a
    convention resolving a target the case never named must land on the Entity
    it selected rather than re-enter the bare-name rule that adjudicates an
    AUTHORED reference.
    """
    spellings = models.declared_entity_spellings(models.read_document(_case_model_path(case)))
    if not spellings:  # pragma: no cover - a formed model declares at least one entity
        raise EngineError(f"{case.path.name}: the case's model declares no entity")
    return spellings[0]


def canonicalize_read(
    query: ObjectQueryNode,
    entity: EntityMetadata,
    model: AcceptedMetamodel,
    *,
    form: Literal["rows", "graph"] = "graph",
) -> ValidatedEntityQuery:
    """Preflight and plan one flat root Entity Query.

    The gate is production's own (`handle.preflight`), including Deferred
    Execution Feature classification: an adapter whose compile lane accepted a
    query its own executor would refuse would claim two different supported
    surfaces. ``m-deep-fetch`` then composes temporal injection plus navigation
    canonicalization before SQL sees the result.
    """
    validated = preflight(query, model=model, form=form)
    projection = deep_fetch.ReadProjectionRequest(
        "none" if form == "rows" else "all",
        form == "graph",
    )
    return deep_fetch.plan(validated, model, projection=projection).root
