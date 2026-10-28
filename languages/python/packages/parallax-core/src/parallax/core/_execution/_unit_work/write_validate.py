from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeMetadata,
    AuthoringViolation,
    EntityMetadata,
    MemberDefinition,
    Metamodel,
    Multiplicity,
    ScalarDefinition,
    ValueObjectMetadata,
)

__all__ = [
    "MarkerJudgment",
    "WriteRejectedError",
    "authoring_refusal_error",
    "joined_path",
    "validate_write",
]

type MarkerJudgment = Callable[[str, Mapping[str, object]], None]
"""Judges the DB-computed marker a row states at one top-level scalar
Attribute, named by its canonical name, at that member's judgment point."""

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
    known_failures: Mapping[int, AuthoringViolation],
    markers: MarkerJudgment | None = None,
) -> None:
    """Validate ``row`` (a neutral write row targeting ``entity``) pre-SQL.

    Raises :class:`WriteRejectedError` naming the violated rule. The caller has
    already applied the Inheritance payload-shape and target rules, and
    ``known_failures`` is the authoring walk's evidence for ``row``, keyed by
    member position. The row is sparse — the primary key plus whichever members
    the caller touched — so an absent top-level member is untouched, never a
    violation, while every present Value Object remains a whole document.

    The null / value-type walk runs over
    ``entity``'s FAMILY-EFFECTIVE member set (`m-inheritance` "Inherited
    members"), so an inherited Attribute's declared type is enforced — a
    standalone entity contributes only its own declarations.

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

    A DB-computed marker a top-level scalar Attribute states is judged by
    ``markers`` where that member is checked; without one it is left unjudged.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    owner = entity.identity.name
    for attribute in view.applicable_attributes:
        if attribute.framework_owned or attribute.identity.name not in row:
            continue
        _check_entity_attribute(
            row,
            attribute,
            owner=owner,
            known_failure=known_failures.get(view.member_selection.position(attribute.identity))
            if known_failures
            else None,
            markers=markers,
        )
    for value_object in view.applicable_value_objects:
        if value_object.identity.path[-1] not in row:
            continue
        _check_value_object_member(
            row,
            value_object,
            owner=owner,
            known_violation=known_failures.get(
                view.member_selection.position(value_object.identity)
            )
            if known_failures
            else None,
        )


# The entity's own top-level scalar attributes (depth 0): a DB-computed marker #


def _check_entity_attribute(
    row: Mapping[str, object],
    attribute: AttributeMetadata,
    *,
    owner: str,
    known_failure: AuthoringViolation | None,
    markers: MarkerJudgment | None,
) -> None:
    name = attribute.identity.name
    value = row[name]
    many = attribute.multiplicity is Multiplicity.MANY
    if value is None:
        if many:
            raise WriteRejectedError(
                "write-required-attribute-missing",
                f"{owner}.{name}: a `many` attribute is never null",
            )
        return
    if not many and _is_scalar_write_marker(value):
        if markers is not None:
            markers(name, cast("Mapping[str, object]", value))
        return
    if known_failure is not None:
        if many:
            raise _rejected_error(known_failure, base=f"{owner}.{name}", many_scalar=True)
        raise WriteRejectedError(
            "write-value-type-mismatch",
            f"{owner}.{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


# absence to require -- `m-document-codec` fixes Missing and [] as one logical #

# is refused at EVERY mutation, sparse ones included: the model gives a `many` #


def _check_value_object_member(
    row: Mapping[str, object],
    vo: ValueObjectMetadata,
    *,
    owner: str,
    known_violation: AuthoringViolation | None,
) -> None:
    name = vo.identity.path[-1]
    if row[name] is None:
        if vo.multiplicity is Multiplicity.MANY:
            raise WriteRejectedError(
                "write-required-value-object-missing",
                f"{owner}.{name}: a `many` value object is never null",
            )
        return
    if known_violation is not None:
        raise _rejected_error(known_violation, base=f"{owner}.{name}")


# error-neutral document-codec finding, which owns no policy text of its own. #
def authoring_refusal_error(
    owner: str, member: MemberDefinition, violation: AuthoringViolation
) -> WriteRejectedError:
    """The refusal of a row's top-level ``member`` for ``violation``, worded
    as this module words the same finding of a validated row."""
    base = f"{owner}.{member.name}"
    scalar = isinstance(member, ScalarDefinition)
    many = member.multiplicity is Multiplicity.MANY
    if not violation.path and violation.reason in ("attribute-missing", "value-object-missing"):
        rule = (
            "write-required-attribute-missing" if scalar else "write-required-value-object-missing"
        )
        kind = "attribute" if scalar else "value object"
        if many:
            return WriteRejectedError(rule, f"{base}: a `many` {kind} is never null")
        return WriteRejectedError(rule, f"{base}: required {kind} is absent (or null)")
    return _rejected_error(violation, base=base, many_scalar=scalar and many)


def _rejected_error(
    violation: AuthoringViolation, *, base: str, many_scalar: bool = False
) -> WriteRejectedError:
    path = joined_path(base, violation.path)
    if violation.reason == "not-a-list":
        expected = "a list of scalar values" if many_scalar else "a list of documents"
        kind = "attribute" if many_scalar else "value object"
        return WriteRejectedError(
            "write-value-type-mismatch",
            f"{path}: a `many` {kind} must bind {expected}, got {type(violation.value).__name__}",
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


def joined_path(base: str, path: str) -> str:
    """``base`` plus a shared-walk violation's own relative ``path`` — a nested
    member dot-joins, a ``many`` element index attaches bracket-first (no dot,
    matching this module's OWN owner-string convention, e.g.
    ``"Supplier.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


def _is_scalar_write_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return frozenset(cast("Mapping[str, object]", value)) in _MarkerKeys
