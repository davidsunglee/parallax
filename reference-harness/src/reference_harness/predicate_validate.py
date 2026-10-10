"""Model-aware predicate validation for the ``rejected`` case shape.

A rejected predicate (`m-case-format` Rejected cases) is schema-valid but
violates an `m-predicate` rule a model-aware resolver MUST apply before any SQL.
This walk judges every node in tree order at the scope it is written in, each
operation subject first: its path and scope, then the operator's applicability
to the member reached, then each typed literal, then a range's bound order.
Quantifiers bind the scope their ``where`` is judged in, and a ``narrow``
narrows the position its operand is judged at. The first violation raises the
:class:`~reference_harness.value_object_resolve.RejectionError` naming its rule.
"""

from __future__ import annotations

from typing import Any

from .inheritance import (
    NARROW_OUTSIDE_RELATIONSHIP_TARGET,
    Family,
    resolve_clamped_narrow,
)
from .predicate_paths import (
    ElementScope,
    EntityScope,
    FieldTerminal,
    RelationshipTerminal,
    ScalarScope,
    Scope,
    ValueObjectTerminal,
    resolve_path,
)
from .value_object_resolve import (
    BETWEEN_BOUNDS_INVERTED,
    NULL_CHECK_NON_NULLABLE_MEMBER,
    PATH_TARGET_KIND_MISMATCH,
    PREDICATE_SUBJECT_OUTSIDE_SCOPE,
    SCALAR_COLLECTION_UNQUANTIFIED,
    STRING_PREDICATE_NON_STRING_MEMBER,
    RejectionError,
    bounds_inverted,
    decode_typed_literal,
    is_string_member,
)

__all__ = ["SCALAR_OPERATION_TAGS", "validate_predicate", "validate_query_predicate"]

_COMPARISON_TAGS = frozenset(
    {"eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"}
)
_STRING_TAGS = frozenset({"like", "notLike", "startsWith", "endsWith", "contains"})
_NULL_TAGS = frozenset({"isNull", "isNotNull"})
SCALAR_OPERATION_TAGS = (
    _COMPARISON_TAGS | _STRING_TAGS | _NULL_TAGS | frozenset({"between", "in", "notIn"})
)


def validate_predicate(family: Family, scope: Scope, node: Any) -> None:
    """Reject ``node`` pre-SQL at ``scope`` if it violates a predicate rule."""
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return
    if tag in SCALAR_OPERATION_TAGS:
        _operation(family, scope, tag, body)
    elif tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            validate_predicate(family, scope, operand)
    elif tag in ("not", "group"):
        validate_predicate(family, scope, body.get("operand"))
    elif tag in ("any", "all", "none"):
        _quantifier(family, scope, body)
    elif tag in ("exists", "notExists"):
        _presence(family, scope, body["path"])
    elif tag == "narrow":
        _narrow(family, scope, body)


def _presence(family: Family, scope: Scope, path: str) -> None:
    terminal = resolve_path(family, scope, path)
    single = (
        isinstance(terminal, ValueObjectTerminal)
        and terminal.value_object.get("multiplicity", "one") != "many"
    ) or (isinstance(terminal, RelationshipTerminal) and not terminal.many)
    if not single:
        raise RejectionError(
            PATH_TARGET_KIND_MISMATCH,
            f"{path!r} names {terminal.kind}, which has no presence of its own",
        )


def _subject(
    family: Family, scope: Scope, tag: str, path: str | None
) -> tuple[dict[str, Any], str]:
    """The declared member an operation reads and how a diagnostic names it."""
    if path is None:
        if not isinstance(scope, ScalarScope):
            raise RejectionError(
                PREDICATE_SUBJECT_OUTSIDE_SCOPE,
                f"{tag} reads the element a scalar-collection quantifier binds, and none "
                "encloses it",
            )
        return scope.attribute, f"{scope.attribute.get('name')} element"
    terminal = resolve_path(family, scope, path)
    if not isinstance(terminal, FieldTerminal):
        raise RejectionError(
            PATH_TARGET_KIND_MISMATCH, f"{path!r} ends on {terminal.kind}, not a field"
        )
    return terminal.attribute, path


def _operation(family: Family, scope: Scope, tag: str, body: dict[str, Any]) -> None:
    path = body.get("path")
    attribute, subject = _subject(family, scope, tag, path)
    if path is not None:
        if tag in _NULL_TAGS:
            if not attribute.get("nullable", False):
                raise RejectionError(
                    NULL_CHECK_NON_NULLABLE_MEMBER,
                    f"{path!r}: isNull/isNotNull is invalid for a non-nullable member",
                )
            return
        if attribute.get("multiplicity", "one") == "many":
            raise RejectionError(
                SCALAR_COLLECTION_UNQUANTIFIED,
                f"{path!r} names a scalar collection, which is not one scalar value",
            )
    _literals(tag, body, attribute.get("type"), subject)


def _literals(tag: str, body: dict[str, Any], declared: Any, subject: str) -> None:
    if tag in _STRING_TAGS:
        if not is_string_member(declared):
            raise RejectionError(
                STRING_PREDICATE_NON_STRING_MEMBER,
                f"{subject!r}: a string predicate reads text, but the declared type is "
                f"{declared!r}",
            )
        decode_typed_literal(body.get("value"), declared, repr(subject))
    elif tag == "between":
        lower = decode_typed_literal(body.get("lower"), declared, f"{subject!r} lower bound")
        upper = decode_typed_literal(body.get("upper"), declared, f"{subject!r} upper bound")
        if bounds_inverted(lower, upper):
            raise RejectionError(
                BETWEEN_BOUNDS_INVERTED,
                f"{subject!r}: lower bound {lower!r} is greater than upper bound {upper!r}",
            )
    elif tag in ("in", "notIn"):
        for value in body.get("values", []) or []:
            decode_typed_literal(value, declared, repr(subject))
    else:
        decode_typed_literal(body.get("value"), declared, repr(subject))


def _quantifier(family: Family, scope: Scope, body: dict[str, Any]) -> None:
    path = body["path"]
    terminal = resolve_path(family, scope, path)
    inner: Scope
    if isinstance(terminal, FieldTerminal) and terminal.attribute.get("multiplicity") == "many":
        inner = ScalarScope(terminal.attribute)
    elif (
        isinstance(terminal, ValueObjectTerminal)
        and terminal.value_object.get("multiplicity") == "many"
    ):
        inner = ElementScope(terminal.value_object)
    elif isinstance(terminal, RelationshipTerminal) and terminal.many:
        inner = EntityScope(
            terminal.target,
            tuple(family.effective_concrete_set(terminal.target)),
            bound=True,
            outside_rule=NARROW_OUTSIDE_RELATIONSHIP_TARGET,
        )
    else:
        raise RejectionError(
            PATH_TARGET_KIND_MISMATCH,
            f"{path!r} names {terminal.kind}, which a quantifier does not range over",
        )
    if "where" in body:
        validate_predicate(family, inner, body["where"])


def _narrow(family: Family, scope: Scope, body: dict[str, Any]) -> None:
    path = body.get("path")
    to = body.get("to", []) or []
    if path is None:
        if not isinstance(scope, EntityScope):
            raise RejectionError(
                PREDICATE_SUBJECT_OUTSIDE_SCOPE,
                "narrow addresses an Entity position, not a bound element",
            )
        narrowed = resolve_clamped_narrow(family, list(scope.position), to, scope.outside_rule)
        inner = EntityScope(scope.key, tuple(narrowed), scope.bound, scope.outside_rule)
    else:
        terminal = resolve_path(family, scope, path)
        if not isinstance(terminal, RelationshipTerminal) or terminal.many:
            raise RejectionError(
                PATH_TARGET_KIND_MISMATCH,
                f"{path!r} names {terminal.kind}; a path-targeted narrow reaches a single "
                "related Entity",
            )
        narrowed = resolve_clamped_narrow(
            family,
            family.effective_concrete_set(terminal.target),
            to,
            NARROW_OUTSIDE_RELATIONSHIP_TARGET,
        )
        inner = EntityScope(
            terminal.target, tuple(narrowed), True, NARROW_OUTSIDE_RELATIONSHIP_TARGET
        )
    validate_predicate(family, inner, body.get("operand"))


def validate_query_predicate(entity_defs: list[dict[str, Any]], query: Any) -> None:
    """Reject an Object Query's predicate pre-SQL, judged at the queried
    position its result narrowing leaves."""
    if not isinstance(query, dict):
        return
    family = Family(entity_defs)
    target = query.get("target")
    if not isinstance(target, str) or target not in family.defs:
        return
    key = family.defs.canonical_key(target)
    position = family.effective_concrete_set(key)
    narrow_to = query.get("narrowTo")
    if isinstance(narrow_to, list):
        position = resolve_clamped_narrow(family, position, narrow_to)
    validate_predicate(
        family, EntityScope(key, tuple(position), bound=False), query.get("predicate")
    )
