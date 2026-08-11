"""``parallax.core.navigate`` enforcement scope (m-navigate).

Relationship-navigation **canonicalization** over the flat predicate produced at
the read-planning boundary.
Its single job is **per-hop as-of propagation**: for every ``navigate`` / ``exists`` /
``notExists`` hop reached anywhere in an already root-injected operation, resolve the
relationship's target entity and, when that entity (or its inheritance family) is
temporal, inject the propagated as-of predicate into the hop's own interior as
**plain** ``m-predicate`` predicate nodes — composed from the identical templates
``m-temporal-read`` uses at the root, matched by axis, latest-defaulted — so nothing
downstream of this module ever needs temporal knowledge.

Polymorphic **SQL emission** (the TPH tag predicate, the TPCS grouped ``OR``) is an
``m-sql`` lowering concern (``m-sql`` legally imports ``m-inheritance``
transitively through ``m-predicate``); this module resolves only what
**as-of propagation** needs from a
polymorphic target — the inheritance family's temporal declaration, always carried on
the family root (`m-inheritance`) — never the tag/branch shape ``m-sql`` derives
independently and directly from the same metamodel.

Per the dependency graph, ``m-navigate``
depends on ``m-predicate`` (the ``navigate``/``exists``/``notExists`` nodes it walks
**are** algebra vocabulary), ``m-unit-work`` (navigation resolves through the unit of
work), ``m-temporal-read`` (a pinned as-of value propagates per hop — the reason this
module exists at all, since the DAG forbids ``m-sql`` from importing
``m-temporal-read``), and ``m-inheritance`` (a relationship target may be a
polymorphic position; its temporal declaration lives on the family root).

:func:`resolve_relationship` and :func:`hop_as_of_terms` are exported so
``parallax.core.deep_fetch`` — the sole downstream ``m-navigate``
dependent — resolves each deep-fetch path segment's
relationship and composes each per-level child query's own propagated as-of
predicate through the SAME primitives this module's own hop canonicalization uses,
rather than re-deriving temporal/relationship knowledge the DAG already lets it reach
only through this module.

A hop resolves to the navigable **direction** the Relationship Facet already
compiled, so this module never pairs a reverse declaration with its peer nor
swaps a join to find the far side: every direction — defining or reverse —
names the Entity it reaches as its own ``join.target.entity``. As-of propagation
needs that target and nothing else, so this module reads no cardinality, join
column, or ordering itself; it resolves the direction downstream consumers need
and stops there.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from parallax.core import inheritance, relationship
from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    RelationshipIdentity,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.predicate import (
    And,
    Comparison,
    Exists,
    Group,
    Narrow,
    Navigate,
    Not,
    NotExists,
    Or,
    PredicateNode,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import conjunction_terms

__all__ = ["canonicalize", "hop_as_of_terms", "resolve_relationship"]

_EMPTY_PINS: Mapping[TemporalDimension, str] = MappingProxyType({})


def canonicalize(
    op: PredicateNode,
    model: Metamodel,
    entity: EntityMetadata,
    root_pins: Mapping[TemporalDimension, str] = _EMPTY_PINS,
) -> PredicateNode:
    """Rewrite every navigation hop in ``op`` to carry its own per-hop as-of term.

    ``op`` is the flat predicate after the root's own temporal terms have already
    been injected. Query-wide result, temporal, and include wrappers never enter
    this function, so canonicalization does not peel or rebuild them. ``entity``
    is the read's queried Entity: the position a hop's
    ``Class.relationship`` reference is written against, which is ``entity`` at the
    top level and the enclosing hop's own target inside a hop's interior. That
    position locates an unresolvable reference rather than scoping resolution —
    the spelling itself names one Entity model-wide or none. ``root_pins`` is the root
    read's resolved per-axis instant —
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
    return _walk(op, model, entity, root_pins)


# --------------------------------------------------------------------------- #
# Fast pre-check (identity for navigation-free operations).                   #
# --------------------------------------------------------------------------- #
def _contains_navigation(op: PredicateNode) -> bool:
    match op:
        case Navigate() | Exists() | NotExists():
            return True
        case And(operands=operands) | Or(operands=operands):
            return any(_contains_navigation(operand) for operand in operands)
        case Not(operand=operand) | Group(operand=operand) | Narrow(operand=operand):
            return _contains_navigation(operand)
        case _:
            # Every remaining leaf (All/NoneOp/Comparison/Between/NullCheck/
            # StringMatch/Membership/NestedComparison/NestedMembership/
            # NestedNullCheck/NestedExists/NestedNotExists) carries no navigation.
            return False


# --------------------------------------------------------------------------- #
# The rewrite walk (only run once navigation is known to exist somewhere).    #
# --------------------------------------------------------------------------- #
def _walk(
    op: PredicateNode,
    model: Metamodel,
    entity: EntityMetadata,
    root_pins: Mapping[TemporalDimension, str],
) -> PredicateNode:
    match op:
        case Navigate(rel=rel, op=inner):
            return Navigate(rel=rel, op=_hop_inner(rel, inner, model, entity, root_pins))
        case Exists(rel=rel, op=inner):
            return Exists(rel=rel, op=_hop_inner(rel, inner, model, entity, root_pins))
        case NotExists(rel=rel, op=inner):
            return NotExists(rel=rel, op=_hop_inner(rel, inner, model, entity, root_pins))
        case And(operands=operands):
            return And(
                operands=tuple(_walk(operand, model, entity, root_pins) for operand in operands)
            )
        case Or(operands=operands):
            return Or(
                operands=tuple(_walk(operand, model, entity, root_pins) for operand in operands)
            )
        case Not(operand=operand):
            return Not(operand=_walk(operand, model, entity, root_pins))
        case Group(operand=operand):
            return Group(operand=_walk(operand, model, entity, root_pins))
        case Narrow(to=to, operand=operand):
            return Narrow(to=to, operand=_walk(operand, model, entity, root_pins))
        case _:
            # Every remaining node (All/NoneOp/Comparison/Between/NullCheck/
            # StringMatch/Membership/NestedComparison/NestedMembership/
            # NestedNullCheck/NestedExists/NestedNotExists) carries no navigation.
            return op


def _hop_inner(
    rel: str,
    inner: PredicateNode | None,
    model: Metamodel,
    owner: EntityMetadata,
    root_pins: Mapping[TemporalDimension, str],
) -> PredicateNode | None:
    """The hop's rewritten interior: its own navigation walked, then its own
    per-hop as-of term (if temporal) appended after (m-navigate As-of propagation).

    The interior's own hop references are written against this hop's TARGET, so
    that is the position threaded into the walk beneath it.
    """
    direction = resolve_relationship(rel, owner.identity, model)
    target = _entity(model, direction.join.target.entity)
    walked = _walk(inner, model, target, root_pins) if inner is not None else None
    return _inject_hop_as_of(walked, target, model, root_pins)


def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - guards an unvalidated operation
        raise ValueError(f"{identity.canonical!r} names no declared entity")
    return entity


def resolve_relationship(
    rel_ref: str, owner: EntityIdentity, model: Metamodel
) -> RelationshipMetadata:
    """Resolve a ``Class.relationship`` reference to the direction it navigates.

    The reference's class name is an operation reference, so it resolves model-wide
    by :func:`~parallax.core.metamodel.entity_by_name`'s rule and never adopts a
    namespace of its own — an accepted reference therefore always resolves here,
    which the owner-relative DECLARATION rule could not promise. ``owner`` is the
    Entity the reference is written against and locates an unresolvable one. The
    Identity that resolution produces then selects the direction from the
    Relationship Facet, the one place a reverse direction's inverted cardinality
    and swapped join exist — so a caller reads a compiled direction rather than
    re-pairing declarations.

    Exported so `parallax.core.deep_fetch` (the sole downstream `m-navigate`
    dependent) resolves each deep-fetch path
    segment's relationship through the SAME lookup this module's own hop
    canonicalization uses, rather than re-deriving it.
    """
    class_name, dot, member_name = rel_ref.rpartition(".")
    if not dot:  # pragma: no cover - guards an unvalidated operation
        raise ValueError(f"relationship reference {rel_ref!r} needs Class.relationship")
    declaring = entity_by_name(model, class_name)
    direction = (
        None
        if declaring is None
        else relationship.view(model).relationship(
            RelationshipIdentity(source_entity=declaring.identity, name=member_name)
        )
    )
    if direction is None:
        raise ValueError(
            f"{rel_ref!r} names no declared relationship on {class_name} "
            f"(written against {owner.canonical})"
        )
    return direction


def _temporal_declarer(model: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    """The Entity that actually DECLARES ``entity``'s as-of axes.

    A standalone Entity declares its own; an inheritance participant's temporal
    axes are declared on the family ROOT and inherited by every concrete subtype
    (`m-inheritance`), so a relationship target naming an abstract position (or
    even a concrete leaf) must resolve to the root to find them. The Inheritance
    Facet answers that for both shapes at once — a standalone Entity is its own
    root — so there is no ancestry walk and no second code path here.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical!r} names no declared entity")
    return _entity(model, view.root)


def hop_as_of_terms(
    target: EntityMetadata,
    model: Metamodel,
    root_pins: Mapping[TemporalDimension, str],
) -> tuple[PredicateNode, ...]:
    """The per-axis as-of term(s) for a hop's target Entity (m-navigate
    "As-of propagation"): empty for a non-temporal target; one term per its own
    declared dimension (two for a finite instant), Valid-Time-first — the
    root's pinned instant for that dimension (``root_pins``) when the root itself
    pinned a specific past moment, else **latest**.

    Exported (alongside :func:`resolve_relationship`) so `parallax.core.deep_fetch`
    composes the IDENTICAL per-hop as-of predicate for each deep-fetch child
    level, matched by axis exactly as a `navigate` / `exists` / `notExists` hop's
    own interior is rewritten by :func:`_inject_hop_as_of` below (which now
    builds on this same term derivation).
    """
    declarer = _temporal_declarer(model, target)
    axes = declarer.declared_as_of_axes
    if not axes:
        return ()
    terms: list[PredicateNode] = []
    # A Temporal Dimension's member value IS its canonical axis rank, so
    # Valid-Time-first needs no separate ordering table.
    for axis in sorted(axes, key=lambda item: item.dimension.value):
        start_ref = f"{declarer.identity.canonical}.{axis.start_attribute.name}"
        end_ref = f"{declarer.identity.canonical}.{axis.end_attribute.name}"
        instant = root_pins.get(axis.dimension)
        if instant is None:
            terms.append(Comparison(op="eq", attr=end_ref, value=INFINITY_LITERAL))
        else:
            terms.append(Comparison(op="lessThanEquals", attr=start_ref, value=instant))
            terms.append(Comparison(op="greaterThan", attr=end_ref, value=instant))
    return tuple(terms)


def _inject_hop_as_of(
    inner: PredicateNode | None,
    target: EntityMetadata,
    model: Metamodel,
    root_pins: Mapping[TemporalDimension, str],
) -> PredicateNode | None:
    """Append the target Entity's own per-axis as-of term(s) after ``inner``.

    A **non-temporal** target carries no as-of term at all (returns ``inner``
    unchanged — a strict identity, mirroring `inject_as_of`'s own non-temporal
    identity). A **temporal** target gets one term per its own declared axis,
    Valid-Time-first: the root's pinned instant for that dimension (``root_pins``) if
    the root itself pinned a specific past moment, else **latest** — covering both
    "an axis unpinned at the root defaults to latest" and "a temporal entity reached
    from a non-temporal one defaults every axis to latest" in one rule, since a
    non-temporal (or axis-undeclared) root simply never populates ``root_pins`` for
    that axis.
    """
    terms = hop_as_of_terms(target, model, root_pins)
    if not terms:
        return inner
    if inner is None:
        conjuncts: tuple[PredicateNode, ...] = terms
    else:
        conjuncts = (*conjunction_terms(inner), *terms)
    return conjuncts[0] if len(conjuncts) == 1 else And(operands=conjuncts)
