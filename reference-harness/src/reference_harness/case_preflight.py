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
from .value_object_resolve import resolve_nested_ref

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
    _write_carrier(case, when.get("write"), "when.write")
    _write_carrier(case, when.get("writeSequence"), "when.writeSequence")
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
                    _literal(case, operation, "timestamp", f"{where}.temporal.{dimension}")
                elif isinstance(operation, Mapping):
                    for name, value in operation.items():
                        _literal(case, value, "timestamp", f"{where}.temporal.{dimension}.{name}")


def _predicate(case: Case, entity: Entity, node: Mapping[str, object], where: str) -> None:
    for operation, payload in node.items():
        if operation in ("and", "or") and isinstance(payload, Sequence):
            for index, child in enumerate(payload):
                if isinstance(child, Mapping):
                    _predicate(case, entity, child, f"{where}.{operation}[{index}]")
            continue
        if operation in ("group", "not") and isinstance(payload, Mapping):
            _predicate(case, entity, payload, f"{where}.{operation}")
            continue
        if not isinstance(payload, Mapping):
            continue
        nested = payload.get("where")
        if isinstance(nested, Mapping):
            _predicate(case, entity, nested, f"{where}.{operation}.where")
        member = _predicate_member(entity, payload)
        if member is None:
            continue
        neutral_type = member.get("type")
        if not isinstance(neutral_type, str):
            continue
        for name in ("value", "lower", "upper", "start", "end"):
            if name in payload:
                _literal(case, payload[name], neutral_type, f"{where}.{operation}.{name}")
        values = payload.get("values")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for index, value in enumerate(values):
                _literal(case, value, neutral_type, f"{where}.{operation}.values[{index}]")


def _predicate_member(entity: Entity, payload: Mapping[str, object]) -> dict[str, Any] | None:
    reference = payload.get("attr")
    if isinstance(reference, str):
        _owner, members = split_reference(reference)
        try:
            return entity.attribute_by_name(members[-1])
        except KeyError:
            return None
    reference = payload.get("nestedRef")
    if isinstance(reference, str):
        try:
            return resolve_nested_ref(entity, reference)
        except Exception:
            return None
    return None


def _write_carrier(case: Case, carrier: object, where: str) -> None:
    if isinstance(carrier, Sequence) and not isinstance(carrier, (str, bytes)):
        for index, item in enumerate(carrier):
            _write_carrier(case, item, f"{where}[{index}]")
        return
    if not isinstance(carrier, Mapping):
        return
    entity_name = carrier.get("entity")
    rows = carrier.get("rows")
    if isinstance(entity_name, str) and isinstance(rows, Sequence):
        entity = case.model.entity(entity_name)
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                _entity_row(case, entity, row, f"{where}.rows[{index}]")
    for name in ("at", "validFrom", "until", "observedTxStart", "observedValidStart"):
        value = carrier.get(name)
        if value is not None and value != "infinity":
            _literal(case, value, "timestamp", f"{where}.{name}")


def _entity_row(case: Case, entity: Entity, row: Mapping[str, object], where: str) -> None:
    attributes = {attribute["name"]: attribute for attribute in entity.attributes}
    value_objects = {occurrence["name"]: occurrence for occurrence in entity.value_objects}
    for name, value in row.items():
        attribute = attributes.get(name)
        if attribute is not None:
            _attribute_literal(case, entity, attribute, value, f"{where}.{name}")
        elif name in value_objects:
            _value_object(case, value_objects[name], value, f"{where}.{name}")


def _value_object(case: Case, occurrence: Mapping[str, object], value: object, where: str) -> None:
    if value is None:
        return
    if occurrence.get("multiplicity", "one") == "many":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, item in enumerate(value):
                _value_object_element(case, occurrence, item, f"{where}[{index}]")
        return
    _value_object_element(case, occurrence, value, where)


def _value_object_element(
    case: Case, occurrence: Mapping[str, object], value: object, where: str
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
            _nullable_literal(case, item, attributes[name]["type"], f"{where}.{name}")
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
                            case, entity, member, value, f"then.rows[{index}].{name}"
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
            expected = step.get("expectGraph")
            if expected is not None:
                _expected_graph(case, expected, f"when.{sequence_name}[{index}].expectGraph")


def _expected_graph(case: Case, value: object, where: str) -> None:
    if isinstance(value, Mapping):
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
                    _entity_row(case, entity, row, f"{where}.{name}[{index}]")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _expected_graph(case, nested, f"{where}[{index}]")


def _nullable_literal(case: Case, value: object, neutral_type: str, where: str) -> None:
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


def _literal(case: Case, value: object, neutral_type: str, where: str) -> None:
    try:
        portable_literal.decode(value, neutral_type)
    except portable_literal.PortableLiteralError as exc:
        raise CaseFailure(f"{case.path.name}: {where}: {exc}") from exc
