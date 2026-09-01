"""Cross-shape typed-literal preflight before compatibility provisioning.

The traversal resolves authored values against raw descriptor dictionaries and
delegates every scalar decision to :mod:`.portable_literal`.  It is intentionally
independent of production Metadata and m-wire.  Null remains an enclosing
presence state and is never handed to the typed codec.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import portable_literal
from .case import Case, Entity
from .case_assertions import CaseFailure
from .references import split_reference
from .value_object_resolve import resolve_element_ref, resolve_nested_ref, resolve_value_object_ref

__all__ = ["preflight_case_literals"]


def preflight_case_literals(case: Case) -> None:
    """Validate every model-resolved authored literal before database setup."""
    for entity in case.model.entities:
        for index, row in enumerate(entity.rows):
            _entity_row(case, entity, row, f"fixtures.{entity.canonical_name}[{index}]")

    when = case.when
    query = when.get("objectQuery")
    if isinstance(query, Mapping):
        _query(case, query, "when.objectQuery")
    for sequence_name in ("scenario", "coherence"):
        steps = when.get(sequence_name)
        if not isinstance(steps, Sequence):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                continue
            nested = step.get("objectQuery")
            if isinstance(nested, Mapping):
                _query(case, nested, f"when.{sequence_name}[{index}].objectQuery")
            _write_carrier(case, step.get("write"), f"when.{sequence_name}[{index}].write")
    _write_carrier(case, when.get("write"), "when.write", fallback=case.model.root_entity)
    _write_carrier(case, when.get("writeSequence"), "when.writeSequence")
    attempts = when.get("attempts")
    if isinstance(attempts, Sequence) and not isinstance(attempts, (str, bytes)):
        for index, attempt in enumerate(attempts):
            if isinstance(attempt, Mapping):
                _write_carrier(
                    case,
                    attempt.get("write"),
                    f"when.attempts[{index}].write",
                    fallback=case.model.root_entity,
                )
    _preflight_expected(case)


def _query(case: Case, query: Mapping[str, object], where: str) -> None:
    target = query.get("target")
    if not isinstance(target, str):
        return
    entity = case.model.entity(target)
    predicate = query.get("predicate")
    if isinstance(predicate, Mapping):
        _predicate(case, entity, predicate, f"{where}.predicate")
    temporal = query.get("temporal")
    if isinstance(temporal, Mapping):
        for dimension, selection in temporal.items():
            if not isinstance(selection, Mapping):
                continue
            for operation in selection.values():
                if isinstance(operation, str) and operation != "latest":
                    _literal(
                        case,
                        operation,
                        "timestamp",
                        f"{where}.temporal.{dimension}",
                    )
                elif isinstance(operation, Mapping):
                    for name, value in operation.items():
                        _literal(
                            case,
                            value,
                            "timestamp",
                            f"{where}.temporal.{dimension}.{name}",
                        )


def _predicate(case: Case, entity: Entity, node: Mapping[str, object], where: str) -> None:
    for operation, payload in node.items():
        if operation in ("and", "or") and isinstance(payload, Mapping):
            operands = payload.get("operands")
            if not isinstance(operands, Sequence):
                continue
            for index, child in enumerate(operands):
                if isinstance(child, Mapping):
                    _predicate(case, entity, child, f"{where}.{operation}.operands[{index}]")
            continue
        if operation in ("group", "not", "narrow") and isinstance(payload, Mapping):
            operand = payload.get("operand")
            if isinstance(operand, Mapping):
                _predicate(case, entity, operand, f"{where}.{operation}.operand")
            continue
        if operation in ("navigate", "exists", "notExists") and isinstance(payload, Mapping):
            related = _related_entity(case, entity, payload.get("rel"))
            operand = payload.get("op")
            if related is not None and isinstance(operand, Mapping):
                _predicate(case, related, operand, f"{where}.{operation}.op")
            continue
        if operation in ("nestedExists", "nestedNotExists") and isinstance(payload, Mapping):
            occurrence = _predicate_value_object(case, entity, payload.get("path"))
            operand = payload.get("where")
            if occurrence is not None and isinstance(operand, Mapping):
                _element_predicate(case, occurrence, operand, f"{where}.{operation}.where")
            continue
        if not isinstance(payload, Mapping):
            continue
        member = _predicate_member(case, entity, payload)
        if member is None:
            continue
        neutral_type = member.get("type")
        if not isinstance(neutral_type, str):
            continue
        for name in ("value", "lower", "upper", "start", "end"):
            if name in payload:
                _literal(
                    case,
                    payload[name],
                    neutral_type,
                    f"{where}.{operation}.{name}",
                )
        values = payload.get("values")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for index, value in enumerate(values):
                _literal(
                    case,
                    value,
                    neutral_type,
                    f"{where}.{operation}.values[{index}]",
                )


def _reference_entity(case: Case, fallback: Entity, reference: str) -> Entity:
    owner, _members = split_reference(reference)
    if owner is None:
        return fallback
    try:
        return case.model.entity(owner)
    except KeyError:
        return fallback


def _predicate_member(
    case: Case, entity: Entity, payload: Mapping[str, object]
) -> dict[str, Any] | None:
    reference = payload.get("attr")
    if isinstance(reference, str):
        _owner, members = split_reference(reference)
        try:
            return _reference_entity(case, entity, reference).attribute_by_name(members[-1])
        except KeyError:
            return None
    reference = payload.get("path")
    if isinstance(reference, str):
        try:
            return resolve_nested_ref(_reference_entity(case, entity, reference), reference)
        except Exception:
            return None
    return None


def _related_entity(case: Case, entity: Entity, reference: object) -> Entity | None:
    if not isinstance(reference, str):
        return None
    owner = _reference_entity(case, entity, reference)
    _owner, members = split_reference(reference)
    try:
        relationship = owner.relationship_metadata_by_name(members[-1])
        return case.model.entity(relationship["join"]["target"]["entity"])
    except (KeyError, TypeError):
        return None


def _predicate_value_object(case: Case, entity: Entity, reference: object) -> dict[str, Any] | None:
    if not isinstance(reference, str):
        return None
    try:
        return resolve_value_object_ref(_reference_entity(case, entity, reference), reference)
    except Exception:
        return None


def _element_predicate(
    case: Case,
    occurrence: dict[str, Any],
    node: Mapping[str, object],
    where: str,
) -> None:
    for operation, payload in node.items():
        if operation in ("and", "or") and isinstance(payload, Mapping):
            operands = payload.get("operands")
            if isinstance(operands, Sequence):
                for index, child in enumerate(operands):
                    if isinstance(child, Mapping):
                        _element_predicate(
                            case,
                            occurrence,
                            child,
                            f"{where}.{operation}.operands[{index}]",
                        )
            continue
        if operation in ("group", "not") and isinstance(payload, Mapping):
            operand = payload.get("operand")
            if isinstance(operand, Mapping):
                _element_predicate(case, occurrence, operand, f"{where}.{operation}.operand")
            continue
        if not isinstance(payload, Mapping):
            continue
        path = payload.get("path")
        if not isinstance(path, str):
            continue
        try:
            member = resolve_element_ref(occurrence, path)
        except Exception:
            continue
        neutral_type = member.get("type")
        if not isinstance(neutral_type, str):
            continue
        for name in ("value", "lower", "upper"):
            if name in payload:
                _literal(
                    case,
                    payload[name],
                    neutral_type,
                    f"{where}.{operation}.{name}",
                )
        values = payload.get("values")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for index, value in enumerate(values):
                _literal(
                    case,
                    value,
                    neutral_type,
                    f"{where}.{operation}.values[{index}]",
                )


def _write_carrier(
    case: Case,
    carrier: object,
    where: str,
    *,
    fallback: Entity | None = None,
) -> None:
    if isinstance(carrier, Sequence) and not isinstance(carrier, (str, bytes)):
        for index, item in enumerate(carrier):
            _write_carrier(case, item, f"{where}[{index}]", fallback=fallback)
        return
    if not isinstance(carrier, Mapping):
        return
    target = carrier.get("target")
    if isinstance(target, Mapping):
        target_name = target.get("entity")
        if isinstance(target_name, str):
            target_entity = case.model.entity(target_name)
            predicate = target.get("predicate")
            if isinstance(predicate, Mapping):
                _predicate(case, target_entity, predicate, f"{where}.target.predicate")
            assignments = carrier.get("assignments")
            if isinstance(assignments, Sequence) and not isinstance(assignments, (str, bytes)):
                for index, assignment in enumerate(assignments):
                    if not isinstance(assignment, Mapping):
                        continue
                    member = _predicate_member(case, target_entity, assignment)
                    value = assignment.get("value")
                    if member is not None and "value" in assignment:
                        _attribute_literal(
                            case,
                            _reference_entity(
                                case,
                                target_entity,
                                str(assignment.get("attr", target_name)),
                            ),
                            member,
                            value,
                            f"{where}.assignments[{index}].value",
                        )
    entity_name = carrier.get("entity")
    rows = carrier.get("rows")
    if isinstance(entity_name, str) and isinstance(rows, Sequence):
        entity = case.model.entity(entity_name)
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                _entity_row(case, entity, row, f"{where}.rows[{index}]")
    elif fallback is not None and "mutation" not in carrier and "target" not in carrier:
        _entity_row(case, fallback, carrier, where)
    for name in ("at", "validFrom", "until", "observedTxStart", "observedValidStart"):
        value = carrier.get(name)
        if value is not None and value != "infinity":
            _literal(case, value, "timestamp", f"{where}.{name}")


def _entity_row(
    case: Case,
    entity: Entity,
    row: Mapping[str, object],
    where: str,
) -> None:
    attributes = {
        key: attribute
        for attribute in entity.attributes
        for key in (attribute["name"], attribute["column"])
    }
    value_objects = {
        key: occurrence
        for occurrence in entity.value_objects
        for key in (occurrence["name"], occurrence.get("column"))
        if key is not None
    }
    for name, value in row.items():
        attribute = attributes.get(name)
        if attribute is not None:
            _attribute_literal(case, entity, attribute, value, f"{where}.{name}")
        elif name in value_objects:
            _value_object(case, value_objects[name], value, f"{where}.{name}")


def _value_object(
    case: Case,
    occurrence: Mapping[str, object],
    value: object,
    where: str,
) -> None:
    if value is None:
        return
    if occurrence.get("multiplicity", "one") == "many":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, item in enumerate(value):
                _value_object_element(case, occurrence, item, f"{where}[{index}]")
        return
    _value_object_element(case, occurrence, value, where)


def _value_object_element(
    case: Case,
    occurrence: Mapping[str, object],
    value: object,
    where: str,
) -> None:
    if not isinstance(value, Mapping):
        return
    raw_attributes = occurrence.get("attributes", [])
    raw_nested = occurrence.get("valueObjects", [])
    attribute_items = raw_attributes if isinstance(raw_attributes, Sequence) else ()
    nested_items = raw_nested if isinstance(raw_nested, Sequence) else ()
    attributes = {item["name"]: item for item in attribute_items if isinstance(item, Mapping)}
    nested = {item["name"]: item for item in nested_items if isinstance(item, Mapping)}
    for name, item in value.items():
        if name in attributes:
            _nullable_literal(
                case,
                item,
                attributes[name]["type"],
                f"{where}.{name}",
            )
        elif name in nested:
            _value_object(case, nested[name], item, f"{where}.{name}")


def _preflight_expected(case: Case) -> None:
    query = case.when.get("objectQuery")
    rows = case.then.get("rows")
    if isinstance(query, Mapping) and isinstance(rows, Sequence):
        target = query.get("target")
        if isinstance(target, str):
            entity = case.model.entity(target)
            by_column = {attribute["column"]: attribute for attribute in entity.attributes}
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    continue
                for name, value in row.items():
                    member = by_column.get(name)
                    if member is not None:
                        _attribute_literal(
                            case,
                            entity,
                            member,
                            value,
                            f"then.rows[{index}].{name}",
                        )
    for name in ("graph", "graphs", "stepGraphs"):
        expected = case.then.get(name)
        if expected is not None:
            _expected_graph(case, expected, f"then.{name}")
    for sequence_name in ("scenario", "coherence"):
        steps = case.when.get(sequence_name)
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                continue
            query = step.get("objectQuery")
            if isinstance(query, Mapping) and isinstance(query.get("target"), str):
                entity = case.model.entity(query["target"])
                for rows_name in ("expectRows", "observeRows"):
                    rows = step.get(rows_name)
                    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                        for row_index, row in enumerate(rows):
                            if isinstance(row, Mapping):
                                _entity_row(
                                    case,
                                    entity,
                                    row,
                                    f"when.{sequence_name}[{index}].{rows_name}[{row_index}]",
                                )
            expected = step.get("expectGraph")
            if expected is not None:
                _expected_graph(case, expected, f"when.{sequence_name}[{index}].expectGraph")


def _expected_graph(case: Case, value: object, where: str) -> None:
    if isinstance(value, Mapping):
        pin = value.get("pin")
        if isinstance(pin, Mapping):
            for dimension, coordinate in pin.items():
                _literal(
                    case,
                    coordinate,
                    "timestamp",
                    f"{where}.pin.{dimension}",
                )
        for name, nested in value.items():
            try:
                entity = case.model.entity(name)
            except KeyError:
                _expected_graph(case, nested, f"{where}.{name}")
                continue
            if not isinstance(nested, Sequence) or isinstance(nested, (str, bytes)):
                continue
            for index, row in enumerate(nested):
                if isinstance(row, Mapping):
                    _expected_entity_row(case, entity, row, f"{where}.{name}[{index}]")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _expected_graph(case, nested, f"{where}[{index}]")


def _expected_entity_row(
    case: Case,
    entity: Entity,
    row: Mapping[str, object],
    where: str,
) -> None:
    variant = row.get("familyVariant")
    if isinstance(variant, str):
        try:
            entity = case.model.entity(variant)
        except KeyError:
            pass
    _entity_row(case, entity, row, where)
    relationships = {
        relationship["name"]: relationship for relationship in entity.relationship_metadata
    }
    for key, value in row.items():
        relationship = relationships.get(key.split("[", 1)[0])
        if relationship is None:
            continue
        target = case.model.entity(relationship["join"]["target"]["entity"])
        if isinstance(value, Mapping):
            _expected_entity_row(case, target, value, f"{where}.{key}")
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                if isinstance(child, Mapping):
                    _expected_entity_row(case, target, child, f"{where}.{key}[{index}]")


def _nullable_literal(
    case: Case,
    value: object,
    neutral_type: str,
    where: str,
) -> None:
    if value is not None:
        _literal(case, value, neutral_type, where)


def _attribute_literal(
    case: Case,
    entity: Entity,
    attribute: Mapping[str, object],
    value: object,
    where: str,
) -> None:
    if isinstance(value, Mapping) and ("computed" in value or "increment" in value):
        return
    temporal_end_columns = {axis["end_column"] for axis in entity.temporal_runtime_axes}
    if value == "infinity" and attribute.get("column") in temporal_end_columns:
        return
    neutral_type = attribute.get("type")
    if isinstance(neutral_type, str):
        _nullable_literal(case, value, neutral_type, where)


def _literal(
    case: Case,
    value: object,
    neutral_type: str,
    where: str,
) -> None:
    try:
        portable_literal.decode(value, neutral_type)
    except portable_literal.PortableLiteralError as exc:
        raise CaseFailure(f"{case.path.name}: {where}: {exc}") from exc
