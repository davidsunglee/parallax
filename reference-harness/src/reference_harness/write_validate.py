"""Model-aware WRITE validation for the ``rejected`` case shape (m-value-object).

A write `rejected` case (m-case-format, resolved Q7) carries a neutral write row
(①) that a model-aware validator MUST refuse **before any DML is emitted**. The row
is resolved against the target's **declared** structure — its scalar Attributes and
its Value Objects, recursively — and this module raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the rule:

* ``write-required-attribute-missing`` — a required (`nullable: false`) attribute is
  absent (or null) at any depth, the entity's own top-level Attributes included;
* ``write-required-value-object-missing`` — a required `one` value object is absent
  (or null) at any depth, or a `many` occurrence is present as an explicit null. An
  ABSENT `many` is not a violation: absence and the empty array are one logical zero
  state, so an unnamed `many` occurrence is the empty collection (m-value-object,
  m-document-codec);
* ``write-value-type-mismatch`` — a value's type differs from what its declared
  position admits: a scalar leaf whose literal does not match the Attribute's
  neutral type, a non-document at a `one` occurrence, or a non-list (or a list of
  non-documents) at a `many` one. A value object binds **atomically as one whole
  document** (m-value-object), so a scalar standing where a document is declared is
  a type mismatch rather than an absence.

The bare `when.write` row carries no mutation context, so it is graded as a FULL
document: every declared member must be present, save a `many` occurrence, whose
absence IS its empty collection. Two member kinds are outside the walk because the
framework, never the caller, supplies their values — the optimistic-lock version
and the As-Of Axis endpoints (:func:`framework_owned_names`), plus a
table-per-hierarchy tag column, whose presence the concrete-subtype protocol below
refuses outright.

The reference harness runs this so the reference implementation actually rejects
what the `rejected` cases pin — the refusal each language implementation must make.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .case import Entity
from .inheritance import (
    ABSTRACT_WRITE_TARGET,
    SUBTYPE_WRITE_METADATA_FIELD,
    SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
    SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
    Family,
    inheritance_of,
    is_abstract,
    tag_of,
)
from .temporality import temporal_axes
from .value_object_resolve import (
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    WRITE_VALUE_TYPE_MISMATCH,
    RejectionError,
    literal_matches_type,
)

# A single-key mapping shaped like one of these is a DB-computed write marker
# (`m-value-object` "Writing" -- pk-gen / the framework version advance) and is
# exempt from type checking. The disambiguation is by the field's declared
# metamodel ROLE, never by the value's shape, so the exemption holds at a scalar
# Attribute alone -- never inside a document, where a value object binds its whole
# document even when that document happens to be shaped like a marker.
_MARKER_KEYS = (frozenset({"computed"}), frozenset({"increment"}))


def framework_owned_names(entity: Entity) -> frozenset[str]:
    """The declared attribute names on *entity* whose values the FRAMEWORK supplies.

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
    """The keys *row* names that *entity* declares no member for, sorted.

    Read from the same declarations :func:`validate_write` walks — *entity*'s
    ancestry-effective Attributes and Value Objects — so the names a row may carry
    and the positions a row is graded against are provably one set, and a concrete
    subtype's row may name an inherited member (`m-inheritance`).
    """
    declared = {attribute["name"] for attribute in entity.attributes}
    declared.update(value_object["name"] for value_object in entity.value_objects)
    return sorted(key for key in row if key not in declared and key not in _ROW_CONTROL_KEYS)


def validate_write(entity: Entity, row: dict[str, Any]) -> None:
    """Reject *row* pre-SQL if it is invalid against *entity*'s declared structure.

    Raises :class:`RejectionError` (``.rule`` one of the write rules) on the first
    violation, walking *entity*'s declared Attributes and then its Value Objects in
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


def _is_many(value_object: dict[str, Any]) -> bool:
    return value_object.get("multiplicity", "one") == "many"


def _is_marker(value: Any) -> bool:
    return isinstance(value, dict) and frozenset(value) in _MARKER_KEYS


def _validate_attribute(
    document: dict[str, Any], attribute: dict[str, Any], *, path: str, marker_exempt: bool = True
) -> None:
    """Validate one scalar Attribute position inside *document*."""
    name = attribute["name"]
    value = document.get(name)
    if name not in document or value is None:
        if not attribute.get("nullable", False):
            raise RejectionError(
                WRITE_REQUIRED_ATTRIBUTE_MISSING,
                f"{path}: required attribute (nullable:false) is absent or null",
            )
        return
    if marker_exempt and _is_marker(value):
        return
    if not literal_matches_type(value, attribute.get("type")):
        raise RejectionError(
            WRITE_VALUE_TYPE_MISMATCH,
            f"{path}: value {value!r} does not match the declared type {attribute.get('type')!r}",
        )


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
        _validate_attribute(
            document, attribute, path=f"{path}.{attribute['name']}", marker_exempt=False
        )
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

_METADATA_PAYLOAD_FIELDS = frozenset({"tag", "tagValue", "familyVariant"})


def validate_subtype_write(
    target: Entity, entity_defs: list[dict[str, Any]], row: dict[str, Any]
) -> None:
    """Reject *row* pre-SQL if it violates the concrete-subtype write protocol.

    A no-op unless *target* participates in an inheritance family (value-object write
    validation, above, owns a non-inheritance entity). Raises :class:`RejectionError`
    with one of the Phase-7 subtype-write rules; used ONLY for ``rejected`` cases.
    """
    if inheritance_of(target.definition) is None:
        return
    defs = [d for d in entity_defs if isinstance(d, dict)]
    family = Family(defs)
    name = target.name

    # The framework-owned metadata a payload MUST NOT carry: the tag column (its value
    # is derived from the concrete subtype's tagValue), plus the `tag` / `tagValue` /
    # `familyVariant` handles.
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
    effective = family.effective_concrete_set(name)
    accepted = {concrete: _ancestry_member_names(family, concrete) for concrete in effective}
    declared_anywhere = frozenset[str]().union(*accepted.values()) if accepted else frozenset()
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
