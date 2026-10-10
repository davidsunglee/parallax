"""Model-aware Object Query clause validation for the ``rejected`` case shape.

A query `rejected` case (m-case-format) carries a SCHEMA-VALID `m-object-query`
document that a model-aware resolver MUST refuse **before any SQL is emitted**.
The predicate is judged by :mod:`predicate_validate`; this module judges the
value-object rules of the query's other clauses and raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the
violated rule:

* an **Include Path** segment aimed at a value object — value objects are
  reached only by value through their owner, never navigated to
  (m-value-object contract 4, m-deep-fetch);
* a **Sort Key** or a **Subtype Selection** at the queried position rooted at a
  value object — a value object is not a queryable root entity (m-value-object
  contract 5);
* a **Sort Key** over a scalar collection, which is not one scalar value.

The reference harness (a non-normative oracle) runs this so the reference
implementation actually rejects what the `rejected` cases pin — the same refusal
each language implementation must make.
"""

from __future__ import annotations

from typing import Any

from .case import Entity
from .value_object_resolve import (
    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
    FIND_ROOT_VALUE_OBJECT,
    SCALAR_COLLECTION_UNQUANTIFIED,
    RejectionError,
    find_top_value_object,
)


def validate_object_query(entity: Entity, query: Any) -> None:
    """Reject *query*'s non-predicate clauses pre-SQL if they misuse a value
    object; else return. Used ONLY for ``rejected`` cases, so it rejects the
    specific negative inputs the corpus pins rather than validating every query.
    """
    if not isinstance(query, dict):
        return
    _check_source_guard(entity, query.get("narrowTo"))
    for key in query.get("orderBy", []) or []:
        if isinstance(key, dict):
            _check_find_root(entity, key.get("attr"))
            _check_order_key_scalar(entity, key.get("attr"))
    _check_includes(entity, query.get("includes", []) or [])


def _check_single_scalar(attribute: dict[str, Any], subject: str) -> None:
    """Refuse a scalar collection where one scalar value is required: nothing
    reaches its elements implicitly (m-predicate)."""
    if attribute.get("multiplicity", "one") == "many":
        raise RejectionError(
            SCALAR_COLLECTION_UNQUANTIFIED,
            f"{subject!r} names a scalar collection, which is not one scalar value",
        )


def _check_order_key_scalar(entity: Entity, subject: Any) -> None:
    """A Sort Key orders by one scalar value, which a scalar collection is not."""
    if not isinstance(subject, str):
        return
    try:
        attribute = entity.attribute_by_name(subject.rpartition(".")[2])
    except KeyError:
        return
    _check_single_scalar(attribute, subject)


def _check_includes(entity: Entity, paths: Any) -> None:
    for path in paths:
        if not isinstance(path, dict):
            continue
        _check_source_guard(entity, path.get("appliesTo"))
        for segment in path.get("segments", []):
            # An Include Segment is a closed object ``{rel, narrowTo?}``; the
            # value-object misuse rule is about the traversed relationship ref.
            rel = segment["rel"] if isinstance(segment, dict) else segment
            cls, _, member = rel.rpartition(".")
            if _names(entity, cls) and find_top_value_object(entity, member) is not None:
                raise RejectionError(
                    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
                    f"include segment {rel!r} names value object {member!r} — "
                    f"a value-object segment is invalid in an Include Path",
                )


def _check_source_guard(entity: Entity, selection: Any) -> None:
    """Reject a Subtype Selection at the QUERIED position aimed at a value object.

    Whole-result narrowing and an Include Path's source guard both resolve at the
    queried position, so every alternative names an Entity. The subtype-position
    rules themselves (the empty and outside-position rejections) belong to the
    inheritance walk; what belongs here is the value-object rule the queried root
    already carries — a value object has no identity, no position, and no concrete
    subtypes, so it is no more selectable than it is queryable.
    """
    if not isinstance(selection, list):
        return
    for name in selection:
        if isinstance(name, str) and find_top_value_object(entity, name) is not None:
            raise RejectionError(
                FIND_ROOT_VALUE_OBJECT,
                f"Subtype Selection names value object {name!r} on "
                f"{entity.name} — a value object is not a queryable root position and "
                f"has no concrete subtypes to select",
            )


def _names(entity: Entity, spelling: str) -> bool:
    """Whether ``spelling`` — bare or canonical — names ``entity`` itself."""
    return spelling in (entity.name, entity.canonical_name)


def _check_find_root(entity: Entity, attr: Any) -> None:
    # An `attr` is `<Entity>.<member>`, so its root is everything before the LAST
    # dot: a value-object occurrence name reaching the root position (`address.city`)
    # lands there whole, and a canonical Entity spelling does too.
    if not isinstance(attr, str):
        return
    cls = attr.rpartition(".")[0]
    if find_top_value_object(entity, cls) is not None:
        raise RejectionError(
            FIND_ROOT_VALUE_OBJECT,
            f"attribute reference {attr!r} roots the query at value object {cls!r} — "
            f"a value object is not a queryable root entity; query it through its owner",
        )
