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
