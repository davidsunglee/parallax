from __future__ import annotations

import json
from collections.abc import Mapping

import yaml

from parallax.core.entity._model import DomainModel, model_of
from parallax.core.metamodel import UnresolvedMetamodel
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._export import DescriptorExportError, ExportTarget
from parallax.descriptor._export import export_document as _document_of_model
from parallax.descriptor._ingest import ingest_document, parse_json, parse_yaml

__all__ = [
    "domain_model_from_document",
    "domain_model_from_json",
    "domain_model_from_yaml",
    "export_document",
    "export_json",
    "export_yaml",
]


def domain_model_from_document(document: Mapping[str, object]) -> DomainModel:
    """Seal an already-decoded descriptor ``document`` into a hub.

    Schema validation is the first gate, so this door never raises
    :class:`~parallax.descriptor.DescriptorSyntaxError`. Otherwise the phase
    order is the one every door shares:
    :class:`~parallax.descriptor.DescriptorSchemaError` for a canonical-schema
    violation, then :class:`~parallax.descriptor.DescriptorValueError` for a
    schema-valid but unconstructible value — both before any hub exists — and
    finally :class:`~parallax.core.model_formation.MetamodelValidationError` for
    every semantic model rule, still inside this call. The document uses the
    schema's two top-level forms: ``entity:`` for one Entity or ``entities:``
    for several.

    Ingestion converts the accepted input into immutable descriptor-owned
    records and retains no caller-owned mutable document, and the returned hub
    is sealed by construction. Repeated calls over one document yield
    structurally equal models.
    """
    return _sealed(unresolved_metamodel(ingest_document(document)))


def domain_model_from_json(text: str | bytes) -> DomainModel:
    """Seal a JSON descriptor document into a hub.

    ``text`` is JSON source, decoded as UTF-8 when supplied as bytes. Adds phase
    1 to :func:`domain_model_from_document`'s contract: undecodable bytes or
    malformed JSON raise :class:`~parallax.descriptor.DescriptorSyntaxError`
    with ``format="json"`` before any later phase runs.
    """
    return _sealed(parse_json(text))


def domain_model_from_yaml(text: str | bytes) -> DomainModel:
    """Seal a YAML descriptor document into a hub — the YAML sibling of
    :func:`domain_model_from_json`, reporting ``format="yaml"``."""
    return _sealed(parse_yaml(text))


def export_document(model: DomainModel) -> dict[str, object]:
    """The canonical minimal descriptor document for ``model``'s sealed model.

    A fresh tree of ordinary mappings, lists, and JSON-compatible scalar values
    each call. Every hub is sealed by construction, so export performs no
    hub-state check and has no state failure to propagate; it renews no
    validation, performs no state change, and retains no descriptor cache.
    Repeated results are structurally equal. A conversion defect raises
    :class:`~parallax.descriptor.DescriptorExportError` with target ``document``
    and the original cause, returns no partial output, and leaves ``model``
    unchanged.
    """
    return _document_of_model(model_of(model))


def export_json(model: DomainModel) -> str:
    """``model``'s canonical descriptor document as JSON text.

    Deterministic: repeated results are byte-identical, and key order is the
    canonical document's own authoring order rather than a sorted rewrite. Adds
    the serialization step to :func:`export_document`'s contract; a defect in
    that step raises :class:`~parallax.descriptor.DescriptorExportError` with
    target ``json``, while a conversion defect keeps the target
    :func:`export_document` reported.
    """
    return _text(model, "json")


def export_yaml(model: DomainModel) -> str:
    """``model``'s canonical descriptor document as YAML text — the YAML
    sibling of :func:`export_json`, reporting target ``yaml``."""
    return _text(model, "yaml")


def _sealed(source: UnresolvedMetamodel) -> DomainModel:
    return DomainModel._from_unresolved(source)  # pyright: ignore[reportPrivateUsage] - first-party seam calls the hub's own private constructor


def _text(model: DomainModel, target: ExportTarget) -> str:
    """One canonical document rendered in ``target``'s concrete syntax.

    :func:`export_document` already reports a conversion defect as
    ``target="document"``; re-wrapping here would mislabel it, so only the
    serialization step is guarded and it reports the text target the caller
    asked for.
    """
    document = export_document(model)
    try:
        if target == "json":
            return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    except Exception as error:
        raise DescriptorExportError(target, error) from error
