"""Model-aware validation for predicate-selected write instructions (COR-35).

The case schema proves the instruction's structural shape.  This module resolves
that neutral shape against a descriptor before any SQL is emitted: the predicate
must be a bare operation over the named target, assignments must name assignable
domain attributes exactly once, and temporal coordinates must fit the target's
profile.
"""

from __future__ import annotations

from typing import Any

from .case import Entity
from .inheritance import inheritance_of
from .op_validate import validate_operation
from .serde import canonical
from .value_object_resolve import RejectionError, literal_matches_type


class PredicateWriteValidationError(ValueError):
    """Raised when a structurally-valid predicate write is model-invalid."""


_ATTRIBUTE_REFERENCE_TAGS = frozenset(
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
_PATH_REFERENCE_TAGS = frozenset(
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
_READ_MODIFIERS = frozenset(
    {
        "orderBy",
        "limit",
        "distinct",
        "deepFetch",
        "asOf",
        "asOfRange",
        "history",
        "groupBy",
        "narrow",
    }
)


def validate_predicate_write(
    entity: Entity, entity_defs: list[dict[str, Any]], instruction: dict[str, Any]
) -> None:
    """Validate one predicate-selected write instruction against *entity*.

    The caller has already validated the instruction and predicate against their
    JSON Schemas.  This function intentionally owns only descriptor-dependent
    checks, keeping the corpus format useful to every implementation without
    deriving write SQL in the reference harness.
    """
    target = instruction.get("target")
    if not isinstance(target, dict):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError("predicate write target must be an object")
    target_name = target.get("entity")
    if target_name != entity.name:
        raise PredicateWriteValidationError(
            f"predicate write target entity {target_name!r} is not model entity {entity.name!r}"
        )
    if inheritance_of(entity.definition) is not None:
        raise PredicateWriteValidationError(
            "predicate-selected writes to inheritance families are unsupported"
        )

    predicate = target.get("predicate")
    if not isinstance(predicate, dict):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError(
            "predicate write target needs an operation-shaped predicate"
        )
    _assert_bare_predicate(predicate)
    _assert_predicate_scope(predicate, entity.name)
    try:
        validate_operation(entity, predicate)
    except RejectionError as exc:
        raise PredicateWriteValidationError(str(exc)) from exc

    mutation = instruction.get("mutation")
    _assert_temporal_shape(entity, mutation, instruction)
    if mutation in ("update", "updateUntil"):
        _assert_assignments(entity, instruction.get("assignments"))


def validate_predicate_write_materialization(
    entity: Entity,
    preceding_steps: list[dict[str, Any]],
    instruction: dict[str, Any],
) -> None:
    """Require an observable prior resolution when a predicate write needs one.

    Versioned and temporal predicate writes lower to per-row work, so their
    scenario data must expose the exact earlier resolution from which that work
    is planned.  The readless exception is deliberately narrow: only an
    unversioned, non-temporal ``update`` or ``delete`` reaches this helper and
    returns without a read.  Structural shape and descriptor validity are owned
    by :func:`validate_predicate_write`; this function only links an already
    validated scenario write to its earlier read result.
    """
    if not _requires_materialization(entity):
        return

    target = instruction.get("target")
    if not isinstance(target, dict):  # pragma: no cover - structural schema guard
        return
    predicate = target.get("predicate")
    if not isinstance(predicate, dict):  # pragma: no cover - structural schema guard
        return

    target_finds = [
        (index, step)
        for index, step in enumerate(preceding_steps)
        if step.get("targetEntity") == entity.name and isinstance(step.get("find"), dict)
    ]
    matching_finds = [
        (index, step)
        for index, step in target_finds
        if canonical(step["find"]) == canonical(predicate)
    ]
    if not matching_finds:
        if target_finds:
            raise PredicateWriteValidationError(
                f"predicate write to {entity.name!r} requires a preceding materializing find "
                "with a matching canonical predicate; earlier finds for that target resolve "
                "different predicates"
            )
        raise PredicateWriteValidationError(
            f"predicate write to {entity.name!r} requires a preceding materializing find "
            "for the same concrete target and canonical predicate"
        )

    for index, step in matching_finds:
        rows = step.get("expectRows")
        if not isinstance(rows, list):
            continue
        _assert_materialization_rows(entity, index, rows)
        return
    indexes = ", ".join(f"scenario[{index}]" for index, _ in matching_finds)
    raise PredicateWriteValidationError(
        f"matching materializing find at {indexes} must declare expectRows to expose "
        "the resolved rows and per-row observations"
    )


def _requires_materialization(entity: Entity) -> bool:
    return entity.is_temporal or any(
        attribute.get("optimisticLocking") for attribute in entity.attributes
    )


def _assert_materialization_rows(entity: Entity, index: int, rows: list[Any]) -> None:
    """Ensure an observable read exposes the identity/version coordinates it needs.

    An empty expected result is itself an observable materialization: no per-row
    write will follow.  For every resolved row, derive the identity and observed
    version/milestone columns from the descriptor rather than its authored SQL.
    """
    required_columns = {
        attribute["column"]
        for attribute in entity.attributes
        if attribute.get("primaryKey") or attribute.get("optimisticLocking")
    }
    if entity.is_temporal:
        required_columns.update(
            column
            for axis in entity.as_of_attributes
            for column in (axis.get("fromColumn"), axis.get("toColumn"))
            if isinstance(column, str)
        )
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):  # pragma: no cover - case schema guard
            continue
        missing = sorted(required_columns - row.keys())
        if missing:
            raise PredicateWriteValidationError(
                f"materializing find at scenario[{index}] expectRows[{row_index}] omits "
                f"required identity/observation column(s) {missing} for {entity.name!r}"
            )


def _assert_bare_predicate(node: Any) -> None:
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag in _READ_MODIFIERS:
        raise PredicateWriteValidationError(
            f"predicate write target contains read modifier {tag!r}; "
            "write targets are bare predicates"
        )
    if not isinstance(body, dict):
        return
    if tag in ("and", "or"):
        for operand in body.get("operands", []):
            _assert_bare_predicate(operand)
    elif tag in ("not", "group"):
        _assert_bare_predicate(body.get("operand"))
    elif tag in ("navigate", "exists", "notExists"):
        _assert_bare_predicate(body.get("op"))
    elif tag in ("nestedExists", "nestedNotExists"):
        _assert_bare_predicate(body.get("where"))


def _assert_predicate_scope(node: Any, target_name: str) -> None:
    classes: set[str] = set()
    _collect_reference_classes(node, classes)
    mismatched = sorted(cls for cls in classes if cls != target_name)
    if mismatched:
        raise PredicateWriteValidationError(
            f"predicate write target {target_name!r} is inconsistent with reference "
            f"class(es) {mismatched}"
        )


def _collect_reference_classes(node: Any, classes: set[str]) -> None:
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return
    if tag in _ATTRIBUTE_REFERENCE_TAGS:
        _add_reference_class(body.get("attr"), classes)
    elif tag in _PATH_REFERENCE_TAGS:
        _add_reference_class(body.get("path"), classes)
    elif tag in ("navigate", "exists", "notExists"):
        _add_reference_class(body.get("rel"), classes)
        # The inner operation resolves in the RELATED entity's scope.  Its
        # references are therefore not evidence that this write target began
        # from a different root entity (the same boundary as read validation).
    elif tag in ("and", "or"):
        for operand in body.get("operands", []):
            _collect_reference_classes(operand, classes)
    elif tag in ("not", "group"):
        _collect_reference_classes(body.get("operand"), classes)
    elif tag == "orderBy":
        _collect_reference_classes(body.get("operand"), classes)
        for key in body.get("keys", []):
            if isinstance(key, dict):
                _add_reference_class(key.get("attr"), classes)


def _add_reference_class(reference: Any, classes: set[str]) -> None:
    if isinstance(reference, str) and "." in reference:
        classes.add(reference.split(".", 1)[0])


def _assert_assignments(entity: Entity, assignments: Any) -> None:
    if not isinstance(assignments, list):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError("assignment-bearing predicate write needs assignments")
    seen: set[str] = set()
    temporal_columns = {
        column
        for axis in entity.as_of_attributes
        for column in (axis.get("fromColumn"), axis.get("toColumn"))
        if isinstance(column, str)
    }
    for assignment in assignments:
        if not isinstance(assignment, dict):  # pragma: no cover - structural schema guard
            raise PredicateWriteValidationError("predicate write assignment must be an object")
        ref = assignment.get("attr")
        if not isinstance(ref, str) or "." not in ref:
            raise PredicateWriteValidationError(f"assignment attribute {ref!r} is not qualified")
        class_name, attribute_name = ref.split(".", 1)
        if class_name != entity.name:
            raise PredicateWriteValidationError(
                f"assignment {ref!r} is unassignable outside target entity {entity.name!r}"
            )
        if ref in seen:
            raise PredicateWriteValidationError(f"duplicate predicate write assignment {ref!r}")
        seen.add(ref)
        try:
            attribute = entity.attribute_by_name(attribute_name)
        except KeyError:
            try:
                value_object = entity.value_object_by_name(attribute_name)
            except KeyError as exc:
                raise PredicateWriteValidationError(
                    f"assignment {ref!r} names no assignable attribute or value object "
                    f"on {entity.name!r}"
                ) from exc
            _assert_value_object_assignment(ref, value_object, assignment.get("value"))
            continue
        if (
            attribute.get("primaryKey")
            or attribute.get("optimisticLocking")
            or attribute.get("column") in temporal_columns
        ):
            raise PredicateWriteValidationError(
                f"assignment {ref!r} targets a framework-owned attribute"
            )
        if not literal_matches_type(assignment.get("value"), attribute.get("type")):
            raise PredicateWriteValidationError(
                f"assignment {ref!r} value does not match declared type {attribute.get('type')!r}"
            )


def _assert_value_object_assignment(ref: str, value_object: dict[str, Any], value: Any) -> None:
    """Validate an atomic top-level value-object assignment literal.

    A value object names one structured-document column, so predicate writes may
    replace that whole document but may not address its nested members.  Its
    declared cardinality determines whether the neutral literal is an object or
    an array; recursive required-member and scalar-type checks keep the literal
    assignable to the declared value object.
    """
    if value is None:
        if not value_object.get("nullable", False):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} is null for a non-nullable value object"
            )
        return
    cardinality = value_object.get("cardinality", "one")
    if cardinality == "many":
        if not isinstance(value, list):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} must use an array for cardinality many"
            )
        for index, document in enumerate(value):
            _assert_value_object_document(f"{ref}[{index}]", value_object, document)
        return
    _assert_value_object_document(ref, value_object, value)


def _assert_value_object_document(ref: str, value_object: dict[str, Any], document: Any) -> None:
    """Validate one complete document against a declared value-object member."""
    if not isinstance(document, dict):
        raise PredicateWriteValidationError(
            f"value object assignment {ref!r} must use an object for cardinality one"
        )
    for attribute in value_object.get("attributes", []):
        name = attribute["name"]
        value = document.get(name)
        if value is None:
            if not attribute.get("nullable", False):
                raise PredicateWriteValidationError(
                    f"value object assignment {ref!r} omits required attribute {name!r}"
                )
            continue
        if not literal_matches_type(value, attribute.get("type")):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} attribute {name!r} does not match "
                f"declared type {attribute.get('type')!r}"
            )
    for nested in value_object.get("valueObjects", []):
        _assert_value_object_assignment(
            f"{ref}.{nested['name']}", nested, document.get(nested["name"])
        )


def _assert_temporal_shape(entity: Entity, mutation: Any, instruction: dict[str, Any]) -> None:
    axes = {axis.get("axis") for axis in entity.as_of_attributes}
    has_processing = "processing" in axes
    has_business = "business" in axes
    temporal_values = {name: instruction.get(name) for name in ("at", "businessFrom", "until")}
    if not axes:
        if any(value is not None for value in temporal_values.values()):
            raise PredicateWriteValidationError(
                "non-temporal predicate write carries temporal bounds"
            )
        if mutation not in ("update", "delete"):
            raise PredicateWriteValidationError(
                f"non-temporal target does not support predicate mutation {mutation!r}"
            )
        return
    if mutation == "delete":
        raise PredicateWriteValidationError("temporal predicate writes use terminate, not delete")
    if has_processing and instruction.get("at") is None:
        raise PredicateWriteValidationError("processing-temporal predicate write requires at")
    if not has_processing and instruction.get("at") is not None:
        raise PredicateWriteValidationError("target has no processing axis, so at is invalid")
    if has_business and instruction.get("businessFrom") is None:
        raise PredicateWriteValidationError(
            "business-temporal predicate write requires businessFrom"
        )
    if not has_business and instruction.get("businessFrom") is not None:
        raise PredicateWriteValidationError(
            "target has no business axis, so businessFrom is invalid"
        )
    if mutation in ("updateUntil", "terminateUntil") and not has_business:
        raise PredicateWriteValidationError(f"{mutation} requires a business-temporal target")
