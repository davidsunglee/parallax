"""The model-aware write validator (m-value-object write validation x
m-inheritance concrete-subtype write protocol).

:func:`validate_write` is the SHARED validator every ingress carrying a write
ROW calls: the conformance engine's rejected run lane, and both transaction
ingresses through the one keyed judgment they share
(``Transaction._validate_keyed``, reached from the developer verbs' ``_buffer``
and from the model-neutral ``write_neutral``) -- the "one validator, many
callers" pattern ``validate_predicate`` established
(`parallax.core.predicate.validate`): the SAME rule classification and check
order runs on every path, so they cannot drift.

A PREDICATE-SELECTED write reaches it nowhere (``write_neutral``'s own predicate
route, ``_predicate_writes.buffer_predicate``): it selects rows by predicate and
carries assignments rather than a row, so there is no write row for a row
validator to measure, and member-name honesty
(:func:`~parallax.core.unit_work.instructions.validate_instruction`) is the whole
of what its ingress runs.

Placement (`core/spec/modules.md` §7 DAG): ``m-unit-work`` depends on
``m-predicate``, ``m-db-port``, and ``m-temporal-read`` only, and its
import-linter contract forbids
``parallax.core.value_object`` outright (no module outside that scope's own DAG
edge may reach it) -- but does NOT forbid ``parallax.core.inheritance``
(transitively reachable through the ``m-predicate --> m-inheritance`` edge).
So the payload-shape / target-validity rules (`m-inheritance` "Concrete-subtype
writes") are PURE functions living in their own owning scope
(:func:`parallax.core.inheritance.validate_subtype_write`) and called directly
from here; the declared-composite walk (`m-value-object` "Writing") cannot
reach its own owning scope's helpers at all, so its structural traversal is the
Metadata reading `m-metamodel` owns
(:func:`~parallax.core.metamodel.vo_document_violation`, error-neutral) and this
module renders ITS OWN rule vocabulary and message text from the returned
violation. This applies the composition-at-the-engine pattern to writes: pure
per-concern rule functions in their owning scopes, ONE shared compose function
(this module) both callers invoke, so the rule ORDER stays a single source of
truth regardless of which scope a given rule's logic lives in.

Check order: the inheritance payload-shape/target-validity rules run FIRST,
unconditionally, whenever ``entity`` participates in a family -- resolving
those rules does not need (and must not wait on) the value-object composite,
and a malformed inheritance payload has no well-defined "target entity" for the
composite walk to run against (`m-inheritance` "A validator checks these
payload-shape rules... before the target-validity rule"). The declared-composite
walk (required-attribute / required-value-object / value-type-mismatch) runs
second, over ``entity``'s family-effective scalar attributes and value objects
(`m-inheritance` "Inherited members"), so an inherited required member and an
inherited Attribute's declared type are enforced on a concrete-subtype write.

``mutation`` classifies whether ``row`` is expected to be a FULL document
(``insert`` / ``insertUntil`` -- every declared member must be present, save a
``many`` Value Object occurrence, whose absence IS its empty collection rather
than a member to require, `m-value-object`) or a SPARSE row (``update`` /
``delete`` / ``terminate`` / ``updateUntil`` /
``terminateUntil`` -- an ABSENT top-level member is simply untouched, never a
violation; the corpus's own sparse keyed-update goldens, e.g.
``m-unit-work-005``'s ``{id, balance}`` omitting the required ``owner``, are
exactly this shape). Sparseness licenses an absent member, never a VALUE, so
naming a ``many`` occurrence explicitly NULL is refused under either
classification: null is a state the model gives it none of, so a row carrying
one has not left the member alone. A value-object document, once PRESENT in
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
from parallax.core.base import coerce_neutral_input, matches_neutral_type
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    ValueObjectMetadata,
    VoDocumentViolation,
    vo_document_violation,
)

__all__ = ["WriteRejectedError", "validate_write"]

# The full-document mutations: every declared member must be present, except a
# `many` Value Object occurrence, which has no absent state to require. Every
# other keyed mutation carries a SPARSE row (the primary key plus whichever
# members the caller actually touched) -- an absent top-level member there is
# untouched, never a violation.
_FULL_DOCUMENT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})

_MarkerKeys: Final[tuple[frozenset[str], ...]] = (frozenset({"computed"}), frozenset({"increment"}))


class WriteRejectedError(ValueError):
    """A write payload violates a `then.rejectedRule` write-validation rule
    (`m-value-object` write validation, `m-inheritance` concrete-subtype write
    protocol) and MUST be refused pre-SQL. ``rule`` is the exact classification.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def validate_write(
    entity: EntityMetadata,
    row: Mapping[str, object],
    model: Metamodel,
    *,
    mutation: str = "insert",
) -> None:
    """Validate ``row`` (a neutral write row targeting ``entity``) pre-SQL.

    Raises :class:`WriteRejectedError` naming the violated rule. See the module
    docstring for the check order and the mutation-aware required-ness rule.

    The required-attribute / required-value-object / value-type walk runs over
    ``entity``'s FAMILY-EFFECTIVE member set (`m-inheritance` "Inherited
    members"), so an inherited required member is required of a subtype write
    and an inherited Attribute's declared type is enforced — a standalone entity
    contributes only its own declarations.

    A framework-owned Attribute is outside that walk entirely: the framework
    supplies its value, so its absence from a write row is not a caller omission
    to report. That covers the milestone interval bounds, which are never part of
    the neutral write input at all (`m-unit-work` "the instant surface is
    dimension-explicit"; ADR 0010: the Transaction-Time instant is Clock-supplied
    flush context and the Valid-Time bounds are the instruction's own
    ``validFrom`` / ``until``), and the optimistic-lock version, which a write
    derives rather than reads off the row (ADR 0013). The designation reaches an
    inherited bound because the applicable-member set carries the root's own
    Attributes, and root-owned axis metadata is exactly what designated them.
    """
    try:
        inheritance.validate_subtype_write(model, entity, row)
    except inheritance.InheritanceError as exc:
        raise WriteRejectedError(exc.rule, str(exc)) from exc
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    full_document = mutation in _FULL_DOCUMENT_MUTATIONS
    owner = entity.identity.name
    for attribute in view.applicable_attributes:
        if attribute.framework_owned:
            continue
        _check_entity_attribute(row, attribute, required=full_document, owner=owner)
    for value_object in view.applicable_value_objects:
        _check_value_object_member(row, value_object, required=full_document, owner=owner)


# --------------------------------------------------------------------------- #
# The entity's own top-level scalar attributes (depth 0): a DB-computed marker #
# exempts a marker-shaped value; the concept does not exist below the top      #
# level (`m-value-object` "Writing").                                          #
# --------------------------------------------------------------------------- #
def _check_entity_attribute(
    row: Mapping[str, object], attribute: AttributeMetadata, *, required: bool, owner: str
) -> None:
    name = attribute.identity.name
    value = row.get(name)
    if name not in row or value is None:
        if required and not attribute.nullable:
            raise WriteRejectedError(
                "write-required-attribute-missing",
                f"{owner}.{name}: required attribute is absent (or null)",
            )
        return
    if _is_scalar_write_marker(value):
        return
    if not matches_neutral_type(coerce_neutral_input(value, attribute.type), attribute.type):
        raise WriteRejectedError(
            "write-value-type-mismatch",
            f"{owner}.{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


# --------------------------------------------------------------------------- #
# Value-object members: a PRESENT document is always validated as a whole,     #
# regardless of the outer mutation. An UNNAMED `many` occurrence is not an     #
# absence to require -- `m-document-codec` fixes Missing and [] as one logical #
# zero state, so the write stores the empty array. Naming one explicitly null  #
# is refused at EVERY mutation, sparse ones included: the model gives a `many` #
# no null state to name, so the null is not a member left untouched but a      #
# value the occurrence cannot hold -- one that would bind SQL NULL to a NOT    #
# NULL Column or patch JSON null at the occurrence's Document Path.            #
# --------------------------------------------------------------------------- #
def _check_value_object_member(
    row: Mapping[str, object], vo: ValueObjectMetadata, *, required: bool, owner: str
) -> None:
    name = vo.identity.path[-1]
    value = row.get(name)
    if name not in row or value is None:
        if vo.multiplicity is Multiplicity.MANY:
            if name in row:
                raise WriteRejectedError(
                    "write-required-value-object-missing",
                    f"{owner}.{name}: a `many` value object is never null",
                )
            return
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
# Renders THIS module's own rule vocabulary / message text from the shared,   #
# error-neutral `m-metamodel` document violation -- that reading owns no text #
# of its own, see its own docstring.                                          #
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
    matching this module's OWN owner-string convention, e.g.
    ``"Supplier.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


# --------------------------------------------------------------------------- #
# DB-computed write markers (scalar attribute columns only, `m-value-object`   #
# "Writing" marker disambiguation).                                            #
# --------------------------------------------------------------------------- #
def _is_scalar_write_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return frozenset(cast("Mapping[str, object]", value)) in _MarkerKeys
