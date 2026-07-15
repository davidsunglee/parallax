"""``parallax.core.navigate`` enforcement scope (m-navigate).

Relationship-navigation **canonicalization**: the composition-at-the-engine step
that runs after ``m-temporal-read``'s :func:`~parallax.core.temporal_read.inject_as_of`
and before ``m-sql``'s ``compile_read`` (the M2 precedent, restated for navigation).
Its single job is **per-hop as-of propagation**: for every ``navigate`` / ``exists`` /
``notExists`` hop reached anywhere in an already root-injected operation, resolve the
relationship's target entity and, when that entity (or its inheritance family) is
temporal, inject the propagated as-of predicate into the hop's own interior as
**plain** ``m-op-algebra`` predicate nodes — composed from the identical templates
``m-temporal-read`` uses at the root, matched by axis, latest-defaulted — so nothing
downstream of this module ever needs temporal knowledge.

Polymorphic **SQL emission** (the TPH tag predicate, the TPCS grouped ``OR``) is an
``m-sql`` lowering concern (COR-3 Phase 7 increment 2 already established the
pattern: ``m-sql`` legally imports ``m-inheritance`` transitively through
``m-op-algebra``); this module resolves only what **as-of propagation** needs from a
polymorphic target — the inheritance family's temporal declaration, always carried on
the family root (`m-inheritance`) — never the tag/branch shape ``m-sql`` derives
independently and directly from the same metamodel.

Per the amended dependency graph (ADR 0025 + the DQ5 core amendment), ``m-navigate``
depends on ``m-op-algebra`` (the ``navigate``/``exists``/``notExists`` nodes it walks
**are** algebra vocabulary), ``m-unit-work`` (navigation resolves through the unit of
work), ``m-temporal-read`` (a pinned as-of value propagates per hop — the reason this
module exists at all, since the DAG forbids ``m-sql`` from importing
``m-temporal-read``), and ``m-inheritance`` (a relationship target may be a
polymorphic position; its temporal declaration lives on the family root).

:func:`resolve_relationship` and :func:`hop_as_of_terms` are exported (COR-3 Phase 7
increment 5) so ``parallax.core.deep_fetch`` — the sole downstream ``m-navigate``
dependent per the DQ5 amendment — resolves each deep-fetch path segment's
relationship and composes each per-level child query's own propagated as-of
predicate through the SAME primitives this module's own hop canonicalization uses,
rather than re-deriving temporal/relationship knowledge the DAG already lets it reach
only through this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from parallax.core import inheritance
from parallax.core.base import INFINITY_LITERAL
from parallax.core.descriptor import Axis, Entity, Metamodel, Relationship
from parallax.core.op_algebra import (
    And,
    AsOf,
    AsOfRange,
    Comparison,
    DeepFetch,
    Distinct,
    Exists,
    Group,
    History,
    Limit,
    Narrow,
    Navigate,
    Not,
    NotExists,
    Operation,
    Or,
    OrderBy,
)
from parallax.core.temporal_read import AXIS_ORDER, attr_ref_for_column, conjunction_terms

__all__ = ["canonicalize", "hop_as_of_terms", "resolve_relationship"]

_EMPTY_PINS: Mapping[Axis, str] = MappingProxyType({})


def canonicalize(
    op: Operation,
    meta: Metamodel,
    root_pins: Mapping[Axis, str] = _EMPTY_PINS,
) -> Operation:
    """Rewrite every navigation hop in ``op`` to carry its own per-hop as-of term.

    ``op`` is the operation **after** the root's own `inject_as_of` has already run
    (the engine/handle composition order: `inject_as_of` then `canonicalize` then
    `compile_read`). ``root_pins`` is the root read's resolved per-axis instant —
    :func:`~parallax.core.temporal_read.resolve_pinned_instants` computed from the
    SAME raw operation `inject_as_of` consumed — mapping an axis to the specific past
    instant the root pinned; an axis absent from the map (undeclared by the root,
    pinned/defaulted to latest, or scanned) independently defaults to **latest** at
    every temporal hop target it reaches, never re-derived from ``op`` itself.

    Returns ``op`` unchanged (strict identity) when it contains no
    ``navigate`` / ``exists`` / ``notExists`` node anywhere — the common case for a
    read with no relationship traversal, mirroring `inject_as_of`'s own identity rule
    for a non-temporal target.
    """
    if not _contains_navigation(op):
        return op
    return _walk(op, meta, root_pins)


# --------------------------------------------------------------------------- #
# Fast pre-check (identity for navigation-free operations).                   #
# --------------------------------------------------------------------------- #
def _contains_navigation(op: Operation) -> bool:
    match op:
        case Navigate() | Exists() | NotExists():
            return True
        case And(operands=operands) | Or(operands=operands):
            return any(_contains_navigation(operand) for operand in operands)
        case (
            Not(operand=operand)
            | Group(operand=operand)
            | Narrow(operand=operand)
            | OrderBy(operand=operand)
            | Limit(operand=operand)
            | Distinct(operand=operand)
            | AsOf(operand=operand)
            | AsOfRange(operand=operand)
            | History(operand=operand)
        ):
            return _contains_navigation(operand)
        case DeepFetch(operand=operand):
            # A deep-fetch level's own operations are built later (`m-deep-fetch`,
            # increment 5); only its root `operand` predicate is walked here.
            return _contains_navigation(operand)
        case _:
            # Every remaining leaf (All/NoneOp/Comparison/Between/NullCheck/
            # StringMatch/Membership/NestedComparison/NestedMembership/
            # NestedNullCheck/NestedExists/NestedNotExists) carries no navigation.
            return False


# --------------------------------------------------------------------------- #
# The rewrite walk (only run once navigation is known to exist somewhere).    #
# --------------------------------------------------------------------------- #
def _walk(op: Operation, meta: Metamodel, root_pins: Mapping[Axis, str]) -> Operation:
    match op:
        case Navigate(rel=rel, op=inner):
            return Navigate(rel=rel, op=_hop_inner(rel, inner, meta, root_pins))
        case Exists(rel=rel, op=inner):
            return Exists(rel=rel, op=_hop_inner(rel, inner, meta, root_pins))
        case NotExists(rel=rel, op=inner):
            return NotExists(rel=rel, op=_hop_inner(rel, inner, meta, root_pins))
        case And(operands=operands):
            return And(operands=tuple(_walk(operand, meta, root_pins) for operand in operands))
        case Or(operands=operands):
            return Or(operands=tuple(_walk(operand, meta, root_pins) for operand in operands))
        case Not(operand=operand):
            return Not(operand=_walk(operand, meta, root_pins))
        case Group(operand=operand):
            return Group(operand=_walk(operand, meta, root_pins))
        case Narrow(entity=entity, to=to, operand=operand):
            return Narrow(entity=entity, to=to, operand=_walk(operand, meta, root_pins))
        case OrderBy(operand=operand, keys=keys):
            return OrderBy(operand=_walk(operand, meta, root_pins), keys=keys)
        case Limit(operand=operand, count=count):
            return Limit(operand=_walk(operand, meta, root_pins), count=count)
        case Distinct(operand=operand):
            return Distinct(operand=_walk(operand, meta, root_pins))
        case AsOf(operand=operand, as_of_attr=as_of_attr, date=date):
            return AsOf(operand=_walk(operand, meta, root_pins), as_of_attr=as_of_attr, date=date)
        case AsOfRange(operand=operand, as_of_attr=as_of_attr, from_=from_, to=to):
            return AsOfRange(
                operand=_walk(operand, meta, root_pins), as_of_attr=as_of_attr, from_=from_, to=to
            )
        case History(operand=operand, as_of_attr=as_of_attr):
            return History(operand=_walk(operand, meta, root_pins), as_of_attr=as_of_attr)
        case DeepFetch(operand=operand, paths=paths):
            return DeepFetch(operand=_walk(operand, meta, root_pins), paths=paths)
        case _:
            # Every remaining node (All/NoneOp/Comparison/Between/NullCheck/
            # StringMatch/Membership/NestedComparison/NestedMembership/
            # NestedNullCheck/NestedExists/NestedNotExists) carries no navigation.
            return op


def _hop_inner(
    rel: str, inner: Operation | None, meta: Metamodel, root_pins: Mapping[Axis, str]
) -> Operation | None:
    """The hop's rewritten interior: its own navigation walked, then its own
    per-hop as-of term (if temporal) appended after (m-navigate As-of propagation)."""
    relationship = resolve_relationship(rel, meta)
    target_entity = meta.entity(relationship.related_entity)
    walked = _walk(inner, meta, root_pins) if inner is not None else None
    return _inject_hop_as_of(walked, target_entity, meta, root_pins)


def resolve_relationship(rel_ref: str, meta: Metamodel) -> Relationship:
    """Resolve a ``Class.relationship`` reference to its declared :class:`Relationship`.

    Exported so `parallax.core.deep_fetch` (the sole downstream `m-navigate`
    dependent, per the DQ5 core amendment) resolves each deep-fetch path
    segment's relationship through the SAME lookup this module's own hop
    canonicalization uses, rather than re-deriving it.
    """
    class_name, _, member_name = rel_ref.partition(".")
    entity = meta.entity(class_name)
    for relationship in entity.relationships:
        if relationship.name == member_name:
            return relationship
    # Unreachable for a validated operation (`m-op-algebra`'s `validate_operation`
    # already resolves every `rel` reference before a read reaches canonicalization).
    raise ValueError(  # pragma: no cover - guards a malformed / unvalidated operation
        f"{rel_ref!r} names no declared relationship on {entity.name}"
    )


def _temporal_declarer(meta: Metamodel, entity: Entity) -> Entity:
    """The entity that actually DECLARES ``entity``'s as-of axes.

    A plain entity declares its own; an inheritance participant's temporal axes are
    declared on the family ROOT and inherited by every concrete subtype
    (`m-inheritance`), so a relationship target that names an abstract position (or
    even a concrete leaf) must resolve to the root to find them.
    """
    if entity.inheritance is None:
        return entity
    return inheritance.family_root(meta, entity)


def hop_as_of_terms(
    target_entity: Entity, meta: Metamodel, root_pins: Mapping[Axis, str]
) -> tuple[Operation, ...]:
    """The per-axis as-of term(s) for a hop's ``target_entity`` (m-navigate
    "As-of propagation"): empty for a non-temporal target; one term per its own
    declared axis (two for a bounded past instant), business-axis-first — the
    root's pinned instant for that axis (``root_pins``) when the root itself
    pinned a specific past moment, else **latest**.

    Exported (alongside :func:`resolve_relationship`) so `parallax.core.deep_fetch`
    composes the IDENTICAL per-hop as-of predicate for each deep-fetch child
    level, matched by axis exactly as a `navigate` / `exists` / `notExists` hop's
    own interior is rewritten by :func:`_inject_hop_as_of` below (which now
    builds on this same term derivation).
    """
    declarer = _temporal_declarer(meta, target_entity)
    if not declarer.as_of_attributes:
        return ()
    terms: list[Operation] = []
    for aoa in sorted(declarer.as_of_attributes, key=lambda attribute: AXIS_ORDER[attribute.axis]):
        from_ref = attr_ref_for_column(declarer, aoa.from_column)
        to_ref = attr_ref_for_column(declarer, aoa.to_column)
        instant = root_pins.get(aoa.axis)
        if instant is None:
            terms.append(Comparison(op="eq", attr=to_ref, value=INFINITY_LITERAL))
        else:
            upper_op = "greaterThanEquals" if aoa.to_is_inclusive else "greaterThan"
            terms.append(Comparison(op="lessThanEquals", attr=from_ref, value=instant))
            terms.append(Comparison(op=upper_op, attr=to_ref, value=instant))
    return tuple(terms)


def _inject_hop_as_of(
    inner: Operation | None,
    target_entity: Entity,
    meta: Metamodel,
    root_pins: Mapping[Axis, str],
) -> Operation | None:
    """Append ``target_entity``'s own per-axis as-of term(s) after ``inner``.

    A **non-temporal** target carries no as-of term at all (returns ``inner``
    unchanged — a strict identity, mirroring `inject_as_of`'s own non-temporal
    identity). A **temporal** target gets one term per its own declared axis,
    business-axis-first: the root's pinned instant for that axis (``root_pins``) if
    the root itself pinned a specific past moment, else **latest** — covering both
    "an axis unpinned at the root defaults to latest" and "a temporal entity reached
    from a non-temporal one defaults every axis to latest" in one rule, since a
    non-temporal (or axis-undeclared) root simply never populates ``root_pins`` for
    that axis.
    """
    terms = hop_as_of_terms(target_entity, meta, root_pins)
    if not terms:
        return inner
    if inner is None:
        conjuncts: tuple[Operation, ...] = terms
    else:
        conjuncts = (*conjunction_terms(inner), *terms)
    return conjuncts[0] if len(conjuncts) == 1 else And(operands=conjuncts)
