"""Model-aware WRITE validation for the ``rejected`` case shape (m-value-object).

A write `rejected` case (m-case-format, resolved Q7) carries a neutral write row
(①) whose value-object document a model-aware validator MUST refuse **before any
DML is emitted**. A value object is written **atomically as one whole document**
(m-value-object), so the document must be structurally complete against its
*declared* recursive structure. This module validates each value-object document in
the row and raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the rule:

* ``write-required-attribute-missing`` — a required (`nullable: false`) attribute is
  absent (or null) at any depth;
* ``write-required-value-object-missing`` — a required nested value object is absent
  (or null), or a required `many` array is absent (an EMPTY array is fine —
  emptiness is not a nullability violation);
* ``write-value-type-mismatch`` — a document field value's type differs from the
  attribute's declared neutral type.

Scalar-attribute presence/typing is out of scope here (a value object's write
validation is about the DOCUMENT), so a non-value-object key is ignored. The
reference harness runs this so the reference implementation actually rejects what
the `rejected` cases pin — the refusal each language implementation must make.
"""

from __future__ import annotations

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
)
from .value_object_resolve import (
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    WRITE_VALUE_TYPE_MISMATCH,
    RejectionError,
    find_top_value_object,
    literal_matches_type,
)


def validate_write(entity: Entity, row: dict[str, Any]) -> None:
    """Reject *row* pre-SQL if a value-object document is structurally invalid.

    Raises :class:`RejectionError` (``.rule`` one of the write rules) on the first
    violation, walking each value-object document depth-first in declaration order.
    Used ONLY for ``rejected`` cases.
    """
    # A required top-level value object omitted ENTIRELY from the row is a violation
    # (a present-but-null one is caught below via `_validate_member`).
    for value_object in entity.value_objects:
        if not value_object.get("nullable", False) and value_object["name"] not in row:
            raise RejectionError(
                WRITE_REQUIRED_VALUE_OBJECT_MISSING,
                f"required value object {value_object['name']!r} is absent from the write input",
            )
    for key, value in row.items():
        if key == "observedVersion":
            continue
        value_object = find_top_value_object(entity, key)
        if value_object is None:
            # A scalar attribute (or an unknown key): scalar-attribute validation is
            # out of scope for value-object write validation.
            continue
        _validate_member(value_object, value)


def _validate_member(value_object: dict[str, Any], value: Any) -> None:
    """Validate a value at a value-object member position against its declaration."""
    nullable = value_object.get("nullable", False)
    cardinality = value_object.get("cardinality", "one")
    if value is None:
        if not nullable:
            raise RejectionError(
                WRITE_REQUIRED_VALUE_OBJECT_MISSING,
                f"required value object {value_object['name']!r} (nullable:false) is "
                f"absent or null",
            )
        return
    if cardinality == "many":
        # `nullable: false` requires the ARRAY be present (satisfied — value is not
        # None here); an empty array is fine. Validate each element as a document.
        if isinstance(value, list):
            for element in value:
                _validate_document(value_object, element)
        return
    _validate_document(value_object, value)


def _validate_document(value_object: dict[str, Any], document: Any) -> None:
    """Validate one document (a `one` member / a `many` element) against its members."""
    if not isinstance(document, dict):
        # A non-object where an object is expected is out of the negatives' scope
        # (the absence-collapse rule reads it as not-present at read time).
        return
    for attribute in value_object.get("attributes", []):
        name = attribute["name"]
        present = name in document and document[name] is not None
        if not present:
            if not attribute.get("nullable", False):
                raise RejectionError(
                    WRITE_REQUIRED_ATTRIBUTE_MISSING,
                    f"required attribute {value_object['name']}.{name} (nullable:false) is "
                    f"absent or null",
                )
            continue
        if not literal_matches_type(document[name], attribute.get("type")):
            raise RejectionError(
                WRITE_VALUE_TYPE_MISMATCH,
                f"{value_object['name']}.{name} value {document[name]!r} does not match "
                f"declared type {attribute.get('type')!r}",
            )
    for nested in value_object.get("valueObjects", []):
        _validate_member(nested, document.get(nested["name"]))


# --- concrete-subtype write validation (m-inheritance, Phase 7) --------------
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

    # (3) Sibling / unrelated-branch attribute. The accepted fields are exactly the
    #     target's ancestry chain, so every authored (non-metadata) attribute MUST fit
    #     the ancestry chain of a SINGLE concrete subtype in the target's effective set.
    domain_fields = {key for key in payload_fields if key not in metadata_fields}
    effective = family.effective_concrete_set(name)
    if effective and not any(
        domain_fields <= _ancestry_attribute_names(family, concrete) for concrete in effective
    ):
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


def _ancestry_attribute_names(family: Family, concrete: str) -> set[str]:
    """The declared attribute NAMES in *concrete*'s ancestry chain (root -> ... -> self).

    Reads the RAW ancestor definitions, so the synthesized framework-owned tag column
    (added only by the flattened definition) is excluded — it is metadata, not an
    accepted payload field.
    """
    names: set[str] = set()
    for ancestor in family.ancestry(concrete):
        for attribute in family.defs.get(ancestor, {}).get("attributes", []) or []:
            attr_name = attribute.get("name")
            if isinstance(attr_name, str):
                names.add(attr_name)
    return names


def _primary_key_names(family: Family, name: str) -> list[str]:
    """The primary-key attribute names in *name*'s ancestry chain (usually the root's)."""
    names: list[str] = []
    for ancestor in family.ancestry(name):
        for attribute in family.defs.get(ancestor, {}).get("attributes", []) or []:
            if attribute.get("primaryKey") and isinstance(attribute.get("name"), str):
                names.append(attribute["name"])
    return names
