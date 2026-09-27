"""Cross-shape typed-literal preflight before compatibility provisioning.

The traversal resolves literals against raw descriptor dictionaries and delegates
every scalar decision to :mod:`.portable_literal`. Authored ingress uses admitted
decoding; fixtures and expected observations require canonical Wire. It is
intentionally independent of production Metadata and m-wire. Null remains an
enclosing presence state and is never handed to the typed codec.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from . import portable_literal
from ._statement_bind_inference import (
    CanonicalBindTarget,
    LiteralBindTarget,
    document_members,
    infer_statement_bind_targets,
)
from .case import Case, Entity
from .case_assertions import CaseFailure
from .references import split_reference
from .storage_layout import (
    AttributeContributor,
    ColumnContributor,
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
    for where, step in _steps(case):
        nested = step.get("objectQuery")
        if isinstance(nested, Mapping):
            _query(case, nested, f"{where}.objectQuery")
        _write_carrier(case, step.get("write"), f"{where}.write")
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


def _steps(case: Case) -> Iterator[tuple[str, Mapping[str, object]]]:
    """Each scenario, then each coherence, step with its document path."""
    for sequence_name in ("scenario", "coherence"):
        steps = case.when.get(sequence_name)
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            continue
        for index, step in enumerate(steps):
            if isinstance(step, Mapping):
                yield f"when.{sequence_name}[{index}]", step


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
        if not isinstance(payload, Mapping):
            continue
        operands = _predicate_operands(case, scope, operation, payload, where)
        if operands is None:
            _predicate_comparison(case, scope, operation, payload, where)
            continue
        for operand_scope, operand, operand_where in operands:
            _predicate(case, operand_scope, operand, operand_where)


_PredicateOperand = tuple[Entity | dict[str, Any], Mapping[str, object], str]


def _predicate_operands(
    case: Case,
    scope: Entity | dict[str, Any],
    operation: str,
    payload: Mapping[str, object],
    where: str,
) -> list[_PredicateOperand] | None:
    """Return the scoped operands of a composite node, or ``None`` for a comparison."""
    if operation in ("and", "or"):
        operands = payload.get("operands")
        if not isinstance(operands, Sequence):
            return []
        return [
            (scope, child, f"{where}.{operation}.operands[{index}]")
            for index, child in enumerate(operands)
            if isinstance(child, Mapping)
        ]
    if operation in ("group", "not") or (operation == "narrow" and isinstance(scope, Entity)):
        return _single_operand(scope, payload.get("operand"), f"{where}.{operation}.operand")
    if not isinstance(scope, Entity):
        return None
    if operation in ("navigate", "exists", "notExists"):
        related = _related_entity(case, scope, payload.get("rel"))
        return _single_operand(related, payload.get("op"), f"{where}.{operation}.op")
    if operation in ("nestedExists", "nestedNotExists"):
        occurrence = _predicate_value_object(case, scope, payload.get("path"))
        return _single_operand(occurrence, payload.get("where"), f"{where}.{operation}.where")
    return None


def _single_operand(
    scope: Entity | dict[str, Any] | None, operand: object, where: str
) -> list[_PredicateOperand]:
    if scope is None or not isinstance(operand, Mapping):
        return []
    return [(scope, operand, where)]


def _predicate_comparison(
    case: Case,
    scope: Entity | dict[str, Any],
    operation: str,
    payload: Mapping[str, object],
    where: str,
) -> None:
    member = _predicate_member(case, scope, payload)
    if member is None:
        return
    neutral_type = member.get("type")
    if not isinstance(neutral_type, str):
        return
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
        _write_selection(case, carrier, target, where)
    _carrier_rows(case, carrier, where, fallback=fallback)
    for name in ("at", "validFrom", "until", "observedTxStart", "observedValidStart"):
        value = carrier.get(name)
        if value is not None and value != "infinity":
            _literal(case, value, "timestamp", f"{where}.{name}")


def _carrier_rows(
    case: Case,
    carrier: Mapping[str, object],
    where: str,
    *,
    fallback: Entity | None,
) -> None:
    """A keyed carrier's ``rows``, or a bare row read as the ``fallback`` Entity's."""
    entity_name = carrier.get("entity")
    rows = carrier.get("rows")
    if isinstance(entity_name, str) and isinstance(rows, Sequence):
        entity = case.model.entity(entity_name)
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                _entity_row(case, entity, row, f"{where}.rows[{index}]")
    elif fallback is not None and "mutation" not in carrier and "target" not in carrier:
        _entity_row(case, fallback, carrier, where)


def _write_selection(
    case: Case,
    carrier: Mapping[str, object],
    target: Mapping[str, object],
    where: str,
) -> None:
    target_name = target.get("entity")
    if not isinstance(target_name, str):
        return
    selection_entity = case.model.entity(target_name)
    predicate = target.get("predicate")
    if isinstance(predicate, Mapping):
        _predicate(case, selection_entity, predicate, f"{where}.target.predicate")
    assignments = carrier.get("assignments")
    if not isinstance(assignments, Sequence) or isinstance(assignments, (str, bytes)):
        return
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, Mapping):
            continue
        member = _predicate_member(case, selection_entity, assignment)
        if member is not None and "value" in assignment:
            _attribute_literal(
                case,
                _reference_entity(
                    case,
                    selection_entity,
                    str(assignment.get("attr", target_name)),
                ),
                member,
                assignment.get("value"),
                f"{where}.assignments[{index}].value",
            )


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
            _expected_rows(case, case.model.entity(target), rows, "then.rows")
    for name in ("graph", "graphs", "stepGraphs"):
        expected = case.then.get(name)
        if expected is not None:
            _expected_graph(case, expected, f"then.{name}")
    _expected_table_state(case)
    for where, step in _steps(case):
        _expected_step(case, step, where)
    _expected_concurrency_rows(case)


def _expected_rows(case: Case, entity: Entity, rows: object, where: str) -> None:
    """Each expected row object of a row list, read as ``entity``'s."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return
    for index, row in enumerate(rows):
        if isinstance(row, Mapping):
            _expected_entity_row(case, entity, row, f"{where}[{index}]")


def _expected_step(case: Case, step: Mapping[str, object], where: str) -> None:
    query = step.get("objectQuery")
    if isinstance(query, Mapping) and isinstance(query.get("target"), str):
        entity = case.model.entity(query["target"])
        for rows_name in ("expectRows", "observeRows"):
            _expected_rows(case, entity, step.get(rows_name), f"{where}.{rows_name}")
    expected = step.get("expectGraph")
    if expected is not None:
        _expected_graph(case, expected, f"{where}.expectGraph")


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
            if isinstance(session, Mapping):
                _expected_rows(
                    case,
                    case.model.root_entity,
                    session.get("expectRows"),
                    f"when.concurrency.rounds[{round_index}].{session_name}.expectRows",
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
        column_where = f"{where}.{slot.column}"
        if isinstance(slot.contributor, RelationalDocument):
            _relational_document(case, document.members, value, column_where)
        else:
            _declared_member_literal(case, slot.contributor, value, column_where)


def _declared_member_literal(
    case: Case, contributor: ColumnContributor, value: object, where: str
) -> None:
    """Check ``value`` canonically against a declared Attribute or top-level Value
    Object contributor; any other contributor, or an undeclared name, is not checked."""
    if isinstance(contributor, AttributeContributor):
        owner = case.model.entity(contributor.owner)
        try:
            attribute = owner.attribute_by_name(contributor.name)
        except KeyError:
            return
        _attribute_literal(case, owner, attribute, value, where, canonical=True)
    elif isinstance(contributor, ValueObjectContributor):
        _top_level_value_object(case, contributor.owner, contributor.name, value, where)


def _top_level_value_object(
    case: Case, owner_name: str, name: str, value: object, where: str
) -> None:
    owner = case.model.entity(owner_name)
    try:
        occurrence = owner.value_object_by_name(name)
    except KeyError:
        return
    _value_object(case, occurrence, value, where, canonical=True)


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
        if found and item is not None:
            _document_member_value(case, member, item, _path_where(where, member.path))


def _document_member_value(case: Case, member: DocumentMember, value: object, where: str) -> None:
    if member.type_spelling is not None:
        _literal(case, value, member.type_spelling, where, canonical=True)
    else:
        _top_level_value_object(case, member.address.owner, member.address.path[0], value, where)


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
    if isinstance(target, DocumentMember):
        if value is not None:
            _document_member_value(case, target, value, where)
        return
    slot = target
    if not isinstance(slot.contributor, RelationalDocument):
        _declared_member_literal(case, slot.contributor, value, where)
    elif isinstance(value, Mapping):
        _relational_document(case, document_members(case, slot), value, where)


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
            _expected_rows(case, entity, nested, f"{where}.{name}")
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
        else:
            _expected_rows(case, target, value, f"{where}.{key}")


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
