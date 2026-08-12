"""Shared Predicate-tag vocabularies and the reference-class walker.

The Predicate schema distinguishes scalar attribute references from value-object
paths. Several validators ask the SAME question of a predicate — which
queried-entity classes does it name? — so both the tag sets and the single walk
that consumes them live here rather than being copied into each caller.

Two callers share the walk: the Object Query self-consistency cross-check
(``schema_validate``) and the predicate-write scope check
(``predicate_write_validate``). They differ only in what surrounds the predicate:
a read carries it as one clause of a query whose other clauses name classes of
their own, whereas a predicate write is the bare predicate alone.
"""

from __future__ import annotations

from typing import Any

from .references import entity_spelling

ATTRIBUTE_REFERENCE_TAGS = frozenset(
    {
        "eq",
        "notEq",
        "greaterThan",
        "greaterThanEquals",
        "lessThan",
        "lessThanEquals",
        "between",
        "isNull",
        "isNotNull",
        "like",
        "notLike",
        "startsWith",
        "endsWith",
        "contains",
        "in",
        "notIn",
    }
)

# Every path-bearing tag exposes the queried class as the FIRST segment of
# ``body["path"]``, which is why one extraction serves the whole set. The flat
# nested comparisons / ranges / memberships / string predicates / null-checks carry a
# ``Class.valueObject.attr``
# path; ``nestedExists`` / ``nestedNotExists`` carry a ``Class.valueObject`` path
# plus an OPTIONAL element-scoped ``where``. That ``where`` uses element-relative
# refs (no leading class), so it names no queried class and is intentionally NOT
# descended for scope — the class always comes from the required ``path``. This is
# why a path's class is extracted differently from an ``attr`` / ``rel`` class,
# whose member name is a single trailing segment.
PATH_REFERENCE_TAGS = frozenset(
    {
        "nestedEq",
        "nestedNotEq",
        "nestedGt",
        "nestedGte",
        "nestedLt",
        "nestedLte",
        "nestedBetween",
        "nestedIn",
        "nestedNotIn",
        "nestedLike",
        "nestedNotLike",
        "nestedStartsWith",
        "nestedEndsWith",
        "nestedContains",
        "nestedIsNull",
        "nestedIsNotNull",
        "nestedExists",
        "nestedNotExists",
    }
)


def _add_member_reference_class(reference: Any, classes: set[str]) -> None:
    """Add the class part of a ``Class.member`` reference (an ``attr`` or a ``rel``).

    The class is the spelling up to the LAST dot, so a canonically spelled position
    (``<namespace>.<Entity>.<member>``) contributes the entity it names rather than
    its leading namespace segment.
    """
    if isinstance(reference, str) and "." in reference:
        classes.add(reference.rsplit(".", 1)[0])


def _add_path_reference_class(reference: Any, classes: set[str]) -> None:
    """Add the class part of a value-object ``path`` (``Class.valueObject[.…]``).

    A path's trailing segments are declared value-object members rather than one
    member name, so the class is everything up to the LAST capitalized segment
    (:func:`~reference_harness.references.split_reference`) rather than up to the
    last dot. An element-relative path names no class and contributes nothing.
    """
    named = entity_spelling(reference)
    if named is not None:
        classes.add(named)


def collect_reference_classes(node: Any, classes: set[str]) -> None:
    """Collect the class part of every queried-entity reference in *node*.

    Descends the same-entity boolean combinators (``and`` / ``or`` / ``not`` /
    ``group``) and the Predicate-scoped ``narrow``, and adds the class named by an
    attribute (``attr``), a value-object path (``path``), or a relationship
    (``rel``). A navigation's INNER predicate and a ``nestedExists`` ``where``
    resolve against a DIFFERENT scope (the related entity / the array element), so
    they are NOT descended: the reference they contain is not evidence that this
    predicate's root entity differs from the target.
    """
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return
    if tag in ATTRIBUTE_REFERENCE_TAGS:
        _add_member_reference_class(body.get("attr"), classes)
    elif tag in PATH_REFERENCE_TAGS:
        _add_path_reference_class(body.get("path"), classes)
    elif tag in ("navigate", "exists", "notExists"):
        _add_member_reference_class(body.get("rel"), classes)
    elif tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            collect_reference_classes(operand, classes)
    elif tag in ("not", "group", "narrow"):
        # A narrow evaluates its operand over the polymorphic position supplied by
        # context, so the operand's queried-entity references are still
        # cross-checked against the target; the narrow's own subset validity is
        # asserted separately (m-inheritance).
        collect_reference_classes(body.get("operand"), classes)
    # all / none name no class.


def collect_query_reference_classes(query: Any, classes: set[str]) -> None:
    """Collect every queried-entity reference class one Object Query names.

    The predicate contributes through :func:`collect_reference_classes`; the
    ordering clause contributes each Sort Key's attribute, and each Include Path
    its FIRST hop's relationship, which is the only segment written against the
    queried position. A Subtype Selection contributes no queried-member class —
    its validity is a position judgement rather than a reference one.
    """
    if not isinstance(query, dict):
        return
    collect_reference_classes(query.get("predicate"), classes)
    for key in query.get("orderBy", []) or []:
        if isinstance(key, dict):
            _add_member_reference_class(key.get("attr"), classes)
    for path in query.get("includes", []) or []:
        segments = path.get("segments") if isinstance(path, dict) else None
        if segments:
            segment = segments[0]
            rel = segment.get("rel") if isinstance(segment, dict) else segment
            _add_member_reference_class(rel, classes)
