"""Shared core-schema loading and the cross-file ``$ref`` registry.

``compatibility-case.schema.json`` references the canonical write-instruction
``$defs`` (``write-instruction.schema.json``) across files rather than redefining
them (m-unit-work / m-case-format). Every validator built from a schema that
carries such a cross-file ``$ref`` MUST resolve it through a
:class:`referencing.Registry` keyed by each schema's ``$id`` — a bare
``Draft202012Validator(schema)`` cannot reach another file. This module is the one
place that loads the core schemas and wires that registry, so the main
``schema_validate`` entrypoint and the DB-free schema fidelity tests resolve
cross-file references identically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .paths import schemas_dir

SCHEMA_FILES = (
    "metamodel.schema.json",
    "operation.schema.json",
    "compatibility-case.schema.json",
    "conformance-adapter.schema.json",
    "write-instruction.schema.json",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schemas(start: Path) -> dict[str, dict[str, Any]]:
    """Load every core schema, keyed by filename, from the ``core/schemas`` dir.

    *start* is any path under ``core/`` (e.g. ``core/compatibility``); the schemas
    directory is resolved relative to it, exactly as the command-line entrypoints
    already locate it.
    """
    schemas = schemas_dir(start)
    return {name: load_json(schemas / name) for name in SCHEMA_FILES}


def build_registry(schemas_by_name: dict[str, dict[str, Any]]) -> Registry:
    """Build a ``$id``-keyed registry so cross-file ``$ref``s resolve.

    A relative ``$ref`` (e.g. ``write-instruction.schema.json#/$defs/writeTarget``)
    resolves against the referring schema's ``$id`` base URI, so every schema is
    registered under its own ``$id``.
    """
    resources = [
        (schema["$id"], Resource.from_contents(schema))
        for schema in schemas_by_name.values()
        if isinstance(schema, dict) and "$id" in schema
    ]
    return Registry().with_resources(resources)


def registry_for(start: Path) -> tuple[dict[str, dict[str, Any]], Registry]:
    """Return ``(schemas_by_name, registry)`` for the core schemas under *start*."""
    schemas = load_schemas(start)
    return schemas, build_registry(schemas)


def validator_for(schema: dict[str, Any], registry: Registry) -> Draft202012Validator:
    """A Draft 2020-12 validator whose cross-file ``$ref``s resolve via *registry*."""
    return Draft202012Validator(schema, registry=registry)
