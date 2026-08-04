"""Three-phase descriptor ingestion (m-descriptor "Descriptor ingestion").

Ingestion is a fixed three-phase contract: syntax, then schema, then value.
Each phase either passes the document forward or fails with that phase's own
error; no phase reports another phase's failures, no failing phase produces an
Unresolved Metamodel, and only a document every phase accepts reaches the
adapter (:func:`~parallax.descriptor._adapter.unresolved_metamodel`) for
semantic formation.

The schema phase (phase 2) evaluates the whole document against the canonical
``metamodel.schema.json`` (JSON Schema Draft 2020-12) with ``jsonschema``, which
``parallax-descriptor`` declares directly alongside ``pyyaml``, so every
installed Descriptor Frontend can execute all three phases and neither
dependency has an optional-import failure branch. The schema itself is read from
this distribution's own packaged copy through :mod:`importlib.resources`;
installed runtime code never searches repository-relative paths.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping
from importlib import resources
from typing import Any, cast

import jsonschema
import yaml
from jsonschema.protocols import Validator

from parallax.core.metamodel import UnresolvedMetamodel
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._errors import (
    DescriptorFormat,
    DescriptorSchemaError,
    DescriptorSchemaViolation,
    DescriptorSyntaxError,
    DescriptorValueError,
    DescriptorValueViolation,
    canonical_schema_violations,
    canonical_value_violations,
)
from parallax.descriptor._records import Metamodel
from parallax.descriptor._serde import parse_document
from parallax.descriptor._type_spelling import parse_type_spelling

__all__ = ["SCHEMA_RESOURCE", "ingest_document", "parse_json", "parse_yaml", "schema_text"]

SCHEMA_RESOURCE: str = "_schemas/metamodel.schema.json"
"""This distribution's packaged copy of the canonical metamodel schema.

A path relative to the ``parallax.descriptor`` package. The language-neutral
``core/schemas/metamodel.schema.json`` remains authoritative; the packaged copy
is byte-for-byte identical and is what an installed frontend validates against.
"""


def schema_text() -> str:
    """The packaged canonical metamodel schema, read as UTF-8 text."""
    return resources.files("parallax.descriptor").joinpath(SCHEMA_RESOURCE).read_text("utf-8")


def parse_json(text: str | bytes) -> UnresolvedMetamodel:
    """Ingest a JSON descriptor document through every ingestion phase.

    ``text`` is JSON source, decoded as UTF-8 when supplied as bytes. Raises
    :class:`~parallax.descriptor._errors.DescriptorSyntaxError` on undecodable
    bytes or malformed JSON,
    :class:`~parallax.descriptor._errors.DescriptorSchemaError` on a
    canonical-schema violation, and
    :class:`~parallax.descriptor._errors.DescriptorValueError` on a
    schema-valid but unconstructible value. No model forms before every phase
    succeeds.
    """
    return unresolved_metamodel(ingest_document(_decode_json(_utf8(text, "json"))))


def parse_yaml(text: str | bytes) -> UnresolvedMetamodel:
    """Ingest a YAML descriptor document through every ingestion phase — the
    YAML sibling of :func:`parse_json`."""
    return unresolved_metamodel(ingest_document(_decode_yaml(_utf8(text, "yaml"))))


def ingest_document(document: object) -> Metamodel:
    """Run the schema (phase 2) and value (phase 3) ingestion phases over an
    already-decoded document, returning its parsed, reference-unresolved
    records.

    Schema validation runs first and reports every violation the canonical
    schema finds over the whole document; only a schema-valid document reaches
    the value phase, which reports every schema-valid but unconstructible
    ``type`` spelling and every authored Index component naming an As-Of Axis
    endpoint. Reference resolution, relationship pairing, and every
    other semantic question belong to Model Formation, reached later by
    passing this function's result to
    :func:`~parallax.descriptor._adapter.unresolved_metamodel` and the
    foundational resolver.
    """
    _validate_schema(document)
    mapping = cast("Mapping[str, object]", document)
    violations = (*_type_spelling_violations(mapping), *_index_temporal_violations(mapping))
    if violations:
        raise DescriptorValueError(canonical_value_violations(violations))
    return parse_document(mapping)


# --------------------------------------------------------------------------- #
# Phase 1 — syntax.                                                           #
# --------------------------------------------------------------------------- #
def _utf8(text: str | bytes, format: DescriptorFormat) -> str:
    """``text`` as source text, decoding bytes as UTF-8.

    Undecodable bytes are a syntax failure of the declared format, not a
    separate error family: the caller handed over source it called JSON or YAML,
    and it is not well-formed in that format's encoding.
    """
    if isinstance(text, str):
        return text
    try:
        return text.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DescriptorSyntaxError(format, cause=exc) from exc


def _decode_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DescriptorSyntaxError("json", line=exc.lineno, column=exc.colno, cause=exc) from exc


def _decode_yaml(text: str) -> object:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = None if mark is None else mark.line + 1
        column = None if mark is None else mark.column + 1
        raise DescriptorSyntaxError("yaml", line=line, column=column, cause=exc) from exc


# --------------------------------------------------------------------------- #
# Phase 2 — schema.                                                           #
# --------------------------------------------------------------------------- #
@functools.cache
def _validator() -> Validator:
    return jsonschema.Draft202012Validator(json.loads(schema_text()))


def _validate_schema(document: object) -> None:
    errors = list(_validator().iter_errors(cast("Any", document)))
    if not errors:
        return
    violations = (
        DescriptorSchemaViolation(
            path=tuple(error.absolute_path), rule=str(error.validator), message=error.message
        )
        for error in errors
    )
    raise DescriptorSchemaError(canonical_schema_violations(violations))


# --------------------------------------------------------------------------- #
# Phase 3 — value.                                                            #
# --------------------------------------------------------------------------- #
def _type_spelling_violations(
    document: Mapping[str, object],
) -> tuple[DescriptorValueViolation, ...]:
    """Every schema-valid but unconstructible ``type`` spelling in ``document``.

    Walks every entity attribute and every Value Object attribute, nested to
    arbitrary depth, over the document's own authored ``entity``/``entities``
    form — the schema phase already guarantees exactly one of those two forms
    is present and every list it names is well-shaped.
    """
    return tuple(
        violation
        for prefix, entity in _entities(document)
        for violation in _entity_type_violations(entity, prefix)
    )


def _index_temporal_violations(
    document: Mapping[str, object],
) -> tuple[DescriptorValueViolation, ...]:
    """Every authored Index component naming an As-Of Axis endpoint.

    The physical key over the axis endpoints is derived, so an authored Index
    naming one either restates it in an author-chosen position or contradicts it.
    Each offending component is one violation at its own document path.
    """
    return tuple(
        violation
        for prefix, entity in _entities(document)
        for violation in _entity_index_temporal_violations(entity, prefix)
    )


def _entity_index_temporal_violations(
    entity: Mapping[str, object], prefix: tuple[str | int, ...]
) -> list[DescriptorValueViolation]:
    """``entity``'s offending Index components, in document order.

    The schema phase has already fixed every shape read here: an ``asOfAxes``
    entry names both endpoints and an ``indices`` entry names a nonempty
    component list, so only their presence is tested.
    """
    axes = cast("list[Mapping[str, str]]", entity.get("asOfAxes", ()))
    endpoints = {axis[key] for axis in axes for key in ("startAttribute", "endAttribute")}
    indices = cast("list[Mapping[str, Any]]", entity.get("indices", ()))
    return [
        DescriptorValueViolation(
            path=(*prefix, "indices", position, "attributes", offset),
            rule="index-temporal-attribute",
            message=(
                f"index component {component!r} is an as-of axis endpoint; "
                "the physical key over the axis endpoints is derived"
            ),
        )
        for position, index in enumerate(indices)
        for offset, component in enumerate(cast("list[str]", index["attributes"]))
        if component in endpoints
    ]


def _entities(
    document: Mapping[str, object],
) -> list[tuple[tuple[str | int, ...], Mapping[str, object]]]:
    if "entity" in document:
        return [(("entity",), cast("Mapping[str, object]", document["entity"]))]
    entities = cast("list[object]", document["entities"])
    return [
        (("entities", index), cast("Mapping[str, object]", item))
        for index, item in enumerate(entities)
    ]


def _entity_type_violations(
    entity: Mapping[str, object], prefix: tuple[str | int, ...]
) -> list[DescriptorValueViolation]:
    violations = _attribute_violations(entity.get("attributes"), prefix)
    value_objects = entity.get("valueObjects")
    if isinstance(value_objects, list):
        for index, occurrence in enumerate(cast("list[object]", value_objects)):
            violations.extend(
                _value_object_violations(
                    cast("Mapping[str, object]", occurrence), (*prefix, "valueObjects", index)
                )
            )
    return violations


def _value_object_violations(
    occurrence: Mapping[str, object], prefix: tuple[str | int, ...]
) -> list[DescriptorValueViolation]:
    violations = _attribute_violations(occurrence.get("attributes"), prefix)
    nested = occurrence.get("valueObjects")
    if isinstance(nested, list):
        for index, item in enumerate(cast("list[object]", nested)):
            violations.extend(
                _value_object_violations(
                    cast("Mapping[str, object]", item), (*prefix, "valueObjects", index)
                )
            )
    return violations


def _attribute_violations(
    attributes: object, prefix: tuple[str | int, ...]
) -> list[DescriptorValueViolation]:
    if not isinstance(attributes, list):
        return []
    violations: list[DescriptorValueViolation] = []
    for index, attribute in enumerate(cast("list[object]", attributes)):
        spelling = cast("Mapping[str, object]", attribute).get("type")
        if isinstance(spelling, str) and parse_type_spelling(spelling) is None:
            violations.append(
                DescriptorValueViolation(
                    path=(*prefix, "attributes", index, "type"),
                    rule="type-spelling-invalid",
                    message=f"{spelling!r} does not denote a constructible neutral type",
                )
            )
    return violations
