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

import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry

from .case import Entity
from .inheritance import Family, resolve_effective_definition, validate_family_defs
from .operation_references import collect_reference_classes
from .predicate_write_validate import (
    PredicateWriteValidationError,
    validate_predicate_write,
    validate_predicate_write_materialization,
)
from .schemas import build_registry, load_schemas
from .value_object_resolve import RejectionError


class ValidationFailure(Exception):
    """Raised with a human-readable list of problems."""


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validation_error(
    instance: Any, schema: dict[str, Any], registry: Registry | None = None
) -> str | None:
    """Return the most relevant JSON Schema failure, or ``None`` when valid.

    *registry* resolves cross-file ``$ref``s (the case schema references the
    canonical write-instruction ``$defs``); a bare validator cannot reach another
    file, so callers validating the case schema MUST pass it.
    """
    validator = (
        Draft202012Validator(schema, registry=registry)
        if registry is not None
        else Draft202012Validator(schema)
    )
    found = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if not found:
        return None
    match = best_match(found)
    location = "/".join(str(p) for p in match.absolute_path) or "<root>"
    return f"at {location}: {match.message}"


def _validate(
    instance: Any,
    schema: dict[str, Any],
    label: str,
    errors: list[str],
    registry: Registry | None = None,
) -> None:
    problem = validation_error(instance, schema, registry)
    if problem is not None:
        errors.append(f"{label}: {problem}")


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
    collect_reference_classes(operation, classes, descend_result_modifiers=True)

    def effective(name: str) -> set[str]:
        return set(family.effective_concrete_set(name)) if family is not None else {name}

    target_set = effective(target_entity)
    inconsistent = sorted(cls for cls in classes if not (effective(cls) <= target_set))
    if inconsistent:
        errors.append(
            f"{label}: targetEntity {target_entity!r} is inconsistent with the "
            f"queried-entity reference class(es) {inconsistent}"
        )


def _scenario_reference_sql_dialect_keys(
    step: dict[str, Any], label: str, errors: list[str]
) -> None:
    """Ensure a scenario read's dialect map covers its golden statement maps.

    This is the scenario-local counterpart to the runner's top-level
    ``then.referenceSql`` key check.  A plain string is dialect-neutral.  A map
    must cover exactly the dialects this read step can execute, otherwise one
    dialect would silently lose its independent oracle.
    """
    reference_sql = step.get("referenceSql")
    if not isinstance(reference_sql, dict):
        return
    statements = step.get("statements")
    if not isinstance(statements, list) or not statements:
        return
    dialect_sets = [
        set(entry["sql"])
        for entry in statements
        if isinstance(entry, dict) and isinstance(entry.get("sql"), dict)
    ]
    if not dialect_sets:
        return
    golden_dialects = set.intersection(*dialect_sets)
    if set(reference_sql) != golden_dialects:
        errors.append(
            f"{label}: referenceSql map keys {sorted(reference_sql)} != scenario golden sql "
            f"map keys {sorted(golden_dialects)}"
        )


def _validate_predicate_write(
    write: Any,
    entity_defs: list[dict[str, Any]],
    operation_schema: dict[str, Any],
    label: str,
    errors: list[str],
) -> Entity | None:
    """Validate the operation and model-dependent parts of one write instruction."""
    if not isinstance(write, dict):
        return None  # legacy string writes remain valid and need no predicate walk
    target = write.get("target")
    if not isinstance(target, dict):
        return None  # the case schema owns missing/malformed target errors
    predicate = target.get("predicate")
    if predicate is not None:
        _validate(predicate, operation_schema, f"{label} target.predicate", errors)
    target_name = target.get("entity")
    if not isinstance(target_name, str):
        return None
    try:
        entity = Entity(definition=resolve_effective_definition(entity_defs, target_name))
    except (KeyError, RejectionError) as exc:
        errors.append(f"{label}: target entity {target_name!r} is not declared: {exc}")
        return None
    try:
        validate_predicate_write(entity, write)
    except PredicateWriteValidationError as exc:
        errors.append(f"{label}: {exc}")
    return entity


def _keyed_member_names(entity_defs: list[dict[str, Any]], entity_name: str) -> set[str] | None:
    """The attribute + value-object names a keyed write row of *entity_name* may name.

    Returns ``None`` when the entity is undeclared (the caller reports that). The
    framework-owned observation is already forbidden on the durable row by the
    canonical schema, so it is not a member name here.
    """
    try:
        definition = resolve_effective_definition(entity_defs, entity_name)
    except (KeyError, RejectionError):
        return None
    names = {
        attribute["name"]
        for attribute in definition.get("attributes", [])
        if isinstance(attribute, dict) and isinstance(attribute.get("name"), str)
    }
    names |= {
        value_object["name"]
        for value_object in definition.get("valueObjects", [])
        if isinstance(value_object, dict) and isinstance(value_object.get("name"), str)
    }
    return names


def _primary_key_names(entity_defs: list[dict[str, Any]], entity_name: str) -> list[str] | None:
    """The primary-key attribute name(s) of *entity_name* (`primaryKey: true`).

    Returns ``None`` when the entity is undeclared (the caller reports that). The
    order follows the descriptor's attribute order, so the identity tuple a buffered
    coalescing pair compares is stable.
    """
    try:
        definition = resolve_effective_definition(entity_defs, entity_name)
    except (KeyError, RejectionError):
        return None
    return [
        attribute["name"]
        for attribute in definition.get("attributes", [])
        if isinstance(attribute, dict)
        and attribute.get("primaryKey") is True
        and isinstance(attribute.get("name"), str)
    ]


def _hashable(value: Any) -> Any:
    """A hashable stand-in for a primary-key value (scalars pass through)."""
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _pk_identities(
    instruction: dict[str, Any], pk_names: list[str]
) -> tuple[frozenset[tuple[Any, ...]], bool]:
    """The set of primary-key identity tuples the keyed instruction's rows name.

    The second element is ``False`` when a row omits a primary-key attribute (so no
    identity can be established — the caller reports it and skips the equality check).
    """
    identities: set[tuple[Any, ...]] = set()
    complete = True
    for row in instruction.get("rows", []):
        if not isinstance(row, dict):
            continue
        if any(name not in row for name in pk_names):
            complete = False
            continue
        identities.add(tuple(_hashable(row[name]) for name in pk_names))
    return frozenset(identities), complete


def _validate_buffered_write(
    instructions: list[Any],
    entity_defs: list[dict[str, Any]],
    operation_schema: dict[str, Any],
    label: str,
    errors: list[str],
) -> None:
    """Validate a buffered scenario write — the m-unit-work coalescing PAIR.

    The schema pins the STRUCTURAL shape (exactly two KEYED instructions: entry 0 a
    keyed ``insert``, entry 1 a keyed ``update`` / ``delete``); this adds the two
    model-aware checks JSON Schema cannot express and the wire harness would otherwise
    skip (it executes the coalesced golden SQL, never the buffered instructions):

    * **member honesty** — each keyed row's keys MUST name declared attributes / value
      objects of its entity, so a buffered write cannot silently name a non-member.
    * **same-object coalescing** — the two entries MUST target the SAME entity and the
      SAME primary-key identity (the object inserted is the object then updated /
      deleted). A pair over two different entities, or two different keys, is NOT a
      coalescing pair and is rejected here.

    A predicate entry is no longer part of the buffered shape (the schema forbids it);
    should a schema-invalid case still carry one, the predicate-write validator reports
    it rather than the keyed member check.
    """
    for position, instruction in enumerate(instructions):
        entry_label = f"{label} buffered write[{position}]"
        if not isinstance(instruction, dict):
            continue  # the case schema owns non-object entries
        if "target" in instruction:
            _validate_predicate_write(
                instruction, entity_defs, operation_schema, entry_label, errors
            )
            continue
        entity_name = instruction.get("entity")
        if not isinstance(entity_name, str):
            continue  # the case schema owns the missing/malformed entity error
        members = _keyed_member_names(entity_defs, entity_name)
        if members is None:
            errors.append(f"{entry_label}: keyed write entity {entity_name!r} is not declared")
            continue
        for row in instruction.get("rows", []):
            if not isinstance(row, dict):
                continue
            unknown = sorted(key for key in row if key not in members)
            if unknown:
                errors.append(
                    f"{entry_label}: keyed write row names {unknown} which are not "
                    f"attributes or value objects of {entity_name}"
                )

    _validate_buffered_coalescing_pair(instructions, entity_defs, label, errors)


def _validate_buffered_coalescing_pair(
    instructions: list[Any],
    entity_defs: list[dict[str, Any]],
    label: str,
    errors: list[str],
) -> None:
    """Enforce the same-entity / same-primary-key equalities JSON Schema cannot express.

    Runs only when the buffer is a well-formed KEYED pair (exactly two keyed, declared
    entries); the schema owns every other structural rejection (wrong length, a
    predicate entry, a non-``insert`` / non-``update``-``delete`` verb), so a malformed
    buffer is left to it rather than double-reported here.
    """
    if len(instructions) != 2:
        return
    first, second = instructions
    if not (isinstance(first, dict) and isinstance(second, dict)):
        return
    if "target" in first or "target" in second:
        return  # a predicate entry is a schema rejection, not a coalescing pair
    first_entity, second_entity = first.get("entity"), second.get("entity")
    if not (isinstance(first_entity, str) and isinstance(second_entity, str)):
        return
    if first_entity != second_entity:
        errors.append(
            f"{label}: buffered coalescing pair must target the SAME entity — the "
            f"inserted object is the one then updated / deleted — but names "
            f"{first_entity!r} then {second_entity!r}"
        )
        return
    pk_names = _primary_key_names(entity_defs, first_entity)
    if not pk_names:
        return  # undeclared entity / no primary key — reported by the member check
    first_ids, first_complete = _pk_identities(first, pk_names)
    second_ids, second_complete = _pk_identities(second, pk_names)
    if not (first_complete and second_complete):
        errors.append(
            f"{label}: buffered coalescing pair must name its primary key "
            f"{pk_names} in every entry so its object identity is explicit"
        )
        return
    if first_ids != second_ids:
        errors.append(
            f"{label}: buffered coalescing pair must target the SAME primary-key "
            f"identity — the inserted object is the one then updated / deleted — but "
            f"names {sorted(first_ids)} then {sorted(second_ids)}"
        )


# --- compile-eligibility backstop (m-case-format / m-conformance-adapter) -----
#
# A case is compile-eligible by default; it is declared RUN-ONLY (a top-level
# `compileEligibility` block) only when its emissions cannot be derived without
# executing SQL. Eligibility is an AUTHORED, reviewed intent declaration, but the
# harness mechanically backstops the DETECTABLE single-connection minority: any case
# that intends database concurrency or locking behavior — a `conflict` /
# `concurrencySuccess` / `boundary` shape, a `when.concurrency` choreography, or a
# `given.apply` / `given.fault` — is run-only regardless of whether its emissions
# happen to be statically derivable, so it MUST carry the declaration. (The
# query-result-dependence criterion is a human judgment the harness cannot detect;
# each language's refusing compile port enforces it structurally at runtime.)

_SINGLE_CONNECTION_SHAPES = frozenset({"conflict", "concurrencySuccess", "boundary"})


def _single_connection_markers(case: dict[str, Any]) -> list[str]:
    """Return the detectable single-connection markers a case carries (empty == none)."""
    markers: list[str] = []
    given = case.get("given")
    if isinstance(given, dict):
        if "apply" in given:
            markers.append("given.apply")
        if "fault" in given:
            markers.append("given.fault")
    when = case.get("when")
    if isinstance(when, dict) and "concurrency" in when:
        markers.append("when.concurrency")
    shape = case.get("shape")
    if shape in _SINGLE_CONNECTION_SHAPES:
        markers.append(f"shape:{shape}")
    return markers


def _check_compile_eligibility(case: Any, label: str, errors: list[str]) -> None:
    """Backstop the DETECTABLE compile-eligibility declarations.

    A case carrying a detectable single-connection marker MUST be declared compile
    run-only with reason ``single-connection``; leaving it compile-eligible (or
    mis-reasoning it) is a loud failure.
    """
    if not isinstance(case, dict):
        return
    markers = _single_connection_markers(case)
    if not markers:
        return
    declaration = case.get("compileEligibility")
    if not (isinstance(declaration, dict) and declaration.get("mode") == "run-only"):
        errors.append(
            f"{label}: carries single-connection compile marker(s) {markers} but is not "
            f"declared compile run-only (add `compileEligibility: {{mode: run-only, "
            f"reason: single-connection}}`)"
        )
        return
    if declaration.get("reason") != "single-connection":
        errors.append(
            f"{label}: single-connection marker(s) {markers} require "
            f"`compileEligibility.reason: single-connection`, not "
            f"{declaration.get('reason')!r}"
        )


def _validate_scenario_reference_sql(
    step: dict[str, Any], case_schema: dict[str, Any], label: str, errors: list[str]
) -> None:
    if "referenceSql" not in step:
        return
    reference_schema = case_schema["$defs"]["referenceSql"]
    _validate(step["referenceSql"], reference_schema, f"{label} referenceSql", errors)
    _scenario_reference_sql_dialect_keys(step, label, errors)


def validate_tree(compatibility_root: Path) -> list[str]:
    """Validate every schema and every fixture; return a list of error strings."""
    compatibility_root = compatibility_root.resolve()
    schema_map = load_schemas(compatibility_root)
    registry = build_registry(schema_map)
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
    model_entities: dict[str, list[dict[str, Any]]] = {}
    for model_path in sorted(models_dir.glob("**/*.y*ml")):
        descriptor = _load_yaml(model_path)
        _validate(descriptor, metamodel_schema, f"model {model_path.name}", errors)
        entity_defs = _descriptor_entity_defs(descriptor)
        families[model_path.name] = Family(entity_defs)
        model_entities[model_path.name] = entity_defs
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
        _validate(case, case_schema, f"case {case_path.name}", errors, registry)
        _check_compile_eligibility(case, f"case {case_path.name}", errors)
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
                    _validate_scenario_reference_sql(
                        step,
                        case_schema,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                    )
                    _check_target_entity(
                        step["find"],
                        step.get("targetEntity"),
                        family,
                        f"case {case_path.name} scenario[{index}].find",
                        errors,
                    )
                if isinstance(step, dict) and isinstance(step.get("write"), dict):
                    entity = _validate_predicate_write(
                        step["write"],
                        model_entities.get(model_name or "", []),
                        operation_schema,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                    )
                    if entity is not None:
                        try:
                            validate_predicate_write_materialization(
                                entity, when["scenario"][:index], step["write"]
                            )
                        except PredicateWriteValidationError as exc:
                            errors.append(f"case {case_path.name} scenario[{index}]: {exc}")
                if isinstance(step, dict) and isinstance(step.get("write"), list):
                    _validate_buffered_write(
                        step["write"],
                        model_entities.get(model_name or "", []),
                        operation_schema,
                        f"case {case_path.name} scenario[{index}]",
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
