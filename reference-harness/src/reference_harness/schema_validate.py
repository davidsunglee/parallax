"""Schema validation: the schemas are valid, and every fixture conforms.

Run as a module against the compatibility tree::

    uv run python -m reference_harness.schema_validate ../core/compatibility

It performs m-case-format layer 1 statically (no database needed):

* **Meta-schema validation** — each core schema is itself a valid JSON Schema
  (Draft 2020-12).
* **Descriptor validation** — every model under ``models/`` validates against the
  metamodel schema.
* **Operation validation** — every case's ``when.operation`` (and each
  scenario/coherence step's ``find``) validates against the operation schema.
* **Case validation** — every case validates against the compatibility-case
  schema, and its referenced model + golden-SQL dialect keys are coherent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .inheritance import Family, validate_family_defs
from .paths import schemas_dir
from .value_object_resolve import RejectionError

_SCHEMA_FILES = (
    "metamodel.schema.json",
    "operation.schema.json",
    "compatibility-case.schema.json",
    "conformance-adapter.schema.json",
)


class ValidationFailure(Exception):
    """Raised with a human-readable list of problems."""


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_schemas(schemas: Path) -> dict[str, dict[str, Any]]:
    return {name: _load_json(schemas / name) for name in _SCHEMA_FILES}


def _validate(instance: Any, schema: dict[str, Any], label: str, errors: list[str]) -> None:
    validator = Draft202012Validator(schema)
    found = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if found:
        match = best_match(found)
        location = "/".join(str(p) for p in match.absolute_path) or "<root>"
        errors.append(f"{label}: at {location}: {match.message}")


def _descriptor_entity_defs(descriptor: Any) -> list[dict[str, Any]]:
    """Lift a descriptor (single ``entity`` or ``entities`` list) to a flat list."""
    if not isinstance(descriptor, dict):
        return []
    if "entities" in descriptor:
        entities = descriptor.get("entities")
        return [d for d in entities if isinstance(d, dict)] if isinstance(entities, list) else []
    entity = descriptor.get("entity")
    return [entity] if isinstance(entity, dict) else []


# --- targetEntity consistency (m-case-format, resolved Q1; m-inheritance) ----
#
# A read names the entity it targets with `targetEntity`; the class part of every
# queried-entity reference in the operation MUST be CONSISTENT with it. This is the
# structural invariant that makes the read-targeting migration self-verifying. It
# is FAMILY-AWARE (m-inheritance): a reference class is consistent when its
# effective concrete-subtype set is a subset of the target's — an abstract root
# names its whole family, an abstract subtype its concrete descendants, a concrete
# subtype itself. For a non-inheritance entity the effective set is the entity
# itself, so "subset" reduces to "equal" (the pre-inheritance meaning). A
# navigation's INNER operation resolves against the RELATED entity, so it is
# intentionally not descended into.

_ATTR_REF_TAGS = frozenset(
    {
        "eq",
        "notEq",
        "greaterThan",
        "greaterThanEquals",
        "lessThan",
        "lessThanEquals",
        "between",
        "isNull",
        "isNotNull",
        "like",
        "notLike",
        "startsWith",
        "endsWith",
        "contains",
        "in",
        "notIn",
    }
)
_PATH_REF_TAGS = frozenset(
    {
        "nestedEq",
        "nestedNotEq",
        "nestedGt",
        "nestedGte",
        "nestedLt",
        "nestedLte",
        "nestedIn",
        "nestedIsNull",
        "nestedIsNotNull",
        "nestedExists",
        "nestedNotExists",
    }
)


def _class_of(ref: Any) -> str | None:
    if not isinstance(ref, str) or "." not in ref:
        return None
    return ref.split(".", 1)[0]


def _collect_queried_classes(node: Any, acc: set[str]) -> None:
    """Collect the class part of every QUERIED-ENTITY reference in *node*.

    Descends through the same-entity boolean combinators, the result / temporal
    directive wrappers, and (for a deep fetch) the operand plus each path's FIRST
    hop — but NOT a navigation's inner operation, which resolves against the
    related entity.
    """
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag == "deepFetch":
        if isinstance(body, dict):
            _collect_queried_classes(body.get("operand"), acc)
            for path in body.get("paths", []) or []:
                if path:
                    segment = path[0]
                    rel = segment.get("rel") if isinstance(segment, dict) else segment
                    cls = _class_of(rel)
                    if cls:
                        acc.add(cls)
        return
    if not isinstance(body, dict):
        return
    if tag in _ATTR_REF_TAGS:
        cls = _class_of(body.get("attr"))
        if cls:
            acc.add(cls)
    elif tag in _PATH_REF_TAGS:
        cls = _class_of(body.get("path"))
        if cls:
            acc.add(cls)
    elif tag in ("navigate", "exists", "notExists"):
        cls = _class_of(body.get("rel"))
        if cls:
            acc.add(cls)
    elif tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            _collect_queried_classes(operand, acc)
    elif tag in ("not", "group", "distinct", "asOf", "asOfRange", "history", "limit"):
        _collect_queried_classes(body.get("operand"), acc)
    elif tag == "orderBy":
        _collect_queried_classes(body.get("operand"), acc)
        for key in body.get("keys", []) or []:
            if isinstance(key, dict):
                cls = _class_of(key.get("attr"))
                if cls:
                    acc.add(cls)
    elif tag == "groupBy":
        _collect_queried_classes(body.get("operand"), acc)
        for key in body.get("keys", []) or []:
            cls = _class_of(key)
            if cls:
                acc.add(cls)
        for aggregate in body.get("aggregates", []) or []:
            if isinstance(aggregate, dict) and len(aggregate) == 1:
                inner = next(iter(aggregate.values()))
                if isinstance(inner, dict):
                    cls = _class_of(inner.get("attr"))
                    if cls:
                        acc.add(cls)
    # all / none carry no queried-entity reference.


def _check_target_entity(
    operation: Any,
    target_entity: Any,
    family: Family | None,
    label: str,
    errors: list[str],
) -> None:
    """Assert every queried-entity reference class is family-consistent with *target_entity*."""
    if not isinstance(target_entity, str):
        return  # a missing / malformed targetEntity is already a schema error
    classes: set[str] = set()
    _collect_queried_classes(operation, classes)

    def effective(name: str) -> set[str]:
        return set(family.effective_concrete_set(name)) if family is not None else {name}

    target_set = effective(target_entity)
    inconsistent = sorted(cls for cls in classes if not (effective(cls) <= target_set))
    if inconsistent:
        errors.append(
            f"{label}: targetEntity {target_entity!r} is inconsistent with the "
            f"queried-entity reference class(es) {inconsistent}"
        )


def validate_tree(compatibility_root: Path) -> list[str]:
    """Validate every schema and every fixture; return a list of error strings."""
    compatibility_root = compatibility_root.resolve()
    schemas = schemas_dir(compatibility_root)
    schema_map = _load_schemas(schemas)
    errors: list[str] = []

    # 1. The schemas themselves are valid JSON Schema documents.
    for name, schema in schema_map.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - surface any meta-schema problem
            errors.append(f"meta-schema: {name} is not a valid JSON Schema: {exc}")

    metamodel_schema = schema_map["metamodel.schema.json"]
    operation_schema = schema_map["operation.schema.json"]
    case_schema = schema_map["compatibility-case.schema.json"]

    # 2. Every model descriptor validates against the metamodel schema AND, if it
    #    declares an inheritance family, satisfies the cross-entity closed-tree
    #    invariants the per-entity schema cannot express (m-inheritance). A family
    #    resolver per model backs the family-aware targetEntity cross-check below.
    models_dir = compatibility_root / "models"
    families: dict[str, Family] = {}
    for model_path in sorted(models_dir.glob("**/*.y*ml")):
        descriptor = _load_yaml(model_path)
        _validate(descriptor, metamodel_schema, f"model {model_path.name}", errors)
        entity_defs = _descriptor_entity_defs(descriptor)
        families[model_path.name] = Family(entity_defs)
        try:
            validate_family_defs(entity_defs)
        except RejectionError as exc:
            errors.append(f"model {model_path.name}: {exc.rule}: {exc.detail}")

    # 3. Every case + its operation validate against their schemas.
    cases_dir = compatibility_root / "cases"
    for case_path in sorted(cases_dir.glob("**/*.y*ml")):
        case = _load_yaml(case_path)
        model_rel = case.get("model") if isinstance(case, dict) else None
        model_name = Path(model_rel).name if isinstance(model_rel, str) else None
        family = families.get(model_name) if model_name is not None else None
        _validate(case, case_schema, f"case {case_path.name}", errors)
        # The action under test lives under `when`; a read case's operation and a
        # scenario/coherence step's `find` are canonical m-op-algebra nodes that
        # must also validate against the operation algebra schema.
        when = case.get("when") if isinstance(case, dict) else None
        when = when if isinstance(when, dict) else {}
        if "operation" in when:
            _validate(
                when["operation"],
                operation_schema,
                f"case {case_path.name} operation",
                errors,
            )
            # A read case names its queried entity with `targetEntity`; cross-check it
            # against the operation's queried-entity references (m-case-format Q1).
            if case.get("shape") == "read":
                _check_target_entity(
                    when["operation"],
                    when.get("targetEntity"),
                    family,
                    f"case {case_path.name}",
                    errors,
                )
        # A scenario case carries its operations per step (under `when.scenario[].find`);
        # each one must also validate against the operation algebra schema.
        if isinstance(when.get("scenario"), list):
            for index, step in enumerate(when["scenario"]):
                if isinstance(step, dict) and "find" in step:
                    _validate(
                        step["find"],
                        operation_schema,
                        f"case {case_path.name} scenario[{index}].find",
                        errors,
                    )
                    _check_target_entity(
                        step["find"],
                        step.get("targetEntity"),
                        family,
                        f"case {case_path.name} scenario[{index}].find",
                        errors,
                    )
        # A coherence case (Phase 11) likewise carries read-step operations under
        # `when.coherence[].find`; each must validate against the operation algebra schema.
        if isinstance(when.get("coherence"), list):
            for index, step in enumerate(when["coherence"]):
                if isinstance(step, dict) and "find" in step:
                    _validate(
                        step["find"],
                        operation_schema,
                        f"case {case_path.name} coherence[{index}].find",
                        errors,
                    )
                    _check_target_entity(
                        step["find"],
                        step.get("targetEntity"),
                        family,
                        f"case {case_path.name} coherence[{index}].find",
                        errors,
                    )
        # The referenced model must exist.
        if isinstance(case, dict) and isinstance(case.get("model"), str):
            referenced = compatibility_root / case["model"]
            if not referenced.is_file():
                errors.append(f"case {case_path.name}: model {case['model']} does not exist")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.schema_validate <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(argv[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    errors = validate_tree(compatibility_root)
    if errors:
        print(f"schema validation FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("schema validation OK: all schemas and fixtures conform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
