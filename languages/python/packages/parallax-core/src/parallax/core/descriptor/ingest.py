"""Three-phase descriptor ingestion (m-descriptor "Descriptor ingestion").

Ingestion is a fixed three-phase contract: syntax, then schema, then value.
Each phase either passes the document forward or fails with that phase's own
error; no phase reports another phase's failures, no failing phase produces an
Unresolved Metamodel, and only a document every phase accepts reaches the
adapter (:func:`~parallax.core.descriptor.unresolved.unresolved_metamodel`) for
semantic formation.

The schema phase (phase 2) evaluates the whole document against
``core/schemas/metamodel.schema.json`` (JSON Schema Draft 2020-12) with
``jsonschema``. That dependency is imported lazily, function-local: the
descriptor scope ships inside ``parallax-core``, whose declared runtime
manifest is ``pydantic`` and ``pyyaml`` alone (`spec/python.md` §8) — text
ingestion (this module) runs only in the development-only conformance harness,
which declares ``jsonschema`` for itself.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from jsonschema.protocols import Validator

from parallax.core.descriptor.errors import (
    DescriptorSchemaError,
    DescriptorSchemaViolation,
    DescriptorSyntaxError,
    DescriptorValueError,
    DescriptorValueViolation,
    canonical_schema_violations,
    canonical_value_violations,
)
from parallax.core.descriptor.records import Metamodel
from parallax.core.descriptor.serde import parse_document
from parallax.core.descriptor.type_spelling import parse_type_spelling
from parallax.core.descriptor.unresolved import unresolved_metamodel
from parallax.core.metamodel import UnresolvedMetamodel

__all__ = ["ingest_document", "parse_json", "parse_yaml"]


def parse_json(text: str) -> UnresolvedMetamodel:
    """Ingest a JSON descriptor document through every ingestion phase.

    Raises :class:`~parallax.core.descriptor.errors.DescriptorSyntaxError` on
    malformed JSON, :class:`~parallax.core.descriptor.errors.DescriptorSchemaError`
    on a canonical-schema violation, and
    :class:`~parallax.core.descriptor.errors.DescriptorValueError` on a
    schema-valid but unconstructible value. No model forms before every phase
    succeeds.
    """
    return unresolved_metamodel(ingest_document(_decode_json(text)))


def parse_yaml(text: str) -> UnresolvedMetamodel:
    """Ingest a YAML descriptor document through every ingestion phase — the
    YAML sibling of :func:`parse_json`."""
    return unresolved_metamodel(ingest_document(_decode_yaml(text)))


def ingest_document(document: object) -> Metamodel:
    """Run the schema (phase 2) and value (phase 3) ingestion phases over an
    already-decoded document, returning its parsed, reference-unresolved
    records.

    Schema validation runs first and reports every violation the canonical
    schema finds over the whole document; only a schema-valid document reaches
    the value phase, which reports every schema-valid but unconstructible
    ``type`` spelling. Reference resolution, relationship pairing, and every
    other semantic question belong to Model Formation, reached later by
    passing this function's result to
    :func:`~parallax.core.descriptor.unresolved.unresolved_metamodel` and the
    foundational resolver.
    """
    _validate_schema(document)
    mapping = cast("Mapping[str, object]", document)
    violations = _type_spelling_violations(mapping)
    if violations:
        raise DescriptorValueError(canonical_value_violations(violations))
    return parse_document(mapping)


# --------------------------------------------------------------------------- #
# Phase 1 — syntax.                                                           #
# --------------------------------------------------------------------------- #
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
def _schema_path() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        schema = candidate / "core" / "schemas" / "metamodel.schema.json"
        if schema.is_file():
            return schema
    raise FileNotFoundError(
        f"core/schemas/metamodel.schema.json not found above {here}; descriptor "
        "schema validation requires a Parallax repository checkout"
    )


@functools.cache
def _validator() -> Validator:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError(
            "descriptor schema validation (m-descriptor ingestion phase 2) requires "
            "the optional `jsonschema` dependency, which `parallax-core` does not "
            "declare (spec/python.md §8); install it directly, or install "
            "`parallax-conformance`, which declares it, to ingest descriptor text"
        ) from exc
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


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
