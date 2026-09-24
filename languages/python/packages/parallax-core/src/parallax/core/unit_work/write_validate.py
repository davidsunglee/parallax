from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.base import NeutralType, coerce_neutral_input, matches_neutral_type
from parallax.core.document_codec._authoring import MAPPING_SOURCE_ACCESS, validate_authoring
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    ValueObjectMetadata,
    VoDocumentViolation,
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
    known_failures: Mapping[int, VoDocumentViolation] | None = None,
    subtype_validated: bool = False,
) -> None:
    """Validate ``row`` (a neutral write row targeting ``entity``) pre-SQL.

    Raises :class:`WriteRejectedError` naming the violated rule. Inheritance
    payload shape and target validity are checked before family-effective member
    validation. Inserts require a full document; other mutations admit sparse
    top-level rows, while every present Value Object remains a whole document.

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
    if not subtype_validated:
        try:
            inheritance.validate_subtype_write(model, entity, row)
        except inheritance.InheritanceError as exc:
            raise WriteRejectedError(exc.rule, str(exc)) from exc
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    failures = (
        validate_authoring(
            view.member_selection.shape,
            row,
            source_access=MAPPING_SOURCE_ACCESS,
            normalize_leaf=_normalize_leaf,
            path=entity.identity.canonical,
            allow_root_markers=True,
        )
        if known_failures is None
        else known_failures
    )
    full_document = mutation in _FULL_DOCUMENT_MUTATIONS
    owner = entity.identity.name
    for attribute in view.applicable_attributes:
        if attribute.framework_owned:
            continue
        _check_entity_attribute(
            row,
            attribute,
            required=full_document,
            owner=owner,
            known_failure=failures.get(view.member_selection.position(attribute.identity)),
        )
    for value_object in view.applicable_value_objects:
        _check_value_object_member(
            row,
            value_object,
            required=full_document,
            owner=owner,
            known_violation=failures.get(view.member_selection.position(value_object.identity)),
        )


# The entity's own top-level scalar attributes (depth 0): a DB-computed marker #


def _check_entity_attribute(
    row: Mapping[str, object],
    attribute: AttributeMetadata,
    *,
    required: bool,
    owner: str,
    known_failure: VoDocumentViolation | None,
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
    if known_failure is not None:
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
    required: bool,
    owner: str,
    known_violation: VoDocumentViolation | None,
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
    if known_violation is not None:
        raise _rejected_error(known_violation, base=f"{owner}.{name}")


def _normalize_leaf(neutral_type: NeutralType, value: object, _path: str) -> tuple[object, bool]:
    managed = coerce_neutral_input(value, neutral_type)
    return managed, matches_neutral_type(managed, neutral_type)


# error-neutral document-codec finding, which owns no policy text of its own. #
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


def _is_scalar_write_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return frozenset(cast("Mapping[str, object]", value)) in _MarkerKeys
