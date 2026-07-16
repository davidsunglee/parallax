"""The model-aware write validator (m-value-object write validation x
m-inheritance concrete-subtype write protocol, COR-3 Phase 8 increment 2).

:func:`validate_write` is the SHARED validator both the conformance engine's
rejected run lane and the developer transaction verbs (``Transaction._buffer``)
call -- the "one validator, two callers" pattern the Phase-7 ``validate_operation``
precedent set (`parallax.core.op_algebra.validate`): the SAME rule classification
and check order runs on both paths, so they cannot drift.

Placement (`core/spec/modules.md` §7 DAG): ``m-unit-work`` depends on
``m-op-algebra`` and ``m-db-port`` only, and its import-linter contract forbids
``parallax.core.value_object`` outright (no module outside that scope's own DAG
edge may reach it) -- but does NOT forbid ``parallax.core.inheritance``
(transitively reachable through the ``m-op-algebra --> m-inheritance`` edge).
So the payload-shape / target-validity rules (`m-inheritance` "Concrete-subtype
writes") are PURE functions living in their own owning scope
(:func:`parallax.core.inheritance.validate_subtype_write`) and called directly
from here; the declared-composite walk (`m-value-object` "Writing") cannot
reach its own owning scope's helpers at all, so -- mirroring the established
`parallax.core.descriptor.vo_path` precedent (`m-op-algebra` / `m-sql` resolve
value-object paths directly against `m-descriptor` records rather than
importing `m-value-object`) -- it is implemented directly against
`parallax.core.descriptor` records here, the one scope every caller already
depends on. This is the M2 composition-at-the-engine precedent applied to
writes: pure per-concern rule functions in their owning scopes, ONE shared
compose function (this module) both callers invoke, so the rule ORDER stays a
single source of truth regardless of which scope a given rule's logic lives in.

Check order: the inheritance payload-shape/target-validity rules run FIRST,
unconditionally, whenever ``entity`` participates in a family -- resolving
those rules does not need (and must not wait on) the value-object composite,
and a malformed inheritance payload has no well-defined "target entity" for the
composite walk to run against (`m-inheritance` "A validator checks these
payload-shape rules... before the target-validity rule"). The declared-composite
walk (required-attribute / required-value-object / value-type-mismatch) runs
second, over ``entity``'s own scalar attributes and value objects.

``mutation`` classifies whether ``row`` is expected to be a FULL document
(``insert`` / ``insertUntil`` -- every declared member must be present) or a
SPARSE row (``update`` / ``delete`` / ``terminate`` / ``updateUntil`` /
``terminateUntil`` -- an ABSENT top-level member is simply untouched, never a
violation; the corpus's own sparse keyed-update goldens, e.g.
``m-unit-work-005``'s ``{id, balance, version}`` omitting the required
``owner``, are exactly this shape). A value-object document, once PRESENT in
the row at any mutation kind, is always validated as a whole (`m-value-object`
"one atomic document bind" -- there is no sparse write below the document
boundary): every declared member the document's OWN composite requires must be
present inside it, regardless of the outer mutation's sparseness. The rejected
run lane's own ``when.write`` input carries no mutation context at all (a bare
neutral write row, `m-case-format` "Read targeting" ①) and is graded against
the strictest, full-document interpretation (the default), matching every
witnessed rejected case's own complete-except-for-the-one-defect shape.

A scalar ATTRIBUTE column's value that is a single-key mapping shaped
``{"computed": ...}`` / ``{"increment": ...}`` is a DB-computed write marker
(`m-value-object` "Writing" -- pk-gen / the framework version advance) and is
exempt from type-checking; the disambiguation is by the field's declared
metamodel ROLE (scalar attribute vs. value object), never by the value's
shape, so this exemption applies ONLY at a scalar attribute leaf, never inside
a value-object document (a value object binds its whole document even when
that document happens to be shaped like a marker).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.descriptor import (
    UNSET,
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = ["WriteRejectedError", "validate_write"]

# The full-document mutations: every declared member must be present. Every
# other keyed mutation carries a SPARSE row (the primary key plus whichever
# members the caller actually touched) -- an absent top-level member there is
# untouched, never a violation.
_FULL_DOCUMENT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})

_MarkerKeys: Final[tuple[frozenset[str], ...]] = (frozenset({"computed"}), frozenset({"increment"}))

# A value-object container: the top-level document or any nested value object
# (mirrors `parallax.core.value_object.Container`, restated here -- that scope
# is unreachable from `m-unit-work`, see the module docstring).
_VoContainer = ValueObject | NestedValueObject


class WriteRejectedError(ValueError):
    """A write payload violates a `then.rejectedRule` write-validation rule
    (`m-value-object` write validation, `m-inheritance` concrete-subtype write
    protocol) and MUST be refused pre-SQL. ``rule`` is the exact classification.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def _temporal_axis_columns(entity: Entity) -> frozenset[str]:
    """The physical columns ``entity``'s OWN declared as-of axes govern (the
    milestone interval bounds) — excluded from the required/type walk below,
    since they are NEVER part of the neutral write input (`m-unit-work` "the
    instant surface is axis-explicit"; ADR 0010: the processing instant is
    Clock-supplied flush context, never an instruction field; the business
    bounds are axis-explicit INSTRUCTION fields, ``businessFrom`` /
    ``businessTo``, never row members, COR-3 Phase 8 increment 4).

    Bare LOCAL axes, never family-resolved: an inheritance participant's own
    declared attributes never include an INHERITED axis's governing columns
    anyway (temporal axes are root-owned metadata a descendant MUST NOT
    redeclare, `m-inheritance` "Inherited members"), so this reduces correctly
    to a no-op for a concrete-subtype ``entity`` — its own bare
    ``as_of_attributes`` is already empty in that case.
    """
    columns: set[str] = set()
    for aoa in entity.as_of_attributes:
        columns.add(aoa.from_column)
        columns.add(aoa.to_column)
    return frozenset(columns)


def validate_write(
    entity: Entity,
    row: Mapping[str, object],
    meta: Metamodel,
    *,
    mutation: str = "insert",
) -> None:
    """Validate ``row`` (a neutral write row targeting ``entity``) pre-SQL.

    Raises :class:`WriteRejectedError` naming the violated rule. See the module
    docstring for the check order and the mutation-aware required-ness rule.
    """
    try:
        inheritance.validate_subtype_write(meta, entity, row)
    except inheritance.InheritanceError as exc:
        raise WriteRejectedError(exc.rule, str(exc)) from exc
    full_document = mutation in _FULL_DOCUMENT_MUTATIONS
    axis_columns = _temporal_axis_columns(entity)
    for attribute in entity.attributes:
        if attribute.column in axis_columns:
            continue
        _check_entity_attribute(row, attribute, required=full_document, owner=entity.name)
    for vo in entity.value_objects:
        _check_value_object_member(row, vo, required=full_document, owner=entity.name)


# --------------------------------------------------------------------------- #
# The entity's own top-level scalar attributes (depth 0): a declared `default` #
# or a DB-computed marker exempts an absent/marker-shaped value; neither       #
# concept exists below the top level (`m-value-object` "Writing").             #
# --------------------------------------------------------------------------- #
def _check_entity_attribute(
    row: Mapping[str, object], attribute: Attribute, *, required: bool, owner: str
) -> None:
    name = attribute.name
    present = name in row
    value = row.get(name)
    if not present or value is None:
        if required and not attribute.nullable and attribute.default is UNSET:
            raise WriteRejectedError(
                "write-required-attribute-missing",
                f"{owner}.{name}: required attribute is absent (or null)",
            )
        return
    if _is_scalar_write_marker(value):
        return
    if not _type_matches(value, attribute.type):
        raise WriteRejectedError(
            "write-value-type-mismatch",
            f"{owner}.{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


# --------------------------------------------------------------------------- #
# Value-object members (top-level or nested, arbitrary depth): a PRESENT      #
# document is always validated as a whole, regardless of the outer mutation.  #
# --------------------------------------------------------------------------- #
def _check_value_object_member(
    row: Mapping[str, object], vo: _VoContainer, *, required: bool, owner: str
) -> None:
    name = vo.name
    present = name in row
    value = row.get(name)
    if not present or value is None:
        if required and not vo.nullable:
            raise WriteRejectedError(
                "write-required-value-object-missing",
                f"{owner}.{name}: required value object is absent (or null)",
            )
        return
    _walk_vo_document(vo, value, owner=f"{owner}.{name}")


def _walk_vo_document(container: _VoContainer, value: object, *, owner: str) -> None:
    if container.cardinality == "many":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise WriteRejectedError(
                "write-value-type-mismatch",
                f"{owner}: a `many` value object must bind a list of documents, got "
                f"{type(value).__name__}",
            )
        # An empty array is fine (m-value-object: "emptiness is not a nullability
        # violation") -- each present element is still a whole document.
        elements = cast("Sequence[object]", value)
        for index, element in enumerate(elements):
            _walk_vo_element(container, element, owner=f"{owner}[{index}]")
        return
    _walk_vo_element(container, value, owner=owner)


def _walk_vo_element(container: _VoContainer, value: object, *, owner: str) -> None:
    if not isinstance(value, Mapping):
        raise WriteRejectedError(
            "write-value-type-mismatch",
            f"{owner}: expected a document (mapping), got {type(value).__name__}",
        )
    document = cast("Mapping[str, object]", value)
    for attribute in container.attributes:
        _check_vo_attribute(document, attribute, owner=owner)
    for nested in container.value_objects:
        # Always required-if-declared once inside a PRESENT document: there is
        # no sparse write below the value-object document boundary.
        _check_value_object_member(document, nested, required=True, owner=owner)


def _check_vo_attribute(
    document: Mapping[str, object], attribute: ValueObjectAttribute, *, owner: str
) -> None:
    name = attribute.name
    present = name in document
    value = document.get(name)
    if not present or value is None:
        if not attribute.nullable:
            raise WriteRejectedError(
                "write-required-attribute-missing",
                f"{owner}.{name}: required attribute is absent (or null)",
            )
        return
    if not _type_matches(value, attribute.type):
        raise WriteRejectedError(
            "write-value-type-mismatch",
            f"{owner}.{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


# --------------------------------------------------------------------------- #
# DB-computed write markers (scalar attribute columns only, `m-value-object`   #
# "Writing" marker disambiguation) and the m-core neutral type check.          #
# --------------------------------------------------------------------------- #
def _is_scalar_write_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return frozenset(cast("Mapping[str, object]", value)) in _MarkerKeys


def _type_matches(value: object, neutral_type: str) -> bool:
    """Whether ``value`` matches ``neutral_type`` -- the m-core neutral scalar
    vocabulary (python.md §2), accepting BOTH the portable JSON-literal shape a
    corpus-authored row carries (int/float/str/bool -- YAML's own numeric/date
    parsing) and the native driver-typed shape a Python entity instance's
    serialized row carries (`Decimal`/`date`/`time`/`datetime`/`UUID`/`bytes`)
    -- the write side's counterpart of `m-op-algebra`'s `_literal_matches_type`
    (a category-level check, not full precision/range/maxLength policing,
    which stays a separate, unclaimed concern here exactly as it does there).
    """
    if isinstance(value, bool):
        return neutral_type == "boolean"
    if neutral_type == "boolean":
        return False
    if neutral_type in ("int32", "int64"):
        return isinstance(value, int)
    if neutral_type in ("float32", "float64"):
        return isinstance(value, (int, float))
    if neutral_type.startswith("decimal"):
        return isinstance(value, (int, float, decimal.Decimal))
    if neutral_type == "string":
        return isinstance(value, str)
    if neutral_type == "bytes":
        return isinstance(value, (bytes, str))
    if neutral_type == "date":
        return isinstance(value, str) or (
            isinstance(value, dt.date) and not isinstance(value, dt.datetime)
        )
    if neutral_type == "time":
        return isinstance(value, (str, dt.time))
    if neutral_type == "timestamp":
        return isinstance(value, (str, dt.datetime))
    if neutral_type == "uuid":
        return isinstance(value, (str, uuid.UUID))
    return True  # pragma: no cover - defensive: every m-core neutral type is covered above
