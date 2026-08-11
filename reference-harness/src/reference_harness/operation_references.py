"""Shared operation-tag vocabularies and the reference-class walker.

The operation schema distinguishes scalar attribute references from value-object
paths. Several validators ask the SAME question of an operation node — which
queried-entity classes does it name? — so both the tag sets and the single walk
that consumes them live here rather than being copied into each caller.

Two callers share the walk: the read ``targetEntity`` cross-check
(``schema_validate``) and the predicate-write scope check
(``predicate_write_validate``). They differ only in what surrounds the predicate:
a read wraps it in result / temporal directives (``orderBy``, ``deepFetch``, …),
whereas a predicate write is a BARE predicate that carries none of them.

A vocabulary also lives here when its consumers ask DIFFERENT questions of the
same closed set — :data:`OPERAND_ROW_WRAPPER_TAGS` is shared by walks that do not
otherwise resemble each other — so that one ``m-op-algebra`` set has one owner
whatever it is being asked.
"""

from __future__ import annotations

from typing import Any

from .references import entity_spelling

# The closed set `m-op-algebra` names as the wrappers "returning their operand's
# OWN rows": the result-shaping directives (``orderBy`` / ``limit`` /
# ``deepFetch``, which attaches fetched levels to those rows rather than
# replacing them) and the temporal wrappers (``asOf`` / ``asOfRange`` /
# ``history``). None of them re-roots the rows its operand yields, so a walk
# looking for the node that fixed those rows descends through this set AND NO
# OTHER NODE. Deliberately purpose-neutral: what a walk does when it stops is its
# own — resolving the position an order key is measured at, or the narrow an
# abstract read's projection superset follows — and only the vocabulary is shared.
OPERAND_ROW_WRAPPER_TAGS = frozenset(
    {
        "orderBy",
        "limit",
        "deepFetch",
        "asOf",
        "asOfRange",
        "history",
    }
)

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


def collect_reference_classes(
    node: Any, classes: set[str], *, descend_result_modifiers: bool
) -> None:
    """Collect the class part of every queried-entity reference in *node*.

    Descends the same-entity boolean combinators (``and`` / ``or`` / ``not`` /
    ``group``) and adds the class named by an attribute (``attr``), a value-object
    path (``path``), or a relationship (``rel``). A navigation's INNER operation
    and a ``nestedExists`` ``where`` resolve against a DIFFERENT scope (the related
    entity / the array element), so they are NOT descended: the reference they
    contain is not evidence that this node's root entity differs from the target.

    Read operations additionally wrap the predicate in result and temporal
    directives (``orderBy``, ``limit``, ``deepFetch``, ``narrow``, ``asOf`` …).
    A predicate write is a BARE predicate that carries none of these,
    so its caller passes ``descend_result_modifiers=False`` to walk only the
    predicate core.
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
            collect_reference_classes(
                operand, classes, descend_result_modifiers=descend_result_modifiers
            )
    elif tag in ("not", "group"):
        collect_reference_classes(
            body.get("operand"), classes, descend_result_modifiers=descend_result_modifiers
        )
    elif descend_result_modifiers:
        _collect_result_modifier_classes(tag, body, classes)
    # all / none (and, for a bare predicate, any result modifier) name no class.


def _collect_result_modifier_classes(tag: str, body: dict[str, Any], classes: set[str]) -> None:
    """Collect classes from a read-only result / temporal directive around the predicate."""
    if tag == "deepFetch":
        collect_reference_classes(body.get("operand"), classes, descend_result_modifiers=True)
        for path in body.get("paths", []) or []:
            segments = path.get("segments") if isinstance(path, dict) else None
            if segments:
                segment = segments[0]
                rel = segment.get("rel") if isinstance(segment, dict) else segment
                _add_member_reference_class(rel, classes)
            # A path-root Subtype Selection contributes no queried-member class;
            # its validity is asserted by the position walk instead.
    elif tag in ("asOf", "asOfRange", "history", "limit", "narrow"):
        # A narrow evaluates its operand over the polymorphic position supplied by
        # context, so the
        # operand's queried-entity references are still cross-checked against the
        # target; the narrow's subset validity is asserted separately (op-algebra).
        collect_reference_classes(body.get("operand"), classes, descend_result_modifiers=True)
    elif tag == "orderBy":
        collect_reference_classes(body.get("operand"), classes, descend_result_modifiers=True)
        for key in body.get("keys", []) or []:
            if isinstance(key, dict):
                _add_member_reference_class(key.get("attr"), classes)
