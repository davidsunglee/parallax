"""Model-aware validation for predicate-selected write instructions.

The case schema proves the instruction's structural shape — including that the
selection is exactly an `m-predicate` node, since a set-based write shapes no
result and the Object Query clauses have no spelling in that position.  This
module resolves the neutral shape against a descriptor before any SQL is emitted:
the target must be one a readless statement can write, the predicate must resolve
over it, an amendment's assignments must name assignable domain attributes exactly
once, and a replacement's row must state a complete writable state.
"""

from __future__ import annotations

from typing import Any

from .case import Entity
from .inheritance import Family, inheritance_of
from .predicate_paths import EntityScope
from .predicate_validate import validate_predicate
from .query_references import collect_reference_classes
from .storage_layout import is_scalar_collection
from .value_object_resolve import (
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    RejectionError,
    decode_typed_literal,
    literal_matches_type,
)
from .write_validate import assignment_violation, undeclared_members

SET_BASED_WRITE_TARGET_UNSUPPORTED = "set-based-write-target-unsupported"

PREDICATE_WRITE_REJECTED_RULES: frozenset[str] = frozenset({SET_BASED_WRITE_TARGET_UNSUPPORTED})


class PredicateWriteValidationError(ValueError):
    """Raised when a structurally-valid predicate write is model-invalid."""


def validate_predicate_write(
    entity: Entity, instruction: dict[str, Any], entity_defs: list[dict[str, Any]]
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
    if target_name not in (entity.name, entity.canonical_name):
        raise PredicateWriteValidationError(
            f"predicate write target entity {target_name!r} is not model entity "
            f"{entity.canonical_name!r}"
        )
    _assert_readless_target(entity, instruction.get("mutation"))
    if inheritance_of(entity.definition) is not None:
        raise PredicateWriteValidationError(
            "predicate-selected writes to inheritance families are unsupported"
        )

    predicate = target.get("predicate")
    if not isinstance(predicate, dict):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError(
            "predicate write target needs a predicate-shaped selection"
        )
    _assert_predicate_scope(predicate, entity)
    family = Family(entity_defs)
    key = family.defs.canonical_key(entity.canonical_name)
    scope = EntityScope(key, tuple(family.effective_concrete_set(key)), bound=False)
    try:
        validate_predicate(family, scope, predicate)
    except RejectionError as exc:
        raise PredicateWriteValidationError(str(exc)) from exc

    mutation = instruction.get("mutation")
    if mutation == "amend":
        _assert_assignments(entity, instruction.get("assignments"))
    elif mutation == "replace":
        _assert_replacement(entity, instruction.get("row"))


def _assert_readless_target(entity: Entity, mutation: Any) -> None:
    """Refuse a target one readless statement cannot write: a versioned or
    temporal one, each of whose objects is written against an observation of it
    (`m-batch-write`). Judged before the predicate, the family, and the
    assignments, because none of them could make the write admissible."""
    versioned = any(attribute.get("optimisticLocking") for attribute in entity.attributes)
    if not (entity.is_temporal or versioned):
        return
    kind = "temporal" if entity.is_temporal else "versioned"
    raise RejectionError(
        SET_BASED_WRITE_TARGET_UNSUPPORTED,
        f"a predicate-selected {mutation!r} on the {kind} entity {entity.name!r} needs an "
        "observation of each object it writes, which one readless statement cannot make",
    )


def _assert_predicate_scope(node: Any, entity: Entity) -> None:
    classes: set[str] = set()
    # A quantifier's `where` and a path-targeted narrowing's operand resolve in
    # a bound scope and are not descended (see collect_reference_classes).
    collect_reference_classes(node, classes)
    named = (entity.name, entity.canonical_name)
    mismatched = sorted(cls for cls in classes if cls not in named)
    if mismatched:
        raise PredicateWriteValidationError(
            f"predicate write target {entity.canonical_name!r} is inconsistent with reference "
            f"class(es) {mismatched}"
        )


def _assert_assignments(entity: Entity, assignments: Any) -> None:
    if not isinstance(assignments, list):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError("assignment-bearing predicate write needs assignments")
    seen: set[str] = set()
    for assignment in assignments:
        if not isinstance(assignment, dict):  # pragma: no cover - structural schema guard
            raise PredicateWriteValidationError("predicate write assignment must be an object")
        ref = assignment.get("attr")
        if not isinstance(ref, str) or "." not in ref:
            raise PredicateWriteValidationError(f"assignment attribute {ref!r} is not qualified")
        class_name, _, attribute_name = ref.rpartition(".")
        if class_name not in (entity.name, entity.canonical_name):
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
        _assert_attribute_assignment(ref, attribute, assignment.get("value"))


def _assert_replacement(entity: Entity, row: Any) -> None:
    """Validate a replacement's row (`m-unit-work` *Source-authorized
    replacement*): it names declared members only and omits no required one,
    and every member it states but the primary key is one a caller may
    assign. The predicate selects the rows, so a stated key addresses nothing:
    it need only be a value of its declared type, and is never written."""
    if not isinstance(row, dict):  # pragma: no cover - structural schema guard
        raise PredicateWriteValidationError("a predicate replacement needs a row")
    unknown = undeclared_members(entity, row)
    if unknown:
        raise PredicateWriteValidationError(
            f"replacement row names {unknown}, which {entity.name!r} does not declare"
        )
    _assert_complete(entity, row)
    for name, value in row.items():
        attribute = next(
            (candidate for candidate in entity.attributes if candidate["name"] == name), None
        )
        if attribute is not None and attribute.get("primaryKey"):
            if not literal_matches_type(value, attribute.get("type")):
                raise PredicateWriteValidationError(
                    f"replacement key {name!r} does not match declared type "
                    f"{attribute.get('type')!r}"
                )
            continue
        violation = assignment_violation(entity, name, value)
        if violation is not None:
            raise PredicateWriteValidationError(violation)


def _assert_complete(entity: Entity, row: dict[str, Any]) -> None:
    """Refuse a replacement row omitting a member a replacement must state: a
    required, writable, non-key scalar, or a required `one` value object. A
    readless target declares no framework-owned member, and an omitted `many`
    or scalar collection is its empty collection."""
    for attribute in entity.attributes:
        if (
            attribute["name"] in row
            or attribute.get("primaryKey")
            or attribute.get("readOnly")
            or attribute.get("nullable", False)
            or is_scalar_collection(attribute)
        ):
            continue
        raise RejectionError(
            WRITE_REQUIRED_ATTRIBUTE_MISSING,
            f"{entity.name}.{attribute['name']}: a replacement states every required member",
        )
    for value_object in entity.value_objects:
        if (
            value_object["name"] in row
            or value_object.get("multiplicity", "one") == "many"
            or value_object.get("nullable", False)
        ):
            continue
        raise RejectionError(
            WRITE_REQUIRED_VALUE_OBJECT_MISSING,
            f"{entity.name}.{value_object['name']}: a replacement states every required member",
        )


def _assert_attribute_assignment(ref: str, attribute: dict[str, Any], value: Any) -> None:
    """Validate a scalar attribute assignment: not the key, and typed as declared.
    A readless target declares no framework-owned member a caller could name."""
    if attribute.get("primaryKey"):
        raise PredicateWriteValidationError(f"assignment {ref!r} targets the primary key")
    if not is_scalar_collection(attribute):
        if not literal_matches_type(value, attribute.get("type")):
            raise PredicateWriteValidationError(
                f"assignment {ref!r} value does not match declared type {attribute.get('type')!r}"
            )
        return
    _assert_collection_literal(ref, attribute, value)


def _assert_collection_literal(ref: str, attribute: dict[str, Any], value: Any) -> None:
    """Validate a scalar collection literal: an array of non-null elements, each
    decoded at its position as the instruction decodes it, so an element its
    declared type cannot decode is refused with the Wire literal rule."""
    if not isinstance(value, list) or any(element is None for element in value):
        raise PredicateWriteValidationError(
            f"assignment {ref!r} must use an array of non-null {attribute.get('type')!r} elements"
        )
    for index, element in enumerate(value):
        decode_typed_literal(element, attribute.get("type"), f"{ref}[{index}]")


def _assert_value_object_assignment(ref: str, value_object: dict[str, Any], value: Any) -> None:
    """Validate a top-level value-object assignment literal.

    A ``one`` patches only its named declared members, while a ``many`` replaces
    its ordered array whole. Recursive scalar-type and required-member checks
    keep every named value assignable to the declaration.
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
    """Validate the declared members named by one authored object."""
    if not isinstance(document, dict):
        raise PredicateWriteValidationError(
            f"value object assignment {ref!r} must use an object for multiplicity one"
        )
    for attribute in value_object.get("attributes", []):
        name = attribute["name"]
        if name not in document and is_scalar_collection(attribute):
            continue
        value = document.get(name)
        if value is None:
            if not attribute.get("nullable", False):
                raise PredicateWriteValidationError(
                    f"value object assignment {ref!r} omits required attribute {name!r}"
                )
            continue
        if is_scalar_collection(attribute):
            _assert_collection_literal(f"{ref}.{name}", attribute, value)
            continue
        if not literal_matches_type(value, attribute.get("type")):
            raise PredicateWriteValidationError(
                f"value object assignment {ref!r} attribute {name!r} does not match "
                f"declared type {attribute.get('type')!r}"
            )
    for nested in value_object.get("valueObjects", []):
        if nested["name"] not in document and (
            nested.get("multiplicity", "one") == "many" or nested.get("nullable", False)
        ):
            continue
        _assert_value_object_assignment(
            f"{ref}.{nested['name']}", nested, document.get(nested["name"])
        )
