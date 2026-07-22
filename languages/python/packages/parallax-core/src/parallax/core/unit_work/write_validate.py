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
importing `m-value-object`) -- its STRUCTURAL traversal lives in
`parallax.core.descriptor.vo_document` (error-neutral, `vo_path`'s own
pattern), the one scope every caller already depends on; this module renders
ITS OWN rule vocabulary and message text from the returned violation.
`parallax.core.inheritance.validate_write_assignment`'s VO-targeted
assignment-value check (COR-3 Phase 8 confirmation-pass residual P3) reuses
the SAME shared walk rather than forking it. This is the M2 composition-at-
the-engine precedent applied to writes: pure per-concern rule functions in
their owning scopes, ONE shared compose function (this module) both callers
invoke, so the rule ORDER stays a single source of truth regardless of which
scope a given rule's logic lives in.

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
``m-unit-work-005``'s ``{id, balance}`` omitting the required ``owner``, are
exactly this shape). A value-object document, once PRESENT in
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

from collections.abc import Mapping
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.descriptor import (
    UNSET,
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    VoDocumentViolation,
    vo_document_violation,
)
from parallax.core.descriptor.neutral_type import type_matches as _type_matches

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
    instant surface is dimension-explicit"; ADR 0010: the Transaction-Time instant is
    Clock-supplied flush context, never an instruction field; the Valid-Time
    bounds are instruction fields, ``validFrom`` / ``until``, never row members.

    Bare LOCAL axes, never family-resolved: an inheritance participant's own
    declared attributes never include an INHERITED axis's governing columns
    anyway (temporal axes are root-owned metadata a descendant MUST NOT
    redeclare, `m-inheritance` "Inherited members"), so this reduces correctly
    to a no-op for a concrete-subtype ``entity`` — its own bare
    ``as_of_axes`` is already empty in that case.
    """
    columns: set[str] = set()
    by_name = {attribute.name: attribute.column for attribute in entity.attributes}
    for axis in entity.as_of_axes:
        columns.add(by_name[axis.start_attribute])
        columns.add(by_name[axis.end_attribute])
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
    violation = vo_document_violation(vo, value)
    if violation is not None:
        raise _rejected_error(violation, base=f"{owner}.{name}")


# --------------------------------------------------------------------------- #
# Renders THIS module's own rule vocabulary / message text from a shared,     #
# error-neutral `parallax.core.descriptor.vo_document` violation (the         #
# extracted `vo_path`-precedent walk both this module and                     #
# `parallax.core.inheritance.validate_write_assignment` reuse) -- the shared  #
# module owns no text of its own, see its own docstring.                      #
# --------------------------------------------------------------------------- #
def _rejected_error(violation: VoDocumentViolation, *, base: str) -> WriteRejectedError:
    path = _joined(base, violation.path)
    if violation.reason == "not-a-list":
        return WriteRejectedError(
            "write-value-type-mismatch",
            f"{path}: a `many` value object must bind a list of documents, got "
            f"{type(violation.value).__name__}",
        )
    if violation.reason == "not-a-document":
        return WriteRejectedError(
            "write-value-type-mismatch",
            f"{path}: expected a document (mapping), got {type(violation.value).__name__}",
        )
    if violation.reason == "attribute-missing":
        return WriteRejectedError(
            "write-required-attribute-missing", f"{path}: required attribute is absent (or null)"
        )
    if violation.reason == "value-object-missing":
        return WriteRejectedError(
            "write-required-value-object-missing",
            f"{path}: required value object is absent (or null)",
        )
    return WriteRejectedError(
        "write-value-type-mismatch",
        f"{path}: value {violation.value!r} does not match the declared type "
        f"{violation.declared_type!r}",
    )


def _joined(base: str, path: str) -> str:
    """``base`` plus a shared-walk violation's own relative ``path`` — a nested
    member dot-joins, a ``many`` element index attaches bracket-first (no dot,
    matching this module's OWN pre-extraction owner-string convention, e.g.
    ``"Supplier.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


# --------------------------------------------------------------------------- #
# DB-computed write markers (scalar attribute columns only, `m-value-object`   #
# "Writing" marker disambiguation). The m-core neutral type check itself is    #
# `parallax.core.descriptor.neutral_type.type_matches` (imported above as      #
# `_type_matches`) -- the ONE scalar-value-policy check this module and        #
# `parallax.core.inheritance.validate_write_assignment` both apply, so it      #
# lives in the shared scope both already depend on rather than staying forked. #
# --------------------------------------------------------------------------- #
def _is_scalar_write_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return frozenset(cast("Mapping[str, object]", value)) in _MarkerKeys
