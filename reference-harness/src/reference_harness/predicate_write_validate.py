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
from .operation_references import collect_reference_classes
from .serde import canonical
from .value_object_resolve import RejectionError, literal_matches_type


class PredicateWriteValidationError(ValueError):
    """Raised when a structurally-valid predicate write is model-invalid."""


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


def validate_predicate_write(entity: Entity, instruction: dict[str, Any]) -> None:
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

    That resolving "materializing find" is the internal materialized-predicate-write
    read — the values-lane / ROW-FORM read of m-case-format's *Read result form* (m-sql
    *Read projection*): it observes each matched row's pk and gate/current-scalar values
    to plan per-row DML without constructing an instance, so it omits slot 4's value-object
    document columns (a reassigned document comes from the write instruction, not the read).
    A managed-object find/refresh step is instead instance-form (the object lane).
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
        rows = _resolving_materialization_rows(step)
        if rows is None:
            continue
        _assert_materialization_rows(entity, index, rows, instruction)
        return
    indexes = ", ".join(f"scenario[{index}]" for index, _ in matching_finds)
    raise PredicateWriteValidationError(
        f"matching materializing find at {indexes} must be a real resolving read: "
        "roundTrips: 1, exactly one authored golden read statement, and expectRows "
        "exposing the resolved rows (or a genuine zero-match result)"
    )


def _requires_materialization(entity: Entity) -> bool:
    return entity.is_temporal or any(
        attribute.get("optimisticLocking") for attribute in entity.attributes
    )


def _resolving_materialization_rows(step: dict[str, Any]) -> list[Any] | None:
    """Return rows only for one real materializing database read.

    A versioned or temporal predicate write cannot plan from a cache hit.  The
    scenario therefore records the one resolving read explicitly: one round trip,
    one authored golden SQL entry, and ``expectRows`` for either the observed rows
    or a genuine zero-match result.  The case schema and generic scenario
    bookkeeping validate the entry's full SQL shape; this descriptor-aware check
    owns the link from that read to a predicate write.
    """
    if step.get("roundTrips") != 1:
        return None
    statements = step.get("statements")
    if not isinstance(statements, list) or len(statements) != 1:
        return None
    rows = step.get("expectRows")
    if not isinstance(rows, list):
        return None
    return rows


def _assert_materialization_rows(
    entity: Entity, index: int, rows: list[Any], instruction: dict[str, Any]
) -> None:
    """Ensure a real read exposes every current value needed to plan the write.

    Derive the projection from the descriptor and requested write rather than
    authored SQL: identities, observed versions, and current temporal coordinates
    are always needed; assignment-bearing updates additionally need the current
    assigned values for per-row no-op elimination; temporal chains need every
    current payload column they copy into their head/middle/tail rows.
    """
    required_columns = _materialization_columns(entity, instruction)
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):  # pragma: no cover - case schema guard
            continue
        missing = sorted(required_columns - row.keys())
        if missing:
            raise PredicateWriteValidationError(
                f"materializing find at scenario[{index}] expectRows[{row_index}] omits "
                f"required current materialization column(s) {missing} for {entity.name!r}"
            )


def _materialization_columns(entity: Entity, instruction: dict[str, Any]) -> set[str]:
    """Return descriptor columns a predicate-write materialization must observe.

    This is intentionally column-based because ``expectRows`` represents the SQL
    projection.  The descriptor identifies observed state; output values generated
    by a write (a bumped version, fresh processing instants, open bounds, or an
    inheritance discriminator) are not requested from the materialization.
    """
    temporal_columns = _temporal_columns(entity)
    required_columns = {
        attribute["column"]
        for attribute in entity.attributes
        if attribute.get("primaryKey") or attribute.get("optimisticLocking")
    }
    if entity.is_temporal:
        required_columns.update(temporal_columns)

    mutation = instruction.get("mutation")
    if mutation in ("update", "updateUntil"):
        required_columns.update(_assigned_columns(entity, instruction.get("assignments")))

    if _temporal_write_carries_payload(entity, mutation):
        required_columns.update(_temporal_payload_columns(entity, temporal_columns))
    return required_columns


def _temporal_columns(entity: Entity) -> set[str]:
    return {
        column
        for axis in entity.temporal_runtime_axes
        for column in (axis.get("start_column"), axis.get("end_column"))
        if isinstance(column, str)
    }


def _assigned_columns(entity: Entity, assignments: Any) -> set[str]:
    """Resolve scalar and whole-document assignment observations from the descriptor."""
    if not isinstance(assignments, list):  # pragma: no cover - structural schema guard
        return set()
    columns: set[str] = set()
    for assignment in assignments:
        if not isinstance(assignment, dict):  # pragma: no cover - structural schema guard
            continue
        reference = assignment.get("attr")
        if not isinstance(reference, str) or "." not in reference:
            continue
        _, name = reference.split(".", 1)
        try:
            columns.add(entity.attribute_by_name(name)["column"])
        except KeyError:
            try:
                columns.add(entity.value_object_by_name(name)["column"])
            except KeyError:
                # Assignment validity is checked earlier by _assert_assignments.
                continue
    return columns


def _temporal_write_carries_payload(entity: Entity, mutation: Any) -> bool:
    """Whether this temporal verb chains a row containing the old payload.

    An update always opens a successor, and a Valid-Time terminate preserves
    the head and/or tail around the removed interval.  A Transaction-Time-Only terminate
    merely closes its row, so its payload is not an input to planning that close.
    """
    if not entity.is_temporal:
        return False
    if mutation in ("update", "updateUntil"):
        return True
    return any(axis.get("dimension") == "validTime" for axis in entity.temporal_runtime_axes)


def _temporal_payload_columns(entity: Entity, temporal_columns: set[str]) -> set[str]:
    """Return current domain columns copied into a temporal successor row."""
    scalar_columns = {
        attribute["column"]
        for attribute in entity.attributes
        if attribute["column"] not in temporal_columns and not attribute.get("optimisticLocking")
    }
    value_object_columns = {
        value_object["column"]
        for value_object in entity.value_objects
        if isinstance(value_object.get("column"), str)
    }
    return scalar_columns | value_object_columns


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
    # A predicate write is a BARE predicate (asserted just above), so the walk
    # stays in the predicate core and does not expect result modifiers.  A
    # navigation's inner operation and a nestedExists `where` resolve in a
    # different scope and are not descended (see collect_reference_classes).
    collect_reference_classes(node, classes, descend_result_modifiers=False)
    mismatched = sorted(cls for cls in classes if cls != target_name)
    if mismatched:
        raise PredicateWriteValidationError(
            f"predicate write target {target_name!r} is inconsistent with reference "
            f"class(es) {mismatched}"
        )


def _assert_assignments(entity: Entity, assignments: Any) -> None:
    if not isinstance(assignments, list):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError("assignment-bearing predicate write needs assignments")
    seen: set[str] = set()
    temporal_columns = _temporal_columns(entity)
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
    declared multiplicity determines whether the neutral literal is an object or
    an array; recursive required-member and scalar-type checks keep the literal
    assignable to the declared value object.
    """
    if value is None:
        if not value_object.get("nullable", False):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} is null for a non-nullable value object"
            )
        return
    multiplicity = value_object.get("multiplicity", "one")
    if multiplicity == "many":
        if not isinstance(value, list):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} must use an array for multiplicity many"
            )
        for index, document in enumerate(value):
            _assert_value_object_document(f"{ref}[{index}]", value_object, document)
        return
    _assert_value_object_document(ref, value_object, value)


def _assert_value_object_document(ref: str, value_object: dict[str, Any], document: Any) -> None:
    """Validate one complete document against a declared value-object member."""
    if not isinstance(document, dict):
        raise PredicateWriteValidationError(
            f"value object assignment {ref!r} must use an object for multiplicity one"
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
    axes = {axis.get("dimension") for axis in entity.temporal_runtime_axes}
    has_transaction_time = "transactionTime" in axes
    has_valid_time = "validTime" in axes
    temporal_values = {name: instruction.get(name) for name in ("at", "validFrom", "until")}
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
    if has_transaction_time and instruction.get("at") is None:
        raise PredicateWriteValidationError(
            "Transaction-Time predicate write requires flush-time at"
        )
    if not has_transaction_time and instruction.get("at") is not None:
        raise PredicateWriteValidationError(
            "target has no Transaction-Time dimension, so at is invalid"
        )
    if has_valid_time and instruction.get("validFrom") is None:
        raise PredicateWriteValidationError("Valid-Time predicate write requires validFrom")
    if not has_valid_time and instruction.get("validFrom") is not None:
        raise PredicateWriteValidationError(
            "target has no Valid-Time dimension, so validFrom is invalid"
        )
    if mutation in ("updateUntil", "terminateUntil") and not has_valid_time:
        raise PredicateWriteValidationError(f"{mutation} requires a Valid-Time target")
