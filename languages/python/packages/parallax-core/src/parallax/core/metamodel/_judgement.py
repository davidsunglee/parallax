from __future__ import annotations

from parallax.core.base import coerce_neutral_input, matches_neutral_type
from parallax.core.metamodel._authoring_violation import AuthoringViolation
from parallax.core.metamodel._states import ValueObjectMetadata
from parallax.core.metamodel._values import AttributeMetadata, Multiplicity, PrimaryKey

__all__ = ["WriteAssignmentError", "judge_assignment"]

_UNJUDGED = object()


class WriteAssignmentError(ValueError):
    """A write assignment names an unassignable target or an ill-typed value.

    ``rule`` is the shared classification every caller reuses verbatim in its own
    error text: ``"primary-key"``, ``"read-only"``, ``"framework-owned"``, or
    ``"value-type-mismatch"``.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def judge_assignment(
    member: AttributeMetadata | ValueObjectMetadata,
    value: object,
    *,
    known_violation: AuthoringViolation | object | None = _UNJUDGED,
    known_value_valid: bool | None = None,
) -> None:
    """Judge writing ``value`` to the already-resolved ``member``, or raise.

    A scalar Attribute refuses a primary-key, read-only, or framework-owned
    target outright — three distinct designations, so the verdict says which one
    it is; otherwise ``None`` is a clearing
    assignment legal only where the member is nullable, and any other value must
    conform to the declared `m-core` neutral type after the developer input
    policy's coercion. A scalar collection and a Value Object occurrence instead
    consume the structural verdict their authoring caller supplied, after a
    collection or a non-nullable occurrence refuses ``None``.

    The message names the member relative to its own owner, so a caller that
    knows a wider position prefixes rather than re-renders.
    """
    if isinstance(member, AttributeMetadata):
        _judge_attribute(
            member, value, known_valid=known_value_valid, known_violation=known_violation
        )
        return
    _judge_value_object(member, value, known_violation=known_violation)


def _judge_attribute(
    attribute: AttributeMetadata,
    value: object,
    *,
    known_valid: bool | None,
    known_violation: AuthoringViolation | object | None,
) -> None:
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
    if attribute.multiplicity is Multiplicity.MANY:
        _consume_verdict(name, known_violation, many_scalar=True)
        return
    valid = (
        matches_neutral_type(coerce_neutral_input(value, attribute.type), attribute.type)
        if known_valid is None
        else known_valid
    )
    if not valid:
        raise WriteAssignmentError(
            "value-type-mismatch",
            f"{name}: value {value!r} does not match the declared type {attribute.type!r}",
        )


def _judge_value_object(
    occurrence: ValueObjectMetadata,
    value: object,
    *,
    known_violation: AuthoringViolation | object | None,
) -> None:
    name = occurrence.identity.path[-1]
    if value is None:
        if not occurrence.nullable:
            raise _authoring_error(name, AuthoringViolation("", "value-object-missing"))
        return
    _consume_verdict(name, known_violation, many_scalar=False)


def _consume_verdict(
    name: str, known_violation: AuthoringViolation | object | None, *, many_scalar: bool
) -> None:
    if known_violation is not None and not isinstance(known_violation, AuthoringViolation):
        raise TypeError(
            f"{name}: a structured assignment's judgement requires the document codec's "
            "authoring verdict"
        )
    if known_violation is not None:
        raise _authoring_error(name, known_violation, many_scalar=many_scalar)


def _authoring_error(
    name: str, violation: AuthoringViolation, *, many_scalar: bool = False
) -> WriteAssignmentError:
    """This module's own rule vocabulary and wording for a shared, error-neutral
    authoring violation — the codec finding owns no text of its own.

    A malformed structured assignment is, in this vocabulary, one more shape of
    "the value does not match the declared type", so every case classifies as
    ``value-type-mismatch``.
    """
    path = _joined(name, violation.path)
    if violation.reason == "not-a-list":
        expected = (
            "a `many` attribute must bind a sequence of scalar values"
            if many_scalar
            else "a `many` value object must bind a list of documents"
        )
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — {expected}",
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
