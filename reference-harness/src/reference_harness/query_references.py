"""Shared Predicate-tag vocabularies and the reference-class walker.

Several validators ask the SAME question of a predicate — which queried-entity
classes do its Entity-qualified paths name? — so both the tag sets and the
single walk that consumes them live here rather than being copied into each
caller.

Two callers share the walk: the Object Query self-consistency cross-check
(``schema_validate``) and the predicate-write scope check
(``predicate_write_validate``). They differ only in what surrounds the predicate:
a read carries it as one clause of a query whose other clauses name classes of
their own, whereas a predicate write is the bare predicate alone.
"""

from __future__ import annotations

from typing import Any

from .references import entity_spelling

SCALAR_OPERATION_TAGS = frozenset(
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

# Every tag whose body may carry a predicate `path`: the scalar operations, the
# quantifiers, the presence tests, and a path-targeted narrowing. An
# Entity-qualified path names the queried class as its entity spelling; a
# relative path, read from a bound object, names none.
PATH_TAGS = SCALAR_OPERATION_TAGS | frozenset(
    {"any", "all", "none", "exists", "notExists", "narrow"}
)


def _add_path_reference_class(reference: Any, classes: set[str]) -> None:
    """Add the class an Entity-qualified ``path`` names (everything up to its
    LAST capitalized segment, :func:`~reference_harness.references.split_reference`);
    a relative path names no class and contributes nothing."""
    named = entity_spelling(reference)
    if named is not None:
        classes.add(named)


def _add_member_reference_class(reference: Any, classes: set[str]) -> None:
    """Add the class part of a ``Class.member`` reference (a Sort Key's ``attr``
    or an Include segment's ``rel``): the spelling up to its LAST dot."""
    if isinstance(reference, str) and "." in reference:
        classes.add(reference.rsplit(".", 1)[0])


def collect_reference_classes(node: Any, classes: set[str]) -> None:
    """Collect the class every queried-position path in *node* names.

    Descends the boolean combinators and a narrowing of the current position. A
    quantifier's ``where`` and a path-targeted narrowing's operand are read from
    a bound object, whose relative paths name no queried class, so they are not
    descended: the path a quantifier or narrowing itself carries is the evidence.
    """
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return
    if tag in PATH_TAGS:
        _add_path_reference_class(body.get("path"), classes)
    if tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            collect_reference_classes(operand, classes)
    elif tag in ("not", "group") or (tag == "narrow" and "path" not in body):
        # A narrowing of the current position evaluates its operand there, so
        # the operand's paths are still cross-checked against the target; the
        # narrowing's own subset validity is asserted separately (m-inheritance).
        collect_reference_classes(body.get("operand"), classes)
    # the constants name no class.


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
