"""Cross-shape typed-literal preflight before compatibility provisioning.

The traversal resolves literals against raw descriptor dictionaries and delegates
every scalar decision to :mod:`.portable_literal`. Authored ingress uses admitted
decoding; fixtures and expected observations require canonical Wire. It is
intentionally independent of production Metadata and m-wire. Null remains an
enclosing presence state and is never handed to the typed codec.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import portable_literal
from ._statement_bind_inference import (
    CanonicalBindTarget,
    LiteralBindTarget,
    infer_statement_bind_targets,
)
from .case import Case, Entity
from .case_assertions import CaseFailure
from .references import split_reference
from .storage_layout import (
    AttributeContributor,
    DocumentMember,
    RelationalDocument,
    TableLayout,
    ValueObjectContributor,
)
from .value_object_resolve import resolve_element_ref, resolve_nested_ref, resolve_value_object_ref

__all__ = ["preflight_case_literals"]


def preflight_case_literals(case: Case) -> None:
    """Validate every model-resolved ingress and oracle literal before database setup."""
    for entity in case.model.entities:
        for index, row in enumerate(entity.rows):
            _entity_row(
                case,
                entity,
                row,
                f"fixtures.{entity.canonical_name}[{index}]",
                canonical=True,
            )

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
    _preflight_statement_binds(case)


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


def _predicate(
    case: Case,
    scope: Entity | dict[str, Any],
    node: Mapping[str, object],
    where: str,
) -> None:
    for operation, payload in node.items():
        if operation in ("and", "or") and isinstance(payload, Mapping):
            operands = payload.get("operands")
            if not isinstance(operands, Sequence):
                continue
            for index, child in enumerate(operands):
                if isinstance(child, Mapping):
                    _predicate(case, scope, child, f"{where}.{operation}.operands[{index}]")
            continue
        if operation in ("group", "not") and isinstance(payload, Mapping):
            operand = payload.get("operand")
            if isinstance(operand, Mapping):
                _predicate(case, scope, operand, f"{where}.{operation}.operand")
            continue
        if operation == "narrow" and isinstance(scope, Entity) and isinstance(payload, Mapping):
            operand = payload.get("operand")
            if isinstance(operand, Mapping):
                _predicate(case, scope, operand, f"{where}.{operation}.operand")
            continue
        if (
            operation in ("navigate", "exists", "notExists")
            and isinstance(scope, Entity)
            and isinstance(payload, Mapping)
        ):
            related = _related_entity(case, scope, payload.get("rel"))
            operand = payload.get("op")
            if related is not None and isinstance(operand, Mapping):
                _predicate(case, related, operand, f"{where}.{operation}.op")
            continue
        if (
            operation in ("nestedExists", "nestedNotExists")
            and isinstance(scope, Entity)
            and isinstance(payload, Mapping)
        ):
            occurrence = _predicate_value_object(case, scope, payload.get("path"))
            operand = payload.get("where")
            if occurrence is not None and isinstance(operand, Mapping):
                _predicate(case, occurrence, operand, f"{where}.{operation}.where")
            continue
        if not isinstance(payload, Mapping):
            continue
        member = _predicate_member(case, scope, payload)
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
    case: Case, scope: Entity | dict[str, Any], payload: Mapping[str, object]
) -> dict[str, Any] | None:
    if not isinstance(scope, Entity):
        reference = payload.get("path")
        if not isinstance(reference, str):
            return None
        try:
            return resolve_element_ref(scope, reference)
        except Exception:
            return None
    reference = payload.get("attr")
    if isinstance(reference, str):
        _owner, members = split_reference(reference)
        try:
            return _reference_entity(case, scope, reference).attribute_by_name(members[-1])
        except KeyError:
            return None
    reference = payload.get("path")
    if isinstance(reference, str):
        try:
            return resolve_nested_ref(_reference_entity(case, scope, reference), reference)
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
            selection_entity = case.model.entity(target_name)
            predicate = target.get("predicate")
            if isinstance(predicate, Mapping):
                _predicate(case, selection_entity, predicate, f"{where}.target.predicate")
            assignments = carrier.get("assignments")
            if isinstance(assignments, Sequence) and not isinstance(assignments, (str, bytes)):
                for index, assignment in enumerate(assignments):
                    if not isinstance(assignment, Mapping):
                        continue
                    member = _predicate_member(case, selection_entity, assignment)
                    value = assignment.get("value")
                    if member is not None and "value" in assignment:
                        _attribute_literal(
                            case,
                            _reference_entity(
                                case,
                                selection_entity,
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
    *,
    canonical: bool = False,
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
            _attribute_literal(
                case, entity, attribute, value, f"{where}.{name}", canonical=canonical
            )
        elif name in value_objects:
            _value_object(case, value_objects[name], value, f"{where}.{name}", canonical=canonical)


def _value_object(
    case: Case,
    occurrence: Mapping[str, object],
    value: object,
    where: str,
    *,
    canonical: bool,
) -> None:
    if value is None:
        return
    if occurrence.get("multiplicity", "one") == "many":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, item in enumerate(value):
                _value_object_element(
                    case, occurrence, item, f"{where}[{index}]", canonical=canonical
                )
        return
    _value_object_element(case, occurrence, value, where, canonical=canonical)


def _value_object_element(
    case: Case,
    occurrence: Mapping[str, object],
    value: object,
    where: str,
    *,
    canonical: bool,
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
                canonical=canonical,
            )
        elif name in nested:
            _value_object(case, nested[name], item, f"{where}.{name}", canonical=canonical)
        elif item is not None:
            _literal(case, item, "json", f"{where}.{name}", canonical=canonical)


def _preflight_expected(case: Case) -> None:
    query = case.when.get("objectQuery")
    rows = case.then.get("rows")
    if isinstance(query, Mapping) and isinstance(rows, Sequence):
        target = query.get("target")
        if isinstance(target, str):
            entity = case.model.entity(target)
            for index, row in enumerate(rows):
                if isinstance(row, Mapping):
                    _expected_entity_row(case, entity, row, f"then.rows[{index}]")
    for name in ("graph", "graphs", "stepGraphs"):
        expected = case.then.get(name)
        if expected is not None:
            _expected_graph(case, expected, f"then.{name}")
    _expected_table_state(case)
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
                                _expected_entity_row(
                                    case,
                                    entity,
                                    row,
                                    f"when.{sequence_name}[{index}].{rows_name}[{row_index}]",
                                )
            expected = step.get("expectGraph")
            if expected is not None:
                _expected_graph(case, expected, f"when.{sequence_name}[{index}].expectGraph")
    _expected_concurrency_rows(case)


def _expected_concurrency_rows(case: Case) -> None:
    concurrency = case.when.get("concurrency")
    if not isinstance(concurrency, Mapping):
        return
    rounds = concurrency.get("rounds")
    if not isinstance(rounds, Sequence) or isinstance(rounds, (str, bytes)):
        return
    for round_index, round_value in enumerate(rounds):
        if not isinstance(round_value, Mapping):
            continue
        for session_name in ("A", "B"):
            session = round_value.get(session_name)
            if not isinstance(session, Mapping):
                continue
            rows = session.get("expectRows")
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
                continue
            for row_index, row in enumerate(rows):
                if isinstance(row, Mapping):
                    _expected_entity_row(
                        case,
                        case.model.root_entity,
                        row,
                        (
                            f"when.concurrency.rounds[{round_index}].{session_name}"
                            f".expectRows[{row_index}]"
                        ),
                    )


def _expected_table_state(case: Case) -> None:
    state = case.then.get("tableState")
    if not isinstance(state, Mapping):
        return
    for table_name, rows in state.items():
        if not isinstance(table_name, str):
            continue
        layout = case.model.storage_layout.table(table_name)
        if layout is None or not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                _expected_table_row(case, layout, row, f"then.tableState.{table_name}[{index}]")


def _expected_table_row(
    case: Case,
    layout: TableLayout,
    row: Mapping[str, object],
    where: str,
) -> None:
    entity = _table_row_entity(case, layout, row)
    document = case.model.storage_layout.document(entity.canonical_name)
    for slot in layout.columns:
        if slot.column not in row or row[slot.column] is None:
            continue
        value = row[slot.column]
        contributor = slot.contributor
        if isinstance(contributor, AttributeContributor):
            owner = case.model.entity(contributor.owner)
            try:
                attribute = owner.attribute_by_name(contributor.name)
            except KeyError:
                continue
            _attribute_literal(
                case,
                owner,
                attribute,
                value,
                f"{where}.{slot.column}",
                canonical=True,
            )
        elif isinstance(contributor, ValueObjectContributor):
            owner = case.model.entity(contributor.owner)
            occurrence = next(
                (
                    candidate
                    for candidate in owner.value_objects
                    if candidate.get("name") == contributor.name
                ),
                None,
            )
            if occurrence is not None:
                _value_object(
                    case,
                    occurrence,
                    value,
                    f"{where}.{slot.column}",
                    canonical=True,
                )
        elif isinstance(contributor, RelationalDocument):
            _relational_document(
                case,
                document.members,
                value,
                f"{where}.{slot.column}",
            )


def _table_row_entity(case: Case, layout: TableLayout, row: Mapping[str, object]) -> Entity:
    candidates = tuple(
        entity
        for entity in case.model.entities
        if (view := case.model.storage_layout.entity(entity.canonical_name)) is not None
        and view.layout == layout
    )
    if len(candidates) == 1:
        return candidates[0]
    for entity in candidates:
        view = case.model.storage_layout.entity(entity.canonical_name)
        assert view is not None
        assignment = view.discriminator
        if assignment is not None and row.get(assignment.slot.column) == assignment.value:
            return entity
    raise CaseFailure(
        f"{case.path.name}: then.tableState.{layout.table}: row does not identify one of "
        f"{[entity.canonical_name for entity in candidates]}"
    )


def _relational_document(
    case: Case,
    members: Sequence[DocumentMember],
    value: object,
    where: str,
) -> None:
    if not isinstance(value, Mapping):
        return
    for member in members:
        found, item = _path_value(value, member.path)
        if not found or item is None:
            continue
        if member.type_spelling is not None:
            _literal(
                case, item, member.type_spelling, _path_where(where, member.path), canonical=True
            )
            continue
        owner = case.model.entity(member.address.owner)
        occurrence = next(
            (
                candidate
                for candidate in owner.value_objects
                if candidate.get("name") == member.address.path[0]
            ),
            None,
        )
        if occurrence is not None:
            _value_object(
                case,
                occurrence,
                item,
                _path_where(where, member.path),
                canonical=True,
            )


def _path_value(value: Mapping[str, object], path: Sequence[str]) -> tuple[bool, object]:
    current: object = value
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _path_where(where: str, path: Sequence[str]) -> str:
    return ".".join((where, *path))


def _preflight_statement_binds(case: Case) -> None:
    _statement_tree(case, case.then, "then")
    _statement_tree(case, case.when, "when")


def _statement_tree(case: Case, value: object, where: str) -> None:
    if isinstance(value, Mapping):
        statements = value.get("statements")
        if isinstance(statements, Sequence) and not isinstance(statements, (str, bytes)):
            _statement_entries(case, statements, f"{where}.statements")
        for name, nested in value.items():
            if name != "statements":
                _statement_tree(case, nested, f"{where}.{name}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _statement_tree(case, nested, f"{where}[{index}]")


def _statement_entries(case: Case, entries: Sequence[object], where: str) -> None:
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        sql = entry.get("sql")
        binds = entry.get("binds", [])
        statements = sql if isinstance(sql, Mapping) else {"postgres": sql}
        for dialect, statement in statements.items():
            if not isinstance(dialect, str) or not isinstance(statement, str):
                continue
            selected = binds.get(dialect) if isinstance(binds, Mapping) else binds
            if not isinstance(selected, Sequence) or isinstance(selected, (str, bytes)):
                continue
            _statement_entry(
                case,
                statement,
                selected,
                dialect,
                f"{where}[{entry_index}].binds"
                + (f".{dialect}" if isinstance(binds, Mapping) else ""),
            )


def _statement_entry(
    case: Case,
    statement: str,
    binds: Sequence[object],
    dialect: str,
    where: str,
) -> None:
    for index, target in infer_statement_bind_targets(case, statement, binds, dialect).items():
        if index < len(binds):
            _canonical_target_value(case, target, binds[index], f"{where}[{index}]")


def _canonical_target_value(
    case: Case, target: CanonicalBindTarget, value: object, where: str
) -> None:
    if isinstance(target, LiteralBindTarget):
        if value is not None:
            _literal(case, value, target.neutral_type, where, canonical=True)
        return
    slot = target
    contributor = slot.contributor
    if isinstance(contributor, AttributeContributor):
        entity = case.model.entity(contributor.owner)
        try:
            attribute = entity.attribute_by_name(contributor.name)
        except KeyError:
            return
        _attribute_literal(case, entity, attribute, value, where, canonical=True)
    elif isinstance(contributor, ValueObjectContributor):
        entity = case.model.entity(contributor.owner)
        occurrence = next(
            (
                candidate
                for candidate in entity.value_objects
                if candidate.get("name") == contributor.name
            ),
            None,
        )
        if occurrence is not None:
            _value_object(case, occurrence, value, where, canonical=True)
    elif isinstance(contributor, RelationalDocument) and isinstance(value, Mapping):
        candidates = tuple(
            member
            for entity in case.model.entities
            if (view := case.model.storage_layout.entity(entity.canonical_name)) is not None
            and slot in view.layout.columns
            for member in case.model.storage_layout.document(entity.canonical_name).members
        )
        by_path: dict[tuple[str, ...], list[DocumentMember]] = {}
        for member in candidates:
            by_path.setdefault(member.path, []).append(member)
        unambiguous = tuple(
            members[0]
            for members in by_path.values()
            if all(
                (member.address, member.type_spelling)
                == (members[0].address, members[0].type_spelling)
                for member in members[1:]
            )
        )
        _relational_document(case, unambiguous, value, where)


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
                    canonical=True,
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
    _entity_row(case, entity, row, where, canonical=True)
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
    *,
    canonical: bool = False,
) -> None:
    if value is not None:
        _literal(case, value, neutral_type, where, canonical=canonical)


def _attribute_literal(
    case: Case,
    entity: Entity,
    attribute: Mapping[str, object],
    value: object,
    where: str,
    *,
    canonical: bool = False,
) -> None:
    if isinstance(value, Mapping) and ("computed" in value or "increment" in value):
        return
    temporal_end_columns = {axis["end_column"] for axis in entity.temporal_runtime_axes}
    if value == "infinity" and attribute.get("column") in temporal_end_columns:
        return
    neutral_type = attribute.get("type")
    if isinstance(neutral_type, str):
        _nullable_literal(case, value, neutral_type, where, canonical=canonical)


def _literal(
    case: Case,
    value: object,
    neutral_type: str,
    where: str,
    *,
    canonical: bool = False,
) -> None:
    try:
        decoder = portable_literal.decode_canonical if canonical else portable_literal.decode
        decoder(value, neutral_type)
    except portable_literal.PortableLiteralError as exc:
        raise CaseFailure(f"{case.path.name}: {where}: {exc}") from exc
