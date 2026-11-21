"""Model-aware WRITE validation for the ``rejected`` case shape (m-value-object).

A write `rejected` case (m-case-format, resolved Q7) carries a neutral write row
(①) that a model-aware validator MUST refuse **before any DML is emitted**. The row
is resolved against the target's **applicable** structure — the scalar Attributes
and Value Objects it declares and, for an inheritance participant, the ones it
inherits (`m-inheritance`), recursively — and this module raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the rule:

* ``write-required-attribute-missing`` — a required (`nullable: false`) attribute is
  absent (or null) at any depth, the entity's own top-level Attributes included;
* ``write-required-value-object-missing`` — a required `one` value object is absent
  (or null) at any depth, or a `many` occurrence is present as an explicit null. An
  ABSENT `many` is not a violation: absence and the empty array are one logical zero
  state, so an unnamed `many` occurrence is the empty collection (m-value-object,
  m-document-codec);
* ``write-value-type-mismatch`` — a Value Object position carries the wrong
  container shape: a non-document at a `one` occurrence, or a non-list (or a list
  of non-documents) at a `many` one. Resolved scalar leaves use the closed
  ``neutral-literal-*`` taxonomy instead. A value object binds **atomically as one
  whole document** (m-value-object), so a scalar standing where a document is
  declared is a type mismatch rather than an absence.

Ahead of every one of them, :func:`validate_write_persistence` refuses any write
to an entity whose family is read-only (``read-only-write-target``, m-unit-work).

The bare `when.write` row carries no mutation context, so it is graded as a FULL
document: every applicable member must be present, save a `many` occurrence, whose
absence IS its empty collection. Two member kinds are outside the walk because the
framework, never the caller, supplies their values — the optimistic-lock version
and the As-Of Axis endpoints (:func:`framework_owned_names`), plus a
table-per-hierarchy tag column, whose presence the concrete-subtype protocol below
refuses outright.

The same applicable structure answers a narrower question for an authored
ASSIGNMENT — one member named with one value, rather than a whole row
(:func:`assignment_violation`) — so a case that assigns a value no member of the
model admits is refused from the same walk that refuses a row.

The reference harness runs this so the reference implementation actually rejects
what the `rejected` cases pin — the refusal each language implementation must make.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from typing import Any

from .case import Entity
from .inheritance import (
    ABSTRACT_WRITE_TARGET,
    SUBTYPE_WRITE_METADATA_FIELD,
    SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
    SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
    TYPE_KEY,
    Family,
    inheritance_of,
    is_abstract,
    tag_of,
)
from .portable_literal import PortableLiteralError, decode
from .storage_layout import is_scalar_collection
from .temporality import temporal_axes
from .value_object_resolve import (
    NEUTRAL_LITERAL_RULES,
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    WRITE_VALUE_TYPE_MISMATCH,
    RejectionError,
    decode_typed_literal,
)


def framework_owned_names(entity: Entity) -> frozenset[str]:
    """The attribute names APPLICABLE to *entity* whose values the FRAMEWORK supplies.

    A neutral write input never authors these, so their absence from a row is not a
    caller omission to report: the optimistic-lock version (a write derives its
    advance and its gate from the observation, ADR 0013), each As-Of Axis endpoint
    (the Transaction-Time instant is Clock-supplied flush context and the Valid-Time
    bounds ride on the instruction, ADR 0010), and a table-per-hierarchy tag column,
    which the write derives from the concrete subtype's ``tagValue``
    (`m-inheritance`).
    """
    facts = entity.runtime_facts
    names = {endpoint.name for axis in temporal_axes(facts) for endpoint in (axis.start, axis.end)}
    names.update(
        attribute["name"] for attribute in entity.attributes if attribute.get("optimisticLocking")
    )
    tag = tag_of(facts)
    if tag is not None:
        names.add(tag[0])
    return frozenset(names)


# The framework control keys a case-format write row may carry beside its members
# (`compatibility-case.schema.json` `$defs/writeRow`): flush-time observation
# context, not a declared member. The canonical durable instruction forbids them
# outright, so a row that may not carry one is already refused at schema validation.
_ROW_CONTROL_KEYS = frozenset({"observedVersion"})


def undeclared_members(entity: Entity, row: Mapping[str, Any]) -> list[str]:
    """The keys *row* names that *entity* has no member for, sorted.

    Read from the same members :func:`validate_write` walks — *entity*'s
    ancestry-effective Attributes and Value Objects — so the names a row may carry
    and the positions a row is graded against are provably one set, and a concrete
    subtype's row may name an inherited member (`m-inheritance`).
    """
    applicable = {attribute["name"] for attribute in entity.attributes}
    applicable.update(value_object["name"] for value_object in entity.value_objects)
    return sorted(key for key in row if key not in applicable and key not in _ROW_CONTROL_KEYS)


def assignment_violation(
    entity: Entity, name: str, value: Any, *, classify_literals: bool = False
) -> str | None:
    """Why *entity* refuses assigning *value* to its member *name*, or ``None``.

    One member with one value, which is what an EDIT authors, where
    :func:`validate_write` judges a whole row: the member must be one this entity
    HAS — declared on it or inherited from an ancestor (`m-inheritance`), so a
    `Dog` answers for `Pet`'s `licenseId` — and one a caller may assign, and the
    value must be one that member admits. Membership and assignability are two
    verdicts, not one: a primary-key, read-only or framework-owned target is an
    applicable member and is still refused whatever the value, those being the
    framework's to supply, while a name naming neither an applicable Attribute nor
    an applicable Value Object occurrence (a relationship, a sibling branch's
    attribute, a misspelling) is refused as naming nothing to assign to.

    The value itself is judged by the SAME walk a row's is: a scalar against its
    declared neutral type, `null` only where the member is nullable, and a Value
    Object occurrence as one whole document (or a list of them for a `many`),
    because an occurrence binds atomically.

    The message is the refusal's own detail, member-qualified, so a caller reports
    what is wrong with the assignment rather than re-deriving it. With
    *classify_literals*, a literal its declared type cannot decode is instead
    refused by raising its classified ``neutral-literal-*``
    :class:`RejectionError`, the observable a `rejected` case grades.
    """
    keep = NEUTRAL_LITERAL_RULES if classify_literals else frozenset()
    path = f"{entity.name}.{name}"
    attribute = next(
        (candidate for candidate in entity.attributes if candidate["name"] == name), None
    )
    if attribute is not None:
        if attribute.get("primaryKey"):
            return f"{path}: primary-key fields may not be assigned"
        if attribute.get("readOnly"):
            return f"{path}: read-only fields may not be assigned"
        if name in framework_owned_names(entity):
            return f"{path}: framework-owned fields may not be assigned"
        return _violation_detail(
            lambda: _validate_attribute({name: value}, attribute, path=path),
            keep=keep,
        )
    occurrence = next(
        (candidate for candidate in entity.value_objects if candidate["name"] == name), None
    )
    if occurrence is None:
        return f"{path}: names no assignable attribute or value object"
    return _violation_detail(
        lambda: _validate_occurrence({name: value}, occurrence, path=path), keep=keep
    )


def _instant(instruction: Mapping[str, Any], name: str) -> dt.datetime | None:
    """The instant *instruction*'s own timestamp member *name* spells, decoded
    by `m-wire`'s ``timestamp`` codec, or ``None`` when that codec refuses it."""
    try:
        return decode(instruction[name], "timestamp")
    except PortableLiteralError:
        return None


def window_violation(entity: Entity, instruction: Mapping[str, Any]) -> str | None:
    """Why a keyed or target instruction's window does not fit *entity*, or
    ``None`` (`m-unit-work`): a Bitemporal target states ``validFrom``, and
    ``until`` exactly where its verb is bounded, each a canonical finite
    timestamp and ``validFrom`` before ``until``; any other target states no
    window."""
    mutation = str(instruction.get("mutation"))
    bounded = mutation.endswith("Until")
    bitemporal = any(axis.dimension == "valid-time" for axis in temporal_axes(entity.runtime_facts))
    has_start = "validFrom" in instruction
    has_end = "until" in instruction
    if not bitemporal and (bounded or has_start or has_end):
        return f"{entity.name}: this target takes no Valid-Time window"
    if bitemporal and (not has_start or has_end != bounded):
        return f"{entity.name}: {mutation!r} requires validFrom and " + (
            "until" if bounded else "no until"
        )
    if not has_start:
        return None
    start = _instant(instruction, "validFrom")
    if start is None:
        return "validFrom must state a canonical finite timestamp"
    if not has_end:
        return None
    end = _instant(instruction, "until")
    if end is None:
        return "until must state a canonical finite timestamp"
    if start >= end:
        return f"{entity.name}: validFrom must precede until"
    return None


def _target_key_violation(entity: Entity, row: dict[str, Any]) -> str | None:
    """Why a target write's *row* names no object of *entity*, or ``None``
    (`m-unit-work` *Target writes*).

    The row names its object by every primary-key member, none of them null. A
    null one is refused by the key's own non-null type, so it raises its
    classified ``write-required-attribute-missing`` :class:`RejectionError`, the
    observable a `rejected` case grades, rather than answering a detail.
    """
    for attribute in _key_attributes(entity):
        path = f"{entity.name}.{attribute['name']}"
        if attribute["name"] not in row:
            return f"{path}: a target write states every primary-key member"
        if row[attribute["name"]] is None:
            _validate_attribute(row, attribute, path=path)
    return None


def _refuse_target_key_value(entity: Entity, row: dict[str, Any]) -> None:
    """Refuse a stated primary-key member whose literal its type does not
    admit, by its classified ``neutral-literal-*`` rule: the key is the first
    value a target payload judges (`m-unit-work`)."""
    for attribute in _key_attributes(entity):
        _validate_attribute(row, attribute, path=f"{entity.name}.{attribute['name']}")


def _key_attributes(entity: Entity) -> list[dict[str, Any]]:
    return [attribute for attribute in entity.attributes if attribute.get("primaryKey")]


def _target_name_violation(entity: Entity, row: dict[str, Any]) -> str | None:
    """Why a target write's *row* names a member it may not state, judged by
    name before any value (`m-unit-work`): an authored framework-owned member
    first, then one *entity* does not declare."""
    owned = sorted(framework_owned_names(entity).intersection(row))
    if owned:
        return f"{entity.name}.{owned[0]}: framework-owned fields may not be assigned"
    unknown = undeclared_members(entity, row)
    if unknown:
        return f"{entity.name}.{unknown[0]}: names no assignable attribute or value object"
    return None


def target_row_violation(entity: Entity, row: dict[str, Any], *, replaces: bool) -> str | None:
    """Why *entity* refuses the members a target write's *row* states beside
    the key :func:`_target_key_violation` judged, or ``None`` (`m-unit-work`
    *Target writes*).

    Every such member is judged as an assignment (:func:`assignment_violation`).
    A replacement states the object's whole writable state, so it also omits no
    required member a caller may assign; an omitted nullable member is written
    empty, and an omitted `many` value object or scalar collection is its empty
    collection.
    """
    key_names = {
        attribute["name"] for attribute in entity.attributes if attribute.get("primaryKey")
    }
    for name, value in row.items():
        violation = None if name in key_names else assignment_violation(entity, name, value)
        if violation is not None:
            return violation
    if not replaces:
        return None
    framework_owned = framework_owned_names(entity)
    omitted = [
        attribute["name"]
        for attribute in entity.attributes
        if attribute["name"] not in row
        and attribute["name"] not in key_names | framework_owned
        and not attribute.get("readOnly")
        and not attribute.get("nullable", False)
        and not is_scalar_collection(attribute)
    ]
    omitted += [
        value_object["name"]
        for value_object in entity.value_objects
        if value_object["name"] not in row
        and not _is_many(value_object)
        and not value_object.get("nullable", False)
    ]
    if omitted:
        return f"{entity.name}: a replacement states every required member, and omits {omitted}"
    return None


def target_write_violation(
    entity: Entity, entity_defs: list[dict[str, Any]], instruction: Mapping[str, Any]
) -> str | None:
    """Why a target instruction's key, verb, row, revision or window does
    not fit its target, or ``None`` (`m-unit-work` *Target writes*).

    The model decides all five, which the case schema cannot see, in one
    sequence: a key absent or null is refused first
    (:func:`_target_key_violation`); a temporal target is deleted by no target
    write and a Non-Temporal one is terminated by none; the window is judged
    as every keyed one is (:func:`window_violation`); a temporal target states
    a canonical ``ifTxStart`` and a versioned Non-Temporal one ``ifVersion``,
    while an unversioned one has no revision and takes no target write. Only
    then is the row judged: its concrete-subtype shape
    (:func:`validate_subtype_write`), its other member names
    (:func:`_target_name_violation`), a destructive write's naming the key
    alone, its key's value, then the rest as :func:`target_row_violation`
    judges it.
    """
    mutation = instruction.get("mutation")
    row = instruction["row"]
    key_violation = _target_key_violation(entity, row)
    if key_violation is not None:
        return f"a target write of {entity.name} — {key_violation}"
    axes = {axis.dimension for axis in temporal_axes(entity.runtime_facts)}
    if mutation == ("delete" if axes else "terminate"):
        return f"a target write of {entity.name} takes no `{mutation}`"
    window = window_violation(entity, instruction)
    if window is not None:
        return f"a target write of {entity.name} — {window}"
    versioned = any(attribute.get("optimisticLocking") for attribute in entity.attributes)
    revision = "ifTxStart" if axes else "ifVersion" if versioned else None
    if revision is None:
        return f"{entity.name} has no revision to state, so it takes no target write"
    stated = [name for name in ("ifVersion", "ifTxStart") if name in instruction]
    if stated != [revision]:
        return (
            f"a target write of {entity.name} states {stated or 'no revision'}, "
            f"but its target takes `{revision}`"
        )
    if revision == "ifTxStart" and _instant(instruction, revision) is None:
        return (
            f"a target write of {entity.name} — ifTxStart must state a canonical finite timestamp"
        )
    validate_subtype_write(entity, entity_defs, row)
    names = _target_name_violation(entity, row)
    if names is not None:
        return f"a target write of {entity.name} — {names}"
    keys = {attribute["name"] for attribute in _key_attributes(entity)}
    if mutation in ("delete", "terminate", "terminateUntil") and set(row) - keys:
        return f"a target write of {entity.name} by `{mutation}` names its key alone"
    _refuse_target_key_value(entity, row)
    replaces = mutation in ("replace", "replaceUntil")
    violation = target_row_violation(entity, row, replaces=replaces)
    if violation is not None:
        return f"a target write of {entity.name} — {violation}"
    return None


def _violation_detail(
    judge: Callable[[], None], *, keep: frozenset[str] = frozenset()
) -> str | None:
    """*judge*'s refusal detail, or ``None`` when it raises nothing.

    The row walk answers by raising a classified :class:`RejectionError`, because a
    `rejected` case's observable IS the rule it names. An assignment's absence and
    shape refusals have no such observable, so their rule is dropped here and only
    the human-readable detail survives; a refusal whose rule is in *keep* is
    re-raised whole.
    """
    try:
        judge()
    except RejectionError as exc:
        if exc.rule in keep:
            raise
        return exc.detail
    return None


READ_ONLY_WRITE_TARGET = "read-only-write-target"

WRITE_PERSISTENCE_REJECTED_RULES: frozenset[str] = frozenset({READ_ONLY_WRITE_TARGET})


def validate_write_persistence(entity: Entity) -> None:
    """Refuse any write to *entity* when its family's effective Persistence Mode is
    ``read-only`` (`m-unit-work` "Writes to a ReadOnly family").

    Judged once the write's target resolves and before every shape-specific or
    row-level check, so no verb, row, or predicate is weighed for a family that
    accepts no write.
    """
    if entity.effective_persistence == "read-only":
        raise RejectionError(
            READ_ONLY_WRITE_TARGET,
            f"{entity.canonical_name}'s family is read-only and accepts no persistence write",
        )


def validate_write(entity: Entity, row: dict[str, Any]) -> None:
    """Reject *row* pre-SQL if it is invalid against *entity*'s applicable structure.

    Raises :class:`RejectionError` (``.rule`` one of the write rules) on the first
    violation, walking *entity*'s applicable Attributes and then its Value Objects in
    DECLARATION order, each document depth-first. Declaration order is what makes
    the classification a property of the model rather than of the row's authoring
    order, so a row carrying two defects names the same rule however it is spelled.
    Used ONLY for ``rejected`` cases.
    """
    framework_owned = framework_owned_names(entity)
    for attribute in entity.attributes:
        if attribute["name"] in framework_owned:
            continue
        _validate_attribute(row, attribute, path=f"{entity.name}.{attribute['name']}")
    for value_object in entity.value_objects:
        _validate_occurrence(row, value_object, path=f"{entity.name}.{value_object['name']}")


def validate_keyed_row_values(entity: Entity, mutation: str, row: dict[str, Any]) -> None:
    """Judge an admitted keyed row's values without changing bare-row grading:
    an opening's in declaration order, and any other row's key first, the
    object it addresses (`m-unit-work`), then a replacement's other members in
    declaration order and a partial row's in the order it states them."""
    owned = framework_owned_names(entity)
    attributes = {attribute["name"]: attribute for attribute in entity.attributes}
    occurrences = {occurrence["name"]: occurrence for occurrence in entity.value_objects}
    if mutation in {"insert", "insertUntil", "replace", "replaceUntil"}:
        replacing = mutation in {"replace", "replaceUntil"}
        declared = list(attributes.items())
        if replacing:
            declared.sort(key=lambda item: not item[1].get("primaryKey"))
        for name, attribute in declared:
            if name not in owned and not (replacing and attribute.get("readOnly")):
                _validate_attribute(
                    row,
                    attribute,
                    path=f"{entity.name}.{name}",
                )
        for name, occurrence in occurrences.items():
            _validate_occurrence(row, occurrence, path=f"{entity.name}.{name}")
        return
    key_names = {name for name, attribute in attributes.items() if attribute.get("primaryKey")}
    ordered = [name for name in row if name in key_names] + [
        name for name in row if name not in key_names
    ]
    for name in ordered:
        if name in attributes and name not in owned:
            _validate_attribute(
                row,
                attributes[name],
                path=f"{entity.name}.{name}",
            )
        elif name in occurrences:
            _validate_occurrence(row, occurrences[name], path=f"{entity.name}.{name}")


def _is_many(value_object: dict[str, Any]) -> bool:
    return value_object.get("multiplicity", "one") == "many"


def _validate_attribute(document: dict[str, Any], attribute: dict[str, Any], *, path: str) -> None:
    """Validate one scalar Attribute position inside *document*."""
    name = attribute["name"]
    value = document.get(name)
    if is_scalar_collection(attribute):
        _validate_collection(document, attribute, path=path)
        return
    if name not in document or value is None:
        if not attribute.get("nullable", False):
            raise RejectionError(
                WRITE_REQUIRED_ATTRIBUTE_MISSING,
                f"{path}: required attribute (nullable:false) is absent or null",
            )
        return
    decode_typed_literal(value, attribute.get("type"), path)


def _validate_collection(document: dict[str, Any], attribute: dict[str, Any], *, path: str) -> None:
    """Validate one scalar collection position inside *document*.

    An unnamed collection is its empty collection; a named one is never null, is
    an array, and holds one non-null literal of its declared element type per
    position.
    """
    name = attribute["name"]
    if name not in document:
        return
    value = document[name]
    if value is None:
        raise RejectionError(
            WRITE_REQUIRED_ATTRIBUTE_MISSING,
            f"{path}: a scalar collection is never null; assign the empty collection instead",
        )
    if not isinstance(value, list):
        raise RejectionError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: a scalar collection binds a list, got {type(value).__name__}",
        )
    for index, element in enumerate(value):
        if element is None:
            raise RejectionError(
                WRITE_VALUE_TYPE_MISMATCH, f"{path}[{index}]: a collection element is never null"
            )
        decode_typed_literal(element, attribute.get("type"), f"{path}[{index}]")


def _validate_occurrence(
    document: dict[str, Any], value_object: dict[str, Any], *, path: str
) -> None:
    """Validate one Value Object occurrence inside *document*, present or not."""
    name = value_object["name"]
    value = document.get(name)
    if name not in document or value is None:
        # An UNNAMED `many` is its empty collection, never a missing member; naming
        # one explicitly null is refused, because the model gives it no null state.
        zero_state = name not in document and _is_many(value_object)
        if not value_object.get("nullable", False) and not zero_state:
            raise RejectionError(
                WRITE_REQUIRED_VALUE_OBJECT_MISSING,
                f"{path}: required value object (nullable:false) is absent or null",
            )
        return
    _validate_value(value_object, value, path=path)


def _validate_value(value_object: dict[str, Any], value: Any, *, path: str) -> None:
    """Validate a PRESENT, non-null value against *value_object*'s multiplicity."""
    if not _is_many(value_object):
        _validate_document(value_object, value, path=path)
        return
    if not isinstance(value, list):
        raise RejectionError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: a `many` value object binds a list of documents, got {type(value).__name__}",
        )
    for index, element in enumerate(value):
        _validate_document(value_object, element, path=f"{path}[{index}]")


def _validate_document(value_object: dict[str, Any], document: Any, *, path: str) -> None:
    """Validate one document (a `one` occurrence / a `many` element) against its members."""
    if not isinstance(document, dict):
        raise RejectionError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: expected a value-object document, got {type(document).__name__}",
        )
    for attribute in value_object.get("attributes", []):
        _validate_attribute(document, attribute, path=f"{path}.{attribute['name']}")
    for nested in value_object.get("valueObjects", []):
        _validate_occurrence(document, nested, path=f"{path}.{nested['name']}")


# --- concrete-subtype write validation ----------------------------------------
#
# A write to an inheritance family is a CONCRETE-SUBTYPE write: its accepted fields
# are exactly the target's ancestry chain (root + abstract ancestors + own). The
# tag column is FRAMEWORK-OWNED metadata a payload never carries (the write derives
# it from the subtype's `tagValue`), an abstract root / subtype is not a write
# handle, and a per-object write is KEYED — a keyless payload is a set-based write,
# out of scope for this slice. The checks run in a fixed order so a payload that
# trips more than one defect pins the payload-shape rule (keyless -> metadata ->
# sibling) before the target-validity rule (abstract handle); `m-inheritance` fixes
# the same ordering.

_METADATA_PAYLOAD_FIELDS = frozenset({"tag", "tagValue", TYPE_KEY})


def validate_subtype_write(
    target: Entity, entity_defs: list[dict[str, Any]], row: dict[str, Any]
) -> None:
    """Reject *row* pre-SQL if it violates the concrete-subtype write protocol.

    A no-op unless *target* participates in an inheritance family (value-object write
    validation, above, owns a non-inheritance entity). Raises :class:`RejectionError`
    with one of the Phase-7 subtype-write rules.
    """
    if inheritance_of(target.definition) is None:
        return
    defs = [d for d in entity_defs if isinstance(d, dict)]
    family = Family(defs)
    name = target.canonical_name

    # The framework-owned metadata a payload MUST NOT carry: the tag column (its value
    # is derived from the concrete subtype's tagValue), plus the `tag` / `tagValue` /
    # `_type` handles.
    metadata_fields = set(_METADATA_PAYLOAD_FIELDS)
    tag_column = family.tag_column_of(name)
    if tag_column is not None:
        metadata_fields.add(tag_column)

    payload_fields = [key for key in row if key != "observedVersion"]

    # (1) Set-based / keyless. A per-object concrete-subtype write is keyed (the tag
    #     guard rides with the primary-key identity predicates, resolved Q9), so a
    #     payload carrying NO primary-key attribute denotes a set-based (predicate)
    #     write — unsupported for an inheritance family in this slice.
    pk_names = _primary_key_names(family, name)
    if pk_names and not any(pk in row for pk in pk_names):
        raise RejectionError(
            SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
            f"the write input to inheritance family {name!r} carries no primary-key "
            f"attribute ({sorted(pk_names)}); a keyless / predicate-driven set-based "
            f"inheritance write is unsupported",
        )

    # (2) Framework-owned metadata field in the payload.
    for key in payload_fields:
        if key in metadata_fields:
            raise RejectionError(
                SUBTYPE_WRITE_METADATA_FIELD,
                f"the write input carries the framework-owned metadata field {key!r}, "
                f"which a concrete-subtype write derives from the subtype's tagValue "
                f"(m-inheritance), never accepts as input",
            )

    # (3) Sibling / unrelated-branch member. The accepted fields are exactly the
    #     target's ancestry chain, so every authored member the FAMILY declares MUST fit
    #     the ancestry chain of a SINGLE concrete subtype in the target's effective set.
    #     The comparison is restricted to family-declared names: a name the family
    #     declares nowhere sits on no branch, sibling or otherwise, so including it
    #     would make every ancestry chain fail and report a sibling attribute for a
    #     member honesty owns (`m-case-format` "What decides a bare write row").
    #
    #     That restriction ranges over the WHOLE family, never over the target's
    #     effective set (`m-inheritance`: "The rule ranges over the names the family
    #     declares somewhere"). A concrete target's effective set is the target alone,
    #     so measuring against it would make every sibling name look undeclared and
    #     hand the family's own conflict to member honesty — the one judgement that
    #     cannot name it.
    effective = family.effective_concrete_set(name)
    accepted = {concrete: _ancestry_member_names(family, concrete) for concrete in effective}
    declared_anywhere = _family_member_names(family, name)
    domain_fields = {
        key for key in payload_fields if key not in metadata_fields and key in declared_anywhere
    }
    if effective and not any(domain_fields <= names for names in accepted.values()):
        raise RejectionError(
            SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
            f"the write input to {name!r} carries fields {sorted(domain_fields)} that no "
            f"single concrete subtype in {sorted(effective)} accepts; the accepted fields "
            f"are exactly the target's ancestry chain (sibling / unrelated-branch fields "
            f"are invalid)",
        )

    # (4) Abstract target. A well-formed concrete-subtype payload aimed at an abstract
    #     root / subtype is rejected — writes are concrete-subtype only.
    if is_abstract(target.definition):
        raise RejectionError(
            ABSTRACT_WRITE_TARGET,
            f"{name!r} is an abstract root / subtype; a create / update / delete write "
            f"handle must name a concrete subtype",
        )


def _family_member_names(family: Family, name: str) -> frozenset[str]:
    """Every member NAME declared anywhere in *name*'s family.

    The union over the family ROOT's concrete set, so an abstract interior node's
    declarations arrive through the ancestry chains that pass through it. This is
    the domain of the sibling comparison, and it does not depend on which position
    in the family the write targets.
    """
    root = family.root_of(name) or name
    concretes = family.effective_concrete_set(root)
    names = [_ancestry_member_names(family, concrete) for concrete in concretes]
    return frozenset[str]().union(*names) if names else frozenset()


def _ancestry_member_names(family: Family, concrete: str) -> frozenset[str]:
    """The declared member NAMES in *concrete*'s ancestry chain (root -> ... -> self).

    Attributes and top-level Value Objects alike, because both are members a payload
    aimed at *concrete* may name.

    Reads the RAW ancestor definitions, so the synthesized framework-owned tag column
    (added only by the flattened definition) is excluded — it is metadata, not an
    accepted payload field.
    """
    names: set[str] = set()
    for ancestor in family.ancestry(concrete):
        definition = family.defs.get(ancestor, {})
        for member in (definition.get("attributes") or []) + (definition.get("valueObjects") or []):
            member_name = member.get("name")
            if isinstance(member_name, str):
                names.add(member_name)
    return frozenset(names)


def _primary_key_names(family: Family, name: str) -> list[str]:
    """The primary-key attribute names in *name*'s ancestry chain (usually the root's)."""
    names: list[str] = []
    for ancestor in family.ancestry(name):
        for attribute in family.defs.get(ancestor, {}).get("attributes", []) or []:
            if attribute.get("primaryKey") and isinstance(attribute.get("name"), str):
                names.append(attribute["name"])
    return names
