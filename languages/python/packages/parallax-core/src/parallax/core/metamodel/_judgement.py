"""One resolved member's verdict on one written value (m-metamodel).

Assignment validation has two halves that need different things. Deciding WHICH
member a name resolves to is a family-effective question about a whole model;
deciding whether a value may be written to an ALREADY RESOLVED member reads that
member's own accepted metadata and the value, and nothing else. This module owns
the second half, so a caller holding a member — the descriptor that installed it,
or a facet walk that just found it — states the rule without reaching a model.

That is what keeps ONE VALIDATOR true across the split. Three surfaces judge
here — the typed ``.set(...)`` path, ``Entity.model_copy(update=...)``, and the
serialized write-instruction path — and only the resolution in front of them
differs: an expression already holds its member, a Python name is resolved
class-shaped, and a canonical ``Class.member`` reference is resolved
family-effectively against a model.
"""

from __future__ import annotations

from parallax.core.base import coerce_neutral_input, matches_neutral_type
from parallax.core.metamodel._states import ValueObjectMetadata
from parallax.core.metamodel._values import AttributeMetadata, PrimaryKey
from parallax.core.metamodel._vo_document import VoDocumentViolation, vo_document_violation

__all__ = ["WriteAssignmentError", "judge_assignment"]


class WriteAssignmentError(ValueError):
    """A write assignment names an unassignable target or an ill-typed value.

    ``rule`` is the shared classification every caller reuses verbatim in its own
    error text: ``"primary-key"``, ``"read-only"``, ``"framework-owned"``, or
    ``"value-type-mismatch"``.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def judge_assignment(member: AttributeMetadata | ValueObjectMetadata, value: object) -> None:
    """Judge writing ``value`` to the already-resolved ``member``, or raise.

    A scalar Attribute refuses a primary-key, read-only, or framework-owned
    target outright — three distinct designations, so the verdict says which one
    it is; otherwise ``None`` is a clearing
    assignment legal only where the member is nullable, and any other value must
    conform to the declared `m-core` neutral type after the developer input
    policy's coercion. A Value Object occurrence refuses ``None`` unless nullable
    and otherwise requires a well-formed document against its declared composite.

    The message names the member relative to its own owner, so a caller that
    knows a wider position prefixes rather than re-renders.
    """
    if isinstance(member, AttributeMetadata):
        _judge_attribute(member, value)
        return
    _judge_value_object(member, value)


def _judge_attribute(attribute: AttributeMetadata, value: object) -> None:
    name = attribute.identity.name
    if isinstance(attribute.primary_key, PrimaryKey):
        raise WriteAssignmentError("primary-key", f"{name}: primary-key fields may not be assigned")
    if attribute.read_only:
        raise WriteAssignmentError("read-only", f"{name}: read-only fields may not be assigned")
    if attribute.framework_owned:
        raise WriteAssignmentError(
            "framework-owned", f"{name}: framework-owned fields may not be assigned"
        )
    if value is None:
        if not attribute.nullable:
            raise WriteAssignmentError(
                "value-type-mismatch", f"{name}: required attribute is absent (or null)"
            )
        return
    if not matches_neutral_type(coerce_neutral_input(value, attribute.type), attribute.type):
        raise WriteAssignmentError(
            "value-type-mismatch",
            f"{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


def _judge_value_object(occurrence: ValueObjectMetadata, value: object) -> None:
    name = occurrence.identity.path[-1]
    if value is None:
        if not occurrence.nullable:
            raise _vo_error(name, VoDocumentViolation("", "value-object-missing"))
        return
    violation = vo_document_violation(occurrence, value)
    if violation is not None:
        raise _vo_error(name, violation)


def _vo_error(name: str, violation: VoDocumentViolation) -> WriteAssignmentError:
    """This module's own rule vocabulary and wording for a shared, error-neutral
    Value Object document violation — ``_vo_document`` owns no text of its own.

    A malformed value-object assignment is, in this vocabulary, one more shape of
    "the value does not match the declared type", so every case classifies as
    ``value-type-mismatch``.
    """
    path = _joined(name, violation.path)
    if violation.reason == "not-a-list":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — a `many` "
            "value object must bind a list of documents",
        )
    if violation.reason == "not-a-document":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — expected a "
            "document (mapping)",
        )
    if violation.reason == "attribute-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required attribute is absent (or null)"
        )
    if violation.reason == "value-object-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required value object is absent (or null)"
        )
    return WriteAssignmentError(
        "value-type-mismatch",
        f"{path}: value {violation.value!r} does not match the declared type "
        f"{violation.declared_type!r}",
    )


def _joined(base: str, path: str) -> str:
    """``base`` plus a walk's own relative ``path`` — a nested member dot-joins,
    a ``many`` element index attaches bracket-first with no separating dot."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"
