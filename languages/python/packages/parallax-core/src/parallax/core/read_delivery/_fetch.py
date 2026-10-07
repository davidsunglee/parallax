from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from parallax.core import deep_fetch, inheritance, opt_lock, read_lock
from parallax.core.base import ManagedValue
from parallax.core.db_port import DatabaseConnection, Row
from parallax.core.dialect import LockMode
from parallax.core.execution_lifecycle._activity import DatabaseCallScope
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.read_delivery._page import ABSENT, ROOT_LEVEL, ChildSlot, PageBuilder
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.unit_work import Concurrency

__all__ = [
    "attach_back_reference",
    "attach_children",
    "attach_empty",
    "correlation_member",
    "correlation_table",
    "entity_read_lock",
    "execute_read",
    "gather_keys",
    "guarded_parents",
    "parent_refs",
    "slot_table",
]


def entity_read_lock(
    meta: Metamodel, entity: EntityIdentity, preference: Concurrency | None
) -> LockMode | None:
    """The read-lock mode a participating read of ``entity`` carries, composed
    from the two policies read planning names at once.

    The lock follows the ENTITY, not the query: `m-opt-lock` derives that
    Entity's Effective Concurrency Strategy from the unit of work's one
    Concurrency Preference and the Entity's own Optimistic Lock Facet, and
    `m-read-lock` maps the derived strategy to the `m-dialect` lock parameter.
    So one transaction's deep fetch locks its unversioned levels while leaving
    its versioned and temporal ones lock-free, and the same level locks or not
    depending on the model rather than on the call.

    ``preference`` is ``None`` for a read no unit of work owns — a standalone
    read — which has no participation to derive a strategy from and therefore
    never locks.
    """
    if preference is None:
        return None
    return read_lock.mode_for(
        opt_lock.effective_strategy(preference, opt_lock.view(meta).key(entity))
    )


def correlation_table(
    plan: deep_fetch.ObjectQueryPlan, meta: Metamodel
) -> tuple[tuple[AttributeIdentity, ...], ...]:
    """Correlation members decoded during the identity pass for each source level."""
    table: list[list[AttributeIdentity]] = [[] for _ in range(len(plan.fetch_steps) + 1)]
    for index, step in enumerate(plan.fetch_steps):
        parent_source = (
            ROOT_LEVEL if isinstance(step.parent, deep_fetch.RootRef) else step.parent.index + 1
        )
        table[parent_source].append(correlation_member(meta, step.owner.identity))
        if isinstance(step, deep_fetch.QueryFetchStep):
            table[index + 1].append(correlation_member(meta, step.related.identity))
    return tuple(tuple(dict.fromkeys(members)) for members in table)


def slot_table(plan: deep_fetch.ObjectQueryPlan) -> tuple[tuple[ChildSlot, ...], ...]:
    """Which view slots each source level's parents can receive, indexed by
    source position: the root is 0 and fetch step ``i`` is ``i + 1``.

    A level contributes one slot to whichever source level its own PARENT rows
    came from, carrying that level's path-root guard as the concretes it admits
    and, for a back-reference, the target concretes its logical claims may
    resolve to. The table is dense over every source level the plan can produce
    a projection at — a level attaching nothing still owns an empty entry, and a
    back-reference level, which converts no row of its own, is simply never
    named as a parent.

    This is where the plan vocabulary stops: what crosses into Page assembly is
    slots, so nothing there interprets a fetch plan.
    """
    table: list[list[ChildSlot]] = [[] for _ in range(len(plan.fetch_steps) + 1)]
    for step in plan.fetch_steps:
        position = plan.includes.position(step.position)
        assert position.view is not None
        parent = (
            ROOT_LEVEL if isinstance(step.parent, deep_fetch.RootRef) else step.parent.index + 1
        )
        parent_position = plan.includes.position(position.parent or plan.includes.root)
        table[parent].append(
            ChildSlot(
                position.view,
                None if position.source == parent_position.target else frozenset(position.source),
                frozenset(position.target)
                if isinstance(step, deep_fetch.BackReferenceFetchStep)
                else None,
            )
        )
    return tuple(tuple(slots) for slots in table)


def attach_children(
    builder: PageBuilder,
    meta: Metamodel,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.QueryFetchStep,
    parents: tuple[int, ...],
    children: tuple[int, ...],
) -> None:
    """Fan one level's converted children back to their parents in memory,
    preserving fetched order within each to-many bucket."""
    position = tree.position(step.position)
    assert position.view is not None
    related = correlation_member(meta, step.related.identity)
    owner = correlation_member(meta, step.owner.identity)
    buckets: dict[object, list[int]] = {}
    for child in children:
        buckets.setdefault(builder.member_value(child, related), []).append(child)
    for parent in parents:
        matched = buckets.get(builder.member_value(parent, owner), [])
        if position.to_many:
            builder.write_view(parent, position.view, tuple(matched))
        else:
            builder.write_to_one(parent, position.view, matched)


def attach_empty(
    builder: PageBuilder,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.QueryFetchStep,
    parents: tuple[int, ...],
) -> None:
    """Attach the empty/null relationship result to every admitted parent.

    m-deep-fetch: an empty gathered parent-key set issues no child query at all,
    and every parent still gets a LOADED view — empty or null — rather than an
    unset one.
    """
    position = tree.position(step.position)
    assert position.view is not None
    empty: tuple[int, ...] | None = () if position.to_many else None
    for parent in parents:
        builder.write_view(parent, position.view, empty)


def attach_back_reference(
    builder: PageBuilder,
    meta: Metamodel,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.BackReferenceFetchStep,
    parents: tuple[int, ...],
) -> None:
    """Record an ancestor-revisit level for root-local identity resolution.

    A back-reference issues no SQL: m-case-format's "Back-reference cycles"
    guarantees the ancestor is already converted, so the parent's own correlation
    member names logical claims this builder has already registered. The Root
    View selects only its own reachable canonical claim among the targets the
    view schema records for the slot.
    """
    position = tree.position(step.position)
    assert position.view is not None
    owner = correlation_member(meta, step.owner.identity)
    for parent in parents:
        builder.write_reference(parent, position.view, step.family, owner)


def correlation_member(meta: Metamodel, attribute: AttributeIdentity) -> AttributeIdentity:
    """The Identity a converted node carries for the member ``attribute`` names.

    A relationship join addresses a correlation Attribute at the POSITION it
    reaches it through, which for an inheritance participant may be a descendant
    of the position that declares it (`Person.pets` joins `Pet.ownerId` for an
    Attribute `Animal` declares). A converted node keys every family-effective
    member by its own DECLARING identity, so the two spellings must be reconciled
    once here rather than by loosening how a node is keyed.

    Resolution runs over the addressed position's own ancestry chain rather than
    the family-wide projection superset, which is what keeps the member addressed
    where the join names it: disjoint sibling branches may reuse a member name
    (`m-inheritance` "Members do not shadow across ancestry"), so the superset can
    hold two same-named Attributes and only the chain distinguishes them.
    """
    position = inheritance.view(meta).entity(attribute.entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return attribute
    declared = position.applicable_attribute(attribute.name)
    if declared is None:  # pragma: no cover - a resolved join names a declared member
        return attribute
    return declared.identity


def execute_read(
    port: DatabaseConnection, compiled: CompiledRead, calls: DatabaseCallScope
) -> list[Row]:
    """Run one compiled read's statement inside its own Database Call bracket.

    A FAILED call finishes too, and the failure then propagates untouched: a
    call that reached the port and came back is work the lifecycle owes an
    account of, whatever it came back with. The bracket owns that, so this
    function announces only the rows it alone holds. Every row-producing read
    goes through here — a find level, and the resolving read a materializing
    predicate write runs — so the duration and failed-call semantics of a `read`
    call have exactly one definition.

    Takes the whole ``CompiledRead`` rather than a statement plus its document
    ordinals: the statement, the ordinals it must be executed with, and the
    target Entity the activity reports all come from one compile or from none.
    """
    statement = compiled.statement
    document_reads = compiled.document_reads
    with calls.database_call(statement, "read", compiled.target) as call:
        driver_sql = port.dialect.to_driver_sql(statement.sql)
        binds = list(statement.binds)
        rows = (
            port.execute(driver_sql, binds, document_reads)
            if document_reads
            else port.execute(driver_sql, binds)
        )
        call.read_completed(rows)
    return rows


def parent_refs(
    parent: deep_fetch.ParentRef,
    root_refs: tuple[int, ...],
    level_refs: Sequence[tuple[int, ...]],
) -> tuple[int, ...]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_refs
    return level_refs[parent.index]


def guarded_parents(
    builder: PageBuilder,
    tree: deep_fetch.IncludeTree,
    step: deep_fetch.FetchStep,
    parents: tuple[int, ...],
) -> tuple[int, ...]:
    """The parent nodes a path-root guard admits into ``level``
    (m-deep-fetch "Path-root guards").

    A guard is a SOURCE filter, not a view: it selects which already-converted
    parents this level gathers keys from and attaches to, so an excluded parent
    never sees the level's view at all — the closed-world distinction
    between "no such related row" and "this object never participated". Selection
    is by each parent's OWN resolved concrete Entity, which is exactly what a
    guard's resolved source set enumerates. An unguarded level returns the
    sequence unchanged.
    """
    position = tree.position(step.position)
    assert position.parent is not None
    if position.source == tree.position(position.parent).target:
        return parents
    admitted = frozenset(position.source)
    return tuple(parent for parent in parents if builder.concrete_of(parent) in admitted)


def gather_keys(
    builder: PageBuilder, parents: tuple[int, ...], member: AttributeIdentity
) -> list[ManagedValue]:
    """The values of ``member`` across ``parents`` that name something.

    A member this level's parents did not carry and one stored null are distinct
    answers now and both drop out here: neither names a child row, so gathering
    either would widen the child query by a key nothing joins on.

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own managed value, even though a projection's values are typed as plain
    ``object``; the cast reflects that runtime invariant.
    """
    keys: list[ManagedValue] = []
    seen: set[ManagedValue] = set()
    for value in (builder.member_value(parent, member) for parent in parents):
        if value is None or value is ABSENT:
            continue
        key = cast("ManagedValue", value)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys
